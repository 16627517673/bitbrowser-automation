"""
Google 账号语言设置脚本
将 Google 账号语言设置为英文 (English - United States)
"""
import asyncio
from playwright.async_api import async_playwright, Page
from bit_api import openBrowser, closeBrowser
from google_recovery import handle_recovery_email_challenge, detect_manual_verification

def _is_us_language_text(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    patterns = [
        "english (united states)",
        "english - united states",
        "english (us)",
        "english - us",
        "英语（美国）",
        "英语 (美国)",
        "英文（美国）",
        "英文 (美国)",
        "inglés (estados unidos)",
        "ingles (estados unidos)",
        "anglais (états-unis)",
        "englisch (vereinigte staaten)",
    ]
    return any(p in lowered for p in patterns)

async def _is_current_page_english(page: Page) -> bool:
    try:
        lang = await page.evaluate("document.documentElement.lang || ''")
    except Exception:
        lang = ""
    if not lang:
        try:
            lang = await page.evaluate("navigator.language || ''")
        except Exception:
            lang = ""
    normalized = (lang or "").lower().replace("_", "-").strip()
    return normalized in ("en", "en-us") or normalized.startswith("en-us-")

async def _is_page_lang_english(page: Page) -> bool:
    try:
        lang = await page.evaluate("document.documentElement.lang || ''")
    except Exception:
        return False
    normalized = (lang or "").lower().replace("_", "-").strip()
    return normalized in ("en", "en-us") or normalized.startswith("en-us-")

async def set_language_to_english(page: Page, password: str = "", backup_email: str = "") -> tuple[bool, str]:
    """
    将 Google 账号语言设置为英文

    Args:
        page: Playwright Page 对象

    Returns:
        (success: bool, message: str)
    """
    try:
        try:
            if await _is_page_lang_english(page):
                return True, "当前页面已是英文，跳过设置"
        except Exception:
            pass

        print("\n开始设置语言...")

        # 1. 导航到语言设置页面
        print("1. 导航到语言设置页面...")
        await page.goto('https://myaccount.google.com/language?hl=en&pli=1', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 已是 English (United States) 则跳过
        try:
            body_text = await page.inner_text('body')
        except Exception:
            body_text = ""
        if _is_us_language_text(body_text):
            return True, "当前已是 English (United States)，跳过"

        # 2. 检查当前语言是否已经是英文
        add_en = await page.locator(
            'button:has-text("Add a language"), button:has-text("Add another language"), '
            'button:has-text("Añadir un idioma"), button:has-text("Añadir otro idioma"), '
            'button:has-text("Aggiungi una lingua"), '
            'button:has-text("Aggiungi lingua"), '
            'button:has-text("Taal toevoegen"), button:has-text("Nog een taal toevoegen"), '
            'button:has-text("Ajouter une langue"), button:has-text("Ajouter une autre langue"), '
            'button:has-text("Sprache hinzufügen"), button:has-text("Weitere Sprache hinzufügen")'
        ).count()
        if add_en > 0:
            print("✅ 语言页面已加载")

        # 2.5 如遇到“Verify it’s you”，先完成验证
        try:
            body_text = await page.inner_text('body')
        except Exception:
            body_text = ""

        if "Verify it’s you" in body_text or "Verify it's you" in body_text or "sign in again" in body_text.lower():
            print("检测到验证身份页面，尝试继续...")
            try:
                next_btn = page.locator('button:has-text("Next"), button:has-text("继续"), [role="button"]:has-text("Next")').first
                if await next_btn.count() > 0 and await next_btn.is_visible():
                    await next_btn.click()
                    await asyncio.sleep(2)
            except Exception:
                pass

            # 可能需要输入密码
            try:
                pwd_input = await page.query_selector('input[type="password"]')
                if pwd_input and await pwd_input.is_visible() and password:
                    await pwd_input.fill(password)
                    await asyncio.sleep(0.5)
                    next_btn = await page.query_selector('button:has-text("Next"), button[type="submit"]')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(2)
            except Exception:
                pass

            # 处理辅助邮箱验证
            if backup_email:
                await handle_recovery_email_challenge(page, backup_email)

            if await detect_manual_verification(page):
                return False, "需要人工完成验证码"

            # 验证后重新进入语言页
            await page.goto('https://myaccount.google.com/language?hl=en&pli=1', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

        # 3. 点击编辑按钮（多语言兼容）
        print("2. 点击编辑语言按钮...")
        edit_selectors = [
            'button[aria-label*="Modifier la langue"]',  # 法语
            'button[aria-label*="Edit language"]',        # 英语
            'button[aria-label*="Sprache bearbeiten"]',  # 德语
            'button[aria-label*="Editar idioma"]',       # 西班牙语
            'button[aria-label*="Modifica lingua"]',     # 意大利语
            'button[aria-label*="编辑语言"]',             # 中文
            'button[aria-label*="Language"]',
            'button[aria-label*="Lingua"]',
            'button[aria-label*="Langue"]',
            'button[aria-label*="Sprache"]',
            'button[aria-label*="Idioma"]',
            'button[aria-label*="Taal bewerken"]',       # 荷兰语
            'button[aria-label*="Bewerk taal"]',         # 荷兰语
            'button[aria-label*="Taal"]',
            # 西班牙语/通用兜底
            'button[aria-label*="Idioma"]',
            'button:has-text("Idioma")',
            '[role="button"]:has-text("Idioma")',
            'button:has-text("Editar")',
            '[role="button"]:has-text("Editar")',
        ]

        clicked = False
        for selector in edit_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click()
                    clicked = True
                    print(f"   ✅ 点击编辑按钮 (selector: {selector})")
                    break
            except:
                continue

        if not clicked:
            # 兜底：在主区域内寻找带语言关键词的按钮
            label_keywords = ["language", "lingua", "langue", "sprache", "idioma", "taal"]
            try:
                main = page.locator('main, [role="main"]').first
                scope = main if await main.count() > 0 else page
            except Exception:
                scope = page
            for kw in label_keywords:
                for selector in (
                    f'button[aria-label*="{kw}"]',
                    f'[role="button"][aria-label*="{kw}"]',
                ):
                    try:
                        btn = scope.locator(selector).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            clicked = True
                            print("   ✅ 使用语言标签按钮打开语言选择")
                            break
                    except Exception:
                        continue
                if clicked:
                    break

        if not clicked:
            # 兜底：点击主区域内的第一个可点击元素
            try:
                main = page.locator('main, [role="main"]').first
                scope = main if await main.count() > 0 else page
                fallback = scope.locator('button, [role="button"], a').first
                if await fallback.count() > 0 and await fallback.first.is_visible():
                    await fallback.first.click()
                    clicked = True
                    print("   ✅ 使用兜底按钮打开语言选择")
            except Exception:
                pass

        if not clicked:
            return True, "未找到编辑语言按钮，跳过"

        await asyncio.sleep(2)

        # 4. 在对话框中查找并选择 English
        print("3. 选择 English...")
        dialog = page.locator('[role="dialog"]')
        if await dialog.count() == 0:
            return False, "未找到语言选择对话框"

        listbox = dialog.locator('[role="listbox"]')
        options = await listbox.locator('[role="option"]').all()

        # 查找 English 选项
        english_found = False
        for opt in options:
            try:
                text = await opt.text_content()
                if text and 'English' in text:
                    await opt.scroll_into_view_if_needed()
                    await opt.click()
                    english_found = True
                    print(f"   ✅ 选择了: {text}")
                    break
            except:
                continue

        if not english_found:
            # 尝试在对话框内搜索 English
            search_selectors = [
                'input[type="text"]',
                'input[aria-label*="Search"]',
                'input[placeholder*="Search"]',
                'input[aria-label*="搜索"]',
                'input[placeholder*="搜索"]',
            ]
            for selector in search_selectors:
                try:
                    inp = dialog.locator(selector).first
                    if await inp.count() > 0 and await inp.is_visible():
                        await inp.fill("English")
                        await asyncio.sleep(1)
                        options = await dialog.locator('[role="option"]').all()
                        for opt in options:
                            try:
                                text = await opt.text_content()
                                if text and 'English' in text:
                                    await opt.scroll_into_view_if_needed()
                                    await opt.click()
                                    english_found = True
                                    print(f"   ✅ 选择了: {text}")
                                    break
                            except Exception:
                                continue
                    if english_found:
                        break
                except Exception:
                    continue

        if not english_found:
            return True, "未找到 English 选项，可能已是英文或列表未加载，跳过"

        await asyncio.sleep(1)

        # 5. 选择地区变体 (United States)
        print("4. 选择 United States...")
        # 刷新选项列表（可能已更新为地区列表）
        options = await listbox.locator('[role="option"]').all()

        us_found = False
        for opt in options:
            try:
                text = await opt.text_content()
                if text and 'United States' in text:
                    await opt.click()
                    us_found = True
                    print(f"   ✅ 选择了: {text}")
                    break
            except:
                continue

        if not us_found:
            print("   ⚠️ 未找到 United States，可能已自动选择")

        await asyncio.sleep(1)

        # 6. 点击保存按钮
        print("5. 点击保存...")
        save_selectors = [
            'button:has-text("Enregistrer")',  # 法语
            'button:has-text("Save")',          # 英语
            'button:has-text("Speichern")',    # 德语
            'button:has-text("Guardar")',      # 西班牙语
            'button:has-text("保存")',          # 中文
        ]

        saved = False
        for selector in save_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click(timeout=5000)
                    saved = True
                    print("   ✅ 已点击保存")
                    break
            except:
                continue

        if not saved:
            # 有些版本会自动保存，无需显式按钮
            try:
                await page.goto('https://myaccount.google.com/language?hl=en&pli=1', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ""
            if _is_us_language_text(body_text):
                return True, "语言已是 English (United States)"
            return True, "未找到保存按钮，可能已自动保存，请手动确认"

        await asyncio.sleep(3)

        # 7. 验证设置
        print("6. 验证语言设置...")
        await page.goto('https://myaccount.google.com/language', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        add_en = await page.locator('button:has-text("Add a language"), button:has-text("Add another language")').count()
        if add_en > 0:
            print("✅ 语言已成功设置为英文！")
            return True, "语言设置成功"
        else:
            print("⚠️ 语言设置可能未生效")
            return True, "语言设置已执行，请手动验证"

    except Exception as e:
        print(f"❌ 设置语言时出错: {e}")
        return False, f"设置语言失败: {e}"


async def set_language_for_browser(browser_id: str) -> tuple[bool, str]:
    """
    为指定浏览器窗口设置语言为英文

    Args:
        browser_id: 浏览器窗口 ID

    Returns:
        (success: bool, message: str)
    """
    print(f"正在打开浏览器: {browser_id}...")

    result = openBrowser(browser_id)
    if not result.get('success'):
        return False, f"打开浏览器失败: {result}"

    ws_endpoint = result['data']['ws']

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(ws_endpoint)
            context = browser.contexts[0]
            page = await context.new_page()

            success, message = await set_language_to_english(page)

            # 关闭设置页面
            await page.close()

            return success, message

        except Exception as e:
            return False, f"设置语言错误: {e}"


def set_language_sync(browser_id: str) -> tuple[bool, str]:
    """
    同步版本的语言设置函数，供 GUI 调用
    """
    return asyncio.run(set_language_for_browser(browser_id))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        browser_id = sys.argv[1]
    else:
        # 默认测试用的浏览器 ID
        browser_id = "65b33437b6834a2d8830400ab3fe7695"

    print(f"设置浏览器 {browser_id} 的语言为英文...")
    print("=" * 50)

    success, message = asyncio.run(set_language_for_browser(browser_id))

    print("=" * 50)
    print(f"结果: {message}")
