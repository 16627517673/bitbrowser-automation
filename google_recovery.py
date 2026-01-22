"""
Google 登录时的辅助邮箱验证处理
"""
import asyncio
from typing import Optional, Callable

from playwright.async_api import Page


async def _click_action_button(page: Page, keywords: list[str], log_callback: Optional[Callable] = None) -> bool:
    selectors_by_keyword = {}
    for keyword in keywords:
        selectors_by_keyword[keyword] = [
            f'button:has-text("{keyword}")',
            f'[role="button"]:has-text("{keyword}")',
            f'a:has-text("{keyword}")',
            f'span:has-text("{keyword}")',
        ]

    search_scopes = []
    try:
        dialog = await page.query_selector('[role="dialog"]')
        if dialog and await dialog.is_visible():
            search_scopes.append(dialog)
    except Exception:
        pass
    search_scopes.append(page)

    for keyword, selectors in selectors_by_keyword.items():
        for scope in search_scopes:
            for selector in selectors:
                try:
                    btn = await scope.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click(force=True)
                        if log_callback:
                            log_callback(f"点击: {keyword}")
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue
        try:
            role_btn = page.get_by_role("button", name=keyword)
            if await role_btn.count() > 0 and await role_btn.first.is_visible():
                await role_btn.first.click(force=True)
                if log_callback:
                    log_callback(f"点击: {keyword}")
                await asyncio.sleep(2)
                return True
        except Exception:
            pass
    return False

async def detect_manual_verification(page: Page) -> bool:
    """检测是否出现需要人工操作的人机验证/验证码页面"""
    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""

    patterns = [
        "Confirm you're not a robot",
        "Confirm you’re not a robot",
        "I'm not a robot",
        "reCAPTCHA",
        "captcha",
        "不是机器人",
        "人机验证",
        "验证您不是机器人",
    ]
    if any(p.lower() in text.lower() for p in patterns):
        return True

    try:
        loc = page.locator('iframe[src*="recaptcha"], iframe[title*="recaptcha"], [title*="reCAPTCHA"]')
        if await loc.count() > 0:
            return True
    except Exception:
        pass

    return False

async def handle_recovery_email_challenge(
    page: Page,
    backup_email: str,
    log_callback: Optional[Callable] = None,
) -> bool:
    """
    处理登录验证页面：优先选择辅助邮箱验证
    """
    if not backup_email:
        return False

    markers = [
        "Verify it’s you",
        "Verify it's you",
        "Verify your identity",
        "Choose a way to sign in",
        "Try another way",
        "Confirm your recovery email",
        "Confirm your backup email",
        "确认您的辅助邮箱",
        "验证身份",
    ]
    try:
        content = await page.content()
    except Exception:
        content = ""

    if await detect_manual_verification(page):
        if log_callback:
            log_callback("检测到人机验证，需人工完成")
        return False

    if not any(m in content for m in markers) and "challenge" not in page.url.lower():
        return False

    if log_callback:
        log_callback("检测到验证身份页面，尝试使用辅助邮箱...")

    await _click_action_button(page, ["Try another way", "试试其他方式"], log_callback)

    option_keywords = [
        "Confirm your recovery email",
        "Confirm your backup email",
        "Confirm your recovery email address",
        "确认您的辅助邮箱",
        "确认辅助邮箱",
    ]

    clicked = False
    for keyword in option_keywords:
        selectors = [
            f'button:has-text("{keyword}")',
            f'[role="button"]:has-text("{keyword}")',
            f'li:has-text("{keyword}")',
            f'div:has-text("{keyword}")',
            f'span:has-text("{keyword}")',
        ]
        for selector in selectors:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    box = await el.bounding_box()
                    if box and box["height"] > 160:
                        continue
                    await el.click(force=True)
                    clicked = True
                    break
            except Exception:
                continue
        if clicked:
            break

    if not clicked:
        try:
            options = await page.query_selector_all('[data-challengetype], [role="button"], [role="listitem"]')
            visible_options = []
            for opt in options:
                try:
                    if await opt.is_visible():
                        text = (await opt.inner_text()).strip()
                        if text:
                            visible_options.append(opt)
                except Exception:
                    continue
            if len(visible_options) >= 3:
                await visible_options[2].click(force=True)
                clicked = True
        except Exception:
            pass

    if not clicked:
        return False

    await asyncio.sleep(1)

    email_input_selectors = [
        'input[type="email"]',
        'input[name*="knowledgePreregisteredEmailResponse"]',
        'input[name*="email"]',
        'input[type="text"]',
    ]
    email_input = None
    for selector in email_input_selectors:
        try:
            inp = await page.query_selector(selector)
            if inp and await inp.is_visible():
                email_input = inp
                break
        except Exception:
            continue

    if email_input:
        await email_input.fill(backup_email)
        await asyncio.sleep(0.5)

    await _click_action_button(page, ["Next", "Continue", "Confirm", "Submit", "下一步", "继续", "确认"], log_callback)
    await asyncio.sleep(2)
    return True
