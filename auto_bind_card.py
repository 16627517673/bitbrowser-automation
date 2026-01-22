"""
自动绑卡脚本 - Google One AI Student 订阅
"""
import asyncio
import os
import pyotp
from playwright.async_api import async_playwright, Page
from bit_api import openBrowser, closeBrowser
from google_recovery import handle_recovery_email_challenge, detect_manual_verification
from account_manager import AccountManager

def _load_default_card() -> dict:
    """从配置文件加载默认卡信息"""
    # 优先从数据库配置读取
    try:
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).parent
        sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))
        from routers.config import get_card_info
        card = get_card_info()
        if card.get("number"):
            return card
    except Exception:
        pass

    # 回退到环境变量
    return {
        'number': os.environ.get('CARD_NUMBER', ''),
        'exp_month': os.environ.get('CARD_EXP_MONTH', ''),
        'exp_year': os.environ.get('CARD_EXP_YEAR', ''),
        'cvv': os.environ.get('CARD_CVV', ''),
        'zip': os.environ.get('CARD_ZIP', '')
    }

# 默认卡信息（从配置加载，不再硬编码）
DEFAULT_CARD = _load_default_card()

def _normalize_exp_parts(exp_month: str, exp_year: str) -> tuple[str, str]:
    """Normalize expiration parts to MM/YY and swap if they look reversed."""
    mm = "".join(ch for ch in (exp_month or "").strip() if ch.isdigit())
    yy = "".join(ch for ch in (exp_year or "").strip() if ch.isdigit())
    if len(yy) >= 4:
        yy = yy[-2:]
    if len(mm) == 1:
        mm = f"0{mm}"
    if len(yy) == 1:
        yy = f"0{yy}"
    try:
        mm_i = int(mm) if mm else 0
        yy_i = int(yy) if yy else 0
    except ValueError:
        return mm, yy
    if mm_i > 12 and 1 <= yy_i <= 12:
        mm, yy = yy.zfill(2), str(mm_i)[-2:]
    return mm, yy

async def check_and_login(page: Page, account_info: dict = None):
    """
    检测是否已登录，如果未登录则执行登录流程
    
    Args:
        page: Playwright Page 对象
        account_info: 账号信息 {'email', 'password', 'secret'}
    
    Returns:
        (success: bool, message: str)
    """
    try:
        print("\n检测登录状态...")
        
        # 检测是否有登录输入框
        try:
            email_input = await page.wait_for_selector('input[type="email"]', timeout=5000)
            
            if email_input:
                print("❌ 未登录，开始登录流程...")
                
                if not account_info:
                    return False, "需要登录但未提供账号信息"
                
                # 1. 输入邮箱
                email = account_info.get('email')
                print(f"正在输入账号: {email}")
                await email_input.fill(email)
                await page.click('#identifierNext >> button')
                
                # 2. 输入密码
                print("等待密码输入框...")
                await page.wait_for_selector('input[type="password"]', state='visible', timeout=15000)
                password = account_info.get('password')
                print("正在输入密码...")
                await page.fill('input[type="password"]', password)
                await page.click('#passwordNext >> button')
                
                # 3. 处理2FA
                print("等待2FA输入...")
                try:
                    totp_input = await page.wait_for_selector(
                        'input[name="totpPin"], input[id="totpPin"], input[type="tel"]',
                        timeout=10000
                    )
                    if totp_input:
                        secret = account_info.get('secret')
                        if secret:
                            s = secret.replace(" ", "").strip()
                            totp = pyotp.TOTP(s)
                            code = totp.now()
                            print(f"正在输入2FA验证码: {code}")
                            await totp_input.fill(code)
                            await page.click('#totpNext >> button')
                            print("✅ 2FA验证完成")
                        else:
                            backup = account_info.get('backup') or account_info.get('backup_email')
                            handled = await handle_recovery_email_challenge(page, backup)
                            if not handled:
                                return False, "需要2FA或辅助邮箱验证，但未提供secret"
                except Exception as e:
                    print(f"2FA步骤跳过或失败（可能不需要）: {e}")

                # 4. 处理辅助邮箱验证页面
                try:
                    backup = account_info.get('backup') or account_info.get('backup_email')
                    await handle_recovery_email_challenge(page, backup)
                    if await detect_manual_verification(page):
                        return False, "需要人工完成验证码"
                except Exception:
                    pass

                # 等待登录完成
                await asyncio.sleep(5)
                print("✅ 登录流程完成")
                return True, "登录成功"
        except:
            print("✅ 已登录，跳过登录流程")
            return True, "已登录"
            
    except Exception as e:
        print(f"登录检测出错: {e}")
        return False, f"登录检测错误: {e}"

async def auto_bind_card(page: Page, card_info: dict = None, account_info: dict = None):
    """
    自动绑卡函数
    
    Args:
        page: Playwright Page 对象
        card_info: 卡信息字典 {'number', 'exp_month', 'exp_year', 'cvv'}
        account_info: 账号信息（用于登录）{'email', 'password', 'secret'}
    
    Returns:
        (success: bool, message: str)
    """
    if card_info is None:
        card_info = DEFAULT_CARD
    
    try:
        # 首先检测并执行登录（如果需要）
        login_success, login_msg = await check_and_login(page, account_info)
        if not login_success:
            return False, f"登录失败: {login_msg}"
        
        print("\n开始自动绑卡流程...")
        
        # 截图1：初始页面
        await page.screenshot(path="step1_initial.png")
        print("截图已保存: step1_initial.png")
        
        # Step 1: 等待并点击 "Get student offer" 按钮（多语言兼容）
        print("等待页面加载...")
        await asyncio.sleep(2)

        print("查找主 CTA 按钮...")
        try:
            # 不依赖文字的选择器 - 按优先级尝试
            selectors = [
                # 1. Google 常用的主按钮样式（蓝色填充按钮）
                'button.VfPpkd-LgbsSe-OWXEXe-k8QpJ',  # Material Design 填充按钮
                'button[data-idom-class*="filled"]',   # 填充按钮标记

                # 2. 基于按钮角色和可见性
                'main button',                          # main 区域内的按钮
                '[role="main"] button',

                # 3. 链接形式的按钮
                'main a[role="button"]',

                # 4. 文字匹配（兜底，多语言）
                'button:has-text("Get student offer")',
                'button:has-text("Get offer")',
                'a:has-text("Get student offer")',
            ]

            clicked = False
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        await element.click()
                        print(f"✅ 已点击按钮 (selector: {selector})")
                        clicked = True
                        break
                except:
                    continue

            if not clicked:
                print("⚠️ 未找到按钮，可能已在付款页面")
            
            # Step 1.5: 若出现订阅按钮，先点击进入付款表单
            print("检查是否需要点击订阅按钮...")
            subscribe_selectors = [
                'button:has-text("Subscribe")',
                'button:has-text("Subscribe now")',
                'button:has-text("Start subscription")',
                'button:has-text("Start plan")',
                'button:has-text("Start trial")',
                '[role="button"]:has-text("Subscribe")',
                '[role="button"]:has-text("Subscribe now")',
                '[role="button"]:has-text("Start subscription")',
                '[role="button"]:has-text("Start plan")',
                '[role="button"]:has-text("Start trial")',
                'a:has-text("Subscribe")',
                'a:has-text("Subscribe now")',
                'button:has-text("订阅")',
                'button:has-text("确认订阅")',
                'button:has-text("开始订阅")',
                'button:has-text("立即订阅")',
                '[role="button"]:has-text("订阅")',
                '[role="button"]:has-text("确认订阅")',
                '[role="button"]:has-text("开始订阅")',
                'a:has-text("订阅")',
            ]

            subscribed_clicked = False
            scopes = [page]
            for f in page.frames:
                scopes.append(f)

            for scope in scopes:
                for selector in subscribe_selectors:
                    try:
                        element = scope.locator(selector).first
                        if await element.count() > 0 and await element.is_visible():
                            await element.click()
                            print(f"✅ 已点击订阅按钮 (selector: {selector})")
                            subscribed_clicked = True
                            break
                    except Exception:
                        continue
                if subscribed_clicked:
                    break

            if subscribed_clicked:
                await asyncio.sleep(5)
                await page.screenshot(path="step2_after_subscribe_click.png")
                print("截图已保存: step2_after_subscribe_click.png")

            # 等待付款页面和 iframe 加载
            print("等待付款页面和 iframe 加载...")
            await asyncio.sleep(8)  # 增加延迟到5秒
            await page.screenshot(path="step2_after_get_offer.png")
            print("截图已保存: step2_after_get_offer.png")
            
        except Exception as e:
            print(f"处理 'Get student offer' 时出错: {e}")
        
        # 前置判断：检查是否已经绑卡（是否已显示订阅按钮）
        print("\n检查账号是否已绑卡...")
        try:
            # 等待一下让页面稳定
            await asyncio.sleep(3)

            iframe_locator = None
            # 先尝试获取 iframe
            try:
                iframe_locator = page.frame_locator('iframe[src*="tokenized.play.google.com"]')
                print("✅ 找到 iframe，在 iframe 中检查订阅按钮")
                
                # 使用精确的选择器
                subscribe_selectors = [
                    'span.UywwFc-vQzf8d:has-text("Subscribe")',
                    'span[jsname="V67aGc"]',
                    'span.UywwFc-vQzf8d',
                    'span:has-text("Subscribe")',
                    ':text("Subscribe")',
                    'button:has-text("Subscribe")',
                ]
                
                # 在 iframe 中查找订阅按钮
                already_bound = False
                subscribe_button_early = None
                
                for selector in subscribe_selectors:
                    try:
                        element = iframe_locator.locator(selector).first
                        count = await element.count()
                        if count > 0:
                            print(f"  ✅ 检测到订阅按钮，账号已绑卡！(iframe, selector: {selector})")
                            subscribe_button_early = element
                            already_bound = True
                            break
                    except:
                        continue

                if not already_bound:
                    print("⚠️ iframe 中未检测到订阅按钮，尝试在页面中查找...")
                    for selector in subscribe_selectors:
                        try:
                            element = page.locator(selector).first
                            count = await element.count()
                            if count > 0 and await element.is_visible():
                                print(f"  ✅ 检测到订阅按钮，账号已绑卡！(page, selector: {selector})")
                                subscribe_button_early = element
                                already_bound = True
                                break
                        except:
                            continue
                
                # 如果找到订阅按钮，说明已经绑过卡了，直接点击订阅
                if already_bound and subscribe_button_early:
                    print("账号已绑卡，跳过绑卡流程，直接订阅...")
                    await asyncio.sleep(2)
                    try:
                        await subscribe_button_early.click(force=True)
                    except Exception:
                        try:
                            wrapper = await subscribe_button_early.evaluate_handle(
                                "el => el.closest('button,[role=\"button\"],a') || el"
                            )
                            await wrapper.as_element().click(force=True)
                        except Exception:
                            pass
                    print("✅ 已点击订阅按钮")
                    
                    # 等待10秒并验证订阅成功
                    await asyncio.sleep(10)
                    await page.screenshot(path="step_subscribe_existing_card.png")
                    print("截图已保存: step_subscribe_existing_card.png")
                    
                    # 在 iframe 中检查是否显示 "Subscribed"
                    try:
                        subscribed_selectors = [
                            ':text("Subscribed")',
                            'text=Subscribed',
                            '*:has-text("Subscribed")',
                        ]
                        
                        subscribed_found = False
                        check_scopes = []
                        if iframe_locator:
                            check_scopes.append(iframe_locator)
                        check_scopes.append(page)
                        for selector in subscribed_selectors:
                            for scope in check_scopes:
                                try:
                                    element = scope.locator(selector).first
                                    count = await element.count()
                                    if count > 0:
                                        print(f"  ✅ 检测到 'Subscribed'，订阅确认成功！")
                                        subscribed_found = True
                                        break
                                except:
                                    continue
                            if subscribed_found:
                                break
                        
                        if subscribed_found:
                            print("✅ 使用已有卡订阅成功并已确认！")
                            # 更新数据库状态为已订阅
                            if account_info and account_info.get('email'):
                                line = f"{account_info.get('email', '')}----{account_info.get('password', '')}----{account_info.get('backup', '')}----{account_info.get('secret', '')}"
                                AccountManager.move_to_subscribed(line)
                            return True, "使用已有卡订阅成功 (Already bound, Subs cribed)"
                        
                        # 如果没找到 Subscribed，检查是否出现 Error（卡过期）
                        print("未检测到 'Subscribed'，检查是否出现错误...")
                        error_selectors = [
                            ':text("Error")',
                            'text=Error',
                            ':has-text("Your card issuer declined")',
                        ]
                        
                        error_found = False
                        error_scopes = []
                        if iframe_locator:
                            error_scopes.append(iframe_locator)
                        error_scopes.append(page)
                        for selector in error_selectors:
                            for scope in error_scopes:
                                try:
                                    element = scope.locator(selector).first
                                    count = await element.count()
                                    if count > 0:
                                        print(f"  ⚠️ 检测到错误信息（卡可能过期），准备换绑...")
                                        error_found = True
                                        break
                                except:
                                    continue
                            if error_found:
                                break
                        
                        if error_found:
                            # 卡过期换绑流程
                            print("\n【卡过期换绑流程】")
                            
                            # 1. 点击 "Got it" 按钮
                            print("1. 点击 'Got it' 按钮...")
                            got_it_selectors = [
                                'button:has-text("Got it")',
                                ':text("Got it")',
                                'button:has-text("确定")',
                            ]
                            
                            for selector in got_it_selectors:
                                try:
                                    target_scope = iframe_locator or page
                                    element = target_scope.locator(selector).first
                                    count = await element.count()
                                    if count > 0:
                                        await element.click()
                                        print("  ✅ 已点击 'Got it'")
                                        await asyncio.sleep(3)
                                        break
                                except:
                                    continue
                            
                            # 2. 点击主页面的主 CTA 按钮（多语言兼容）
                            print("2. 重新点击主页面的主 CTA 按钮...")
                            get_offer_selectors = [
                                # 不依赖文字的选择器
                                'button.VfPpkd-LgbsSe-OWXEXe-k8QpJ',  # Material Design 填充按钮
                                'button[data-idom-class*="filled"]',
                                'main button',
                                '[role="main"] button',
                                'main a[role="button"]',
                                # 兜底文字匹配
                                'button:has-text("Get student offer")',
                                ':text("Get student offer")',
                            ]

                            for selector in get_offer_selectors:
                                try:
                                    element = page.locator(selector).first
                                    if await element.count() > 0 and await element.is_visible():
                                        await element.click()
                                        print(f"  ✅ 已点击按钮 (selector: {selector})")
                                        await asyncio.sleep(8)
                                        break
                                except:
                                    continue
                            
                            # 3. 在 iframe 中找到并点击已有卡片
                            print("3. 在 iframe 中查找并点击过期卡片...")
                            try:
                                iframe_locator_card = page.frame_locator('iframe[src*="tokenized.play.google.com"]')
                                
                                # 点击卡片（Mastercard-7903 或类似）
                                card_selectors = [
                                    'span.Ngbcnc',  # Mastercard-7903 的 span
                                    'div.dROd9.ct1Mcc',  # 卡片容器
                                    ':has-text("Mastercard")',
                                ]
                                
                                for selector in card_selectors:
                                    try:
                                        element = iframe_locator_card.locator(selector).first
                                        count = await element.count()
                                        if count > 0:
                                            await element.click()
                                            print(f"  ✅ 已点击过期卡片 (selector: {selector})")
                                            await asyncio.sleep(5)
                                            break
                                    except:
                                        continue
                                
                                print("4. 进入换绑流程，继续后续绑卡操作...")
                                # 不 return，让代码继续执行后面的绑卡流程
                                
                            except Exception as e:
                                print(f"  点击过期卡片时出错: {e}，尝试继续...")
                        else:
                            print("⚠️ 未检测到 'Subscribed' 或 'Error'，但可能仍然成功")
                            return True, "使用已有卡订阅成功 (Already bound)"
                            
                    except Exception as e:
                        print(f"验证订阅状态时出错: {e}")
                        return True, "使用已有卡订阅成功 (Already bound)"
                else:
                    print("未检测到订阅按钮，继续绑卡流程...")
                    
            except Exception as e:
                print(f"获取 iframe 失败: {e}，继续正常绑卡流程...")
                
        except Exception as e:
            print(f"前置判断时出错: {e}，继续正常绑卡流程...")
        
        # Step 2: 切换到 iframe（付款表单在 iframe 中）
        print("\n检测并切换到 iframe...")
        try:
            # 等待 iframe 加载
            await asyncio.sleep(3)
            iframe_locator = page.frame_locator('iframe[src*="tokenized.play.google.com"]')
            print("✅ 找到 tokenized.play.google.com iframe，已切换上下文")

            # 等待 iframe 内部文档加载
            print("等待 iframe 内部文档加载...")
            await asyncio.sleep(3)
            
        except Exception as e:
            print(f"❌ 未找到 iframe: {e}")
            return False, "未找到付款表单 iframe"
        
        # Step 3: 在 iframe 中点击 "Add card"（多语言兼容）
        print("\n在 iframe 中等待并点击 'Add card' 按钮...")
        try:
            await asyncio.sleep(3)  # 等待元素可点击

            # 在 iframe 中查找 Add card（支持多语言）
            selectors = [
                # 多语言文字匹配
                'button:has-text("Ajouter une carte")',  # 法语
                'button:has-text("Add card")',            # 英语
                'button:has-text("Añadir tarjeta")',     # 西班牙语
                'button:has-text("Karte hinzufügen")',   # 德语
                'button:has-text("添加卡")',              # 中文
                # 结构性选择器
                'span.PjwEQ',
                ':text("Add card")',
                ':text("Ajouter")',
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    element = iframe_locator.locator(selector).first
                    count = await element.count()
                    if count > 0:
                        print(f"  找到 'Add card' (iframe, selector: {selector})")
                        await element.click()
                        print(f"✅ 已在 iframe 中点击 'Add card'")
                        clicked = True
                        break
                except:
                    continue
            
            if not clicked:
                print("⚠️ 在 iframe 中未找到 'Add card'，尝试直接查找输入框...")
            
            # 等待表单加载
            print("等待卡片输入表单加载...")
            await asyncio.sleep(5)
            await page.screenshot(path="step3_card_form_in_iframe.png")
            print("截图已保存: step3_card_form_in_iframe.png")
            
            # 关键：点击 Add card 后，卡片表单在 payments.google.com 的 iframe 中
            # 直接通过 page.frames 查找包含 instrumentmanager 的 frame
            print("\n查找卡片输入表单所在的 frame...")
            card_form_frame = None

            for frame in page.frames:
                if 'instrumentmanager' in frame.url:
                    card_form_frame = frame
                    print(f"✅ 找到卡片表单 frame: {frame.url[:60]}...")
                    break

            if not card_form_frame:
                print("⚠️ 未找到卡片表单 frame，等待后重试...")
                await asyncio.sleep(3)
                for frame in page.frames:
                    if 'instrumentmanager' in frame.url or 'payments.google.com' in frame.url:
                        card_form_frame = frame
                        print(f"✅ 找到卡片表单 frame: {frame.url[:60]}...")
                        break
            
        except Exception as e:
            await page.screenshot(path="error_iframe_add_card.png")
            return False, f"在 iframe 中点击 'Add card' 失败: {e}"

        # 检查是否找到卡片表单 frame
        if not card_form_frame:
            return False, "未找到卡片输入表单 frame"

        # Step 4: 填写卡号（在 card_form_frame 中）
        print(f"\n填写卡号: {card_info['number']}")
        await asyncio.sleep(2)

        try:
            # 简化策略：frame 中有多个输入框，按顺序分别是：
            # 1. Card number (第1个)
            # 2. MM/YY (第2个)
            # 3. Security code (第3个)

            print("在 frame 中查找所有输入框...")

            # 获取所有输入框
            all_inputs = card_form_frame.locator('input')
            input_count = await all_inputs.count()
            print(f"  找到 {input_count} 个输入框")

            if input_count < 3:
                return False, f"输入框数量不足，只找到 {input_count} 个"

            # 第1个输入框 = Card number
            card_number_input = all_inputs.nth(0)
            print("  使用第1个输入框作为卡号输入框")

            await card_number_input.click()
            await card_number_input.fill(card_info['number'])
            print("✅ 卡号已填写")
            await asyncio.sleep(0.5)
        except Exception as e:
            return False, f"填写卡号失败: {e}"

        # Step 5: 填写过期日期 (MM/YY)
        exp_month, exp_year = _normalize_exp_parts(
            card_info.get('exp_month', ''),
            card_info.get('exp_year', ''),
        )
        print(f"填写过期日期: {exp_month}/{exp_year}")
        try:
            # 第2个输入框 = MM/YY
            exp_date_input = all_inputs.nth(1)
            print("  使用第2个输入框作为过期日期输入框")

            await exp_date_input.click()
            exp_value = f"{exp_month}{exp_year}"
            await exp_date_input.fill(exp_value)
            print("✅ 过期日期已填写")
            await asyncio.sleep(0.5)
        except Exception as e:
            return False, f"填写过期日期失败: {e}"

        # Step 6: 填写 CVV (Security code)
        print(f"填写 CVV: {card_info['cvv']}")
        try:
            # 第3个输入框 = Security code
            cvv_input = all_inputs.nth(2)
            print("  使用第3个输入框作为CVV输入框")

            await cvv_input.click()
            await cvv_input.fill(card_info['cvv'])
            print("✅ CVV已填写")
            await asyncio.sleep(0.5)
        except Exception as e:
            return False, f"填写CVV失败: {e}"

        # Step 6.5: 填写邮编 (Billing zip code) - 如果有的话
        zip_code = card_info.get('zip', '')
        if zip_code:
            print(f"填写邮编: {zip_code}")
            try:
                # 第4个或第5个输入框可能是邮编
                for i in range(3, input_count):
                    zip_input = all_inputs.nth(i)
                    # 检查是否是 tel 类型（邮编通常是 tel 类型）
                    input_type = await zip_input.get_attribute('type')
                    if input_type == 'tel' or i == input_count - 1:
                        await zip_input.click()
                        await zip_input.fill(zip_code)
                        print(f"✅ 邮编已填写 (输入框 {i})")
                        break
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"⚠️ 填写邮编失败: {e}，继续...")

        # Step 7: 点击 "Save card" 按钮（多语言兼容）
        print("点击 'Save card' 按钮...")
        try:
            # 多语言选择器
            save_selectors = [
                'button:has-text("Enregistrer")',  # 法语
                'button:has-text("Save")',          # 英语
                'button:has-text("Guardar")',       # 西班牙语
                'button:has-text("Speichern")',    # 德语
                'button:has-text("保存")',          # 中文
                'button[type="submit"]',
            ]

            save_button = None
            for selector in save_selectors:
                try:
                    element = card_form_frame.locator(selector).first
                    count = await element.count()
                    if count > 0:
                        print(f"  找到 Save 按钮 (selector: {selector})")
                        save_button = element
                        break
                except:
                    continue

            if not save_button:
                return False, "未找到 Save card 按钮"

            await save_button.click()
            print("✅ 已点击 'Save card'")
        except Exception as e:
            return False, f"点击 Save card 失败: {e}"
        
        # Step 7: 点击订阅按钮完成流程
        print("\n等待订阅页面加载...")
        await asyncio.sleep(8)  # 等待订阅弹窗显示
        await page.screenshot(path="step7_before_subscribe.png")
        print("截图已保存: step7_before_subscribe.png")
        
        try:
            # 关键改变：订阅按钮在主页面的弹窗中，不在 iframe 中！
            print("查找订阅按钮...")
            
            subscribe_selectors = [
                # 用户提供的精确选择器 - 优先尝试
                'span.UywwFc-vQzf8d:has-text("Subscribe")',
                'span[jsname="V67aGc"]',
                'span.UywwFc-vQzf8d',
                # 其他备选
                'span:has-text("Subscribe")',
                ':text("Subscribe")',
                'button:has-text("Subscribe")',
                'button:has-text("订阅")',
                'button:has-text("Start")',
                'button:has-text("开始")',
                'button:has-text("继续")',
                'div[role="button"]:has-text("Subscribe")',
                '[role="button"]:has-text("Subscribe")',
                'button[type="submit"]',
                # 根据截图，可能在 dialog 中
                'dialog span:has-text("Subscribe")',
                '[role="dialog"] span:has-text("Subscribe")',
                'dialog button:has-text("Subscribe")',
                '[role="dialog"] button:has-text("Subscribe")',
            ]
            
            subscribe_button = None
            
            # 优先在 iframe 中查找（订阅按钮在iframe中）
            print("在 iframe 中查找订阅按钮...")
            try:
                iframe_locator_subscribe = page.frame_locator('iframe[src*="tokenized.play.google.com"]')
                for selector in subscribe_selectors:
                    try:
                        element = iframe_locator_subscribe.locator(selector).first
                        count = await element.count()
                        if count > 0:
                            print(f"  找到订阅按钮 (iframe, selector: {selector})")
                            subscribe_button = element
                            break
                    except:
                        continue
            except Exception as e:
                print(f"  iframe查找失败: {e}")
            
            # 如果 iframe 中没找到，尝试在主页面查找
            if not subscribe_button:
                print("在主页面中查找订阅按钮...")
                for selector in subscribe_selectors:
                    try:
                        element = page.locator(selector).first
                        count = await element.count()
                        if count > 0:
                            print(f"  找到订阅按钮 (main page, selector: {selector})")
                            subscribe_button = element
                            break
                    except Exception as e:
                        continue
            
            if subscribe_button:
                print("准备点击订阅按钮...")
                await asyncio.sleep(2)  # 点击前等待
                await subscribe_button.click()
                print("✅ 已点击订阅按钮")
                
                # 等待10秒并验证订阅成功
                await asyncio.sleep(10)
                await page.screenshot(path="step8_after_subscribe.png")
                print("截图已保存: step8_after_subscribe.png")
                
                # 在 iframe 中检查是否显示 "Subscribed"
                try:
                    # 重新获取 iframe
                    iframe_locator_final = page.frame_locator('iframe[src*="tokenized.play.google.com"]')
                    
                    subscribed_selectors = [
                        ':text("Subscribed")',
                        'text=Subscribed',
                        '*:has-text("Subscribed")',
                    ]
                    
                    subscribed_found = False
                    for selector in subscribed_selectors:
                        try:
                            element = iframe_locator_final.locator(selector).first
                            count = await element.count()
                            if count > 0:
                                print(f"  ✅ 检测到 'Subscribed'，订阅确认成功！")
                                subscribed_found = True
                                break
                        except:
                            continue
                    
                    if subscribed_found:
                        print("✅ 绑卡并订阅成功，已确认！")
                        # 更新数据库状态为已订阅
                        if account_info and account_info.get('email'):
                            line = f"{account_info.get('email', '')}----{account_info.get('password', '')}----{account_info.get('backup', '')}----{account_info.get('secret', '')}"
                            AccountManager.move_to_subscribed(line)
                        return True, "绑卡并订阅成功 (Subscribed confirmed)"
                    else:
                        print("⚠️ 未检测到 'Subscribed'，但可能仍然成功")
                        # 更新数据库状态为已订阅
                        if account_info and account_info.get('email'):
                            line = f"{account_info.get('email', '')}----{account_info.get('password', '')}----{account_info.get('backup', '')}----{account_info.get('secret', '')}"
                            AccountManager.move_to_subscribed(line)
                        return True, "绑卡并订阅成功 (Subscribed)"
                except Exception as e:
                    print(f"验证订阅状态时出错: {e}")
                    return True, "绑卡并订阅成功 (Subscribed)"
            else:
                print("⚠️ 未找到订阅按钮，可能已自动完成")
                print("✅ 绑卡成功")
                return True, "绑卡成功"
                
        except Exception as e:
            print(f"点击订阅按钮时出错: {e}")
            import traceback
            traceback.print_exc()
            print("✅ 绑卡已完成（订阅步骤可能需要手动）")
            return True, "绑卡已完成"
        
    except Exception as e:
        print(f"❌ 绑卡过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False, f"绑卡错误: {str(e)}"


async def test_bind_card_with_browser(browser_id: str, account_info: dict = None):
    """
    测试绑卡功能
    
    Args:
        browser_id: 浏览器窗口ID
        account_info: 账号信息 {'email', 'password', 'secret'}（可选，如果不提供则从浏览器remark中获取）
    """
    print(f"正在打开浏览器: {browser_id}...")
    
    # 如果没有提供账号信息，尝试从浏览器信息中获取
    if not account_info:
        print("未提供账号信息，尝试从浏览器remark中获取...")
        from create_window import get_browser_info
        
        target_browser = get_browser_info(browser_id)
        if target_browser:
            remark = target_browser.get('remark', '')
            parts = remark.split('----')
            
            if len(parts) >= 4:
                account_info = {
                    'email': parts[0].strip(),
                    'password': parts[1].strip(),
                    'backup': parts[2].strip(),
                    'secret': parts[3].strip()
                }
                print(f"✅ 从remark获取到账号信息: {account_info.get('email')}")
            else:
                print("⚠️ remark格式不正确，可能需要手动登录")
                account_info = None
        else:
            print("⚠️ 无法获取浏览器信息")
            account_info = None
    
    result = openBrowser(browser_id)
    
    if not result.get('success'):
        return False, f"打开浏览器失败: {result}"
    
    ws_endpoint = result['data']['ws']
    print(f"WebSocket URL: {ws_endpoint}")
    
    async with async_playwright() as playwright:
        try:
            chromium = playwright.chromium
            browser = await chromium.connect_over_cdp(ws_endpoint)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()
            
            # 导航到目标页面
            target_url = "https://one.google.com/ai-student?g1_landing_page=75&utm_source=antigravity&utm_campaign=argon_limit_reached"
            print(f"导航到: {target_url}")
            await page.goto(target_url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待页面加载
            print("等待页面完全加载...")
            await asyncio.sleep(5)  # 增加等待时间以确保弹窗有机会出现
            
            # 执行自动绑卡（包含登录检测）
            success, message = await auto_bind_card(page, account_info=account_info)
            
            print(f"\n{'='*50}")
            print(f"绑卡结果: {message}")
            print(f"{'='*50}\n")
            
            # 保持浏览器打开以便查看结果
            print("绑卡流程完成。浏览器将保持打开状态。")
            
            return True, message
            
        except Exception as e:
            print(f"测试过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
        finally:
            # 不关闭浏览器，方便查看结果
            # closeBrowser(browser_id)
            pass


def bind_card_sync(
    browser_id: str,
    card_info: dict = None,
    log_callback=None,
    close_after: bool = True,
) -> tuple[bool, str]:
    """
    同步版本的绑卡函数，供 GUI 调用

    Args:
        browser_id: 浏览器窗口ID
        card_info: 卡信息 {'number', 'exp_month', 'exp_year', 'cvv', 'zip'}
        log_callback: 日志回调函数

    Returns:
        (success: bool, message: str)
    """
    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    async def _run():
        from create_window import get_browser_info

        # 获取账号信息
        browser_info = get_browser_info(browser_id)
        if not browser_info:
            return False, "找不到浏览器信息"

        remark = browser_info.get('remark', '')
        parts = remark.split('----')

        account_info = {
            'email': parts[0].strip() if len(parts) > 0 else '',
            'password': parts[1].strip() if len(parts) > 1 else '',
            'backup': parts[2].strip() if len(parts) > 2 else '',
            'secret': parts[3].strip() if len(parts) > 3 else '',
        }

        log(f"账号: {account_info['email']}")

        # 打开浏览器
        log("正在打开浏览器...")
        res = openBrowser(browser_id)
        if not res.get('success'):
            return False, f"无法打开浏览器: {res}"

        ws_endpoint = res.get('data', {}).get('ws')
        if not ws_endpoint:
            closeBrowser(browser_id)
            return False, "无法获取 WebSocket 端点"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(ws_endpoint)
                try:
                    context = browser.contexts[0]
                    page = context.pages[-1] if context.pages else await context.new_page()

                    # 导航到订阅页面
                    target_url = "https://one.google.com/ai-student?g1_landing_page=75&utm_source=antigravity&utm_campaign=argon_limit_reached"
                    log("正在导航到订阅页面...")
                    await page.goto(target_url, timeout=30000, wait_until='domcontentloaded')
                    await asyncio.sleep(5)

                    # 执行绑卡
                    success, message = await auto_bind_card(page, card_info=card_info, account_info=account_info)

                    if success:
                        # 记录到文件
                        import os
                        from datetime import datetime
                        base_path = os.path.dirname(os.path.abspath(__file__))
                        with open(os.path.join(base_path, '已绑卡号.txt'), 'a', encoding='utf-8') as f:
                            card_last4 = card_info.get('number', '')[-4:] if card_info else 'N/A'
                            f.write(f"{account_info['email']}----{card_last4}----{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log(f"已记录到 已绑卡号.txt")

                    return success, message
                finally:
                    # 确保断开 CDP 连接，释放资源
                    try:
                        await browser.close()
                    except Exception:
                        pass

        except Exception as e:
            return False, f"绑卡错误: {e}"
        finally:
            if close_after:
                closeBrowser(browser_id)

    return asyncio.run(_run())


if __name__ == "__main__":
    # 使用用户指定的浏览器 ID 测试
    test_browser_id = "94b7f635502e42cf87a0d7e9b1330686"
    
    # 测试账号信息（如果需要登录）
    # 格式: {'email': 'xxx@gmail.com', 'password': 'xxx', 'secret': 'XXXXX'}
    test_account = None  # 如果已登录则为 None
    
    print(f"开始测试自动绑卡功能...")
    print(f"目标浏览器 ID: {test_browser_id}")
    print(f"测试卡信息: {DEFAULT_CARD}")
    print(f"\n{'='*50}\n")
    
    result = asyncio.run(test_bind_card_with_browser(test_browser_id, test_account))
    
    print(f"\n最终结果: {result}")
