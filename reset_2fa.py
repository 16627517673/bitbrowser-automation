"""
Google 2FA 重置功能
自动删除现有的 Authenticator App 并添加新的，获取新的密钥
"""
import asyncio
import os
import sys
import re
import time
from datetime import datetime
from typing import Optional, Tuple, Callable

import pyotp
import requests
from playwright.async_api import async_playwright, Playwright, Page, Locator

from bit_api import openBrowser, closeBrowser
from create_window import get_browser_info, get_browser_list
from set_language import set_language_to_english

# 比特浏览器 API
BIT_API_URL = "http://127.0.0.1:54345"
BIT_HEADERS = {'Content-Type': 'application/json'}
# 禁用代理，避免本地 API 请求被代理拦截
NO_PROXY = {'http': None, 'https': None}

# Google 两步验证页面 URL
TWO_STEP_VERIFICATION_URL = "https://myaccount.google.com/signinoptions/two-step-verification?hl=en&pli=1"


def get_base_path() -> str:
    """获取基础路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


async def _safe_screenshot(page: Page, path: str, log_callback: Optional[Callable] = None) -> None:
    """截图失败不阻塞流程"""
    try:
        await page.screenshot(path=path, timeout=5000, animations="disabled")
        print(f"[调试] 已截图: {path}")
    except Exception as e:
        msg = f"[警告] 截图失败: {path} ({e})"
        if log_callback:
            log_callback(msg)
        print(msg)


def update_browser_2fa(browser_id: str, new_secret: str,
                       log_callback: Optional[Callable] = None) -> bool:
    """
    更新比特浏览器配置中的 2FA 密钥

    Args:
        browser_id: 浏览器窗口 ID
        new_secret: 新的 2FA 密钥

    Returns:
        是否更新成功
    """
    try:
        # 获取当前浏览器配置
        browser_info = get_browser_info(browser_id)
        if not browser_info:
            print(f"[错误] 找不到浏览器: {browser_id}")
            return False

        # 更新 remark 中的 2FA 密钥
        remark = browser_info.get('remark', '') or ''
        parts = remark.split('----') if remark else []
        if len(parts) < 3:
            while len(parts) < 3:
                parts.append('')
        if len(parts) >= 4:
            parts[3] = new_secret
        else:
            parts.append(new_secret)
        new_remark = '----'.join(parts)

        # 更新配置
        update_data = {
            'ids': [browser_id],
            'remark': new_remark,
            'faSecretKey': new_secret
        }

        def _log(msg: str) -> None:
            if log_callback:
                log_callback(msg)
            print(msg)

        res = requests.post(
            f"{BIT_API_URL}/browser/update/partial",
            json=update_data,
            headers=BIT_HEADERS,
            timeout=10,
            proxies=NO_PROXY
        ).json()

        update_ok = res.get('success') or res.get('code') == 0
        if not update_ok:
            _log(f"[警告] 备注+密钥更新失败，准备重试: {res}")

        verify_info = get_browser_info(browser_id) or {}
        retry_key_ok = False
        if verify_info.get('faSecretKey') != new_secret:
            retry_data = {'ids': [browser_id], 'faSecretKey': new_secret}
            try:
                retry_res = requests.post(
                    f"{BIT_API_URL}/browser/update/partial",
                    json=retry_data,
                    headers=BIT_HEADERS,
                    timeout=10,
                    proxies=NO_PROXY
                ).json()
                _log(f"[信息] 重试更新密钥: {retry_res}")
                retry_key_ok = retry_res.get('success') or retry_res.get('code') == 0
            except Exception as e:
                _log(f"[警告] 重试更新密钥异常: {e}")

        verify_info = get_browser_info(browser_id) or {}
        retry_remark_ok = False
        if verify_info.get('remark') != new_remark:
            retry_data = {'ids': [browser_id], 'remark': new_remark}
            try:
                retry_res = requests.post(
                    f"{BIT_API_URL}/browser/update/partial",
                    json=retry_data,
                    headers=BIT_HEADERS,
                    timeout=10,
                    proxies=NO_PROXY
                ).json()
                _log(f"[信息] 重试更新备注: {retry_res}")
                retry_remark_ok = retry_res.get('success') or retry_res.get('code') == 0
            except Exception as e:
                _log(f"[警告] 重试更新备注异常: {e}")

        verify_info = get_browser_info(browser_id) or {}
        fa_visible = 'faSecretKey' in verify_info and verify_info.get('faSecretKey') is not None
        remark_visible = 'remark' in verify_info and verify_info.get('remark') is not None
        if (not fa_visible or verify_info.get('faSecretKey') == new_secret) and (
            not remark_visible or verify_info.get('remark') == new_remark
        ) and (update_ok or retry_key_ok or retry_remark_ok):
            _log("[成功] 已更新浏览器 2FA 配置")
            return True

        if update_ok or retry_key_ok or retry_remark_ok:
            _log("[警告] 更新请求成功，但校验字段不可用/未刷新")
            return True

        _log("[错误] 更新浏览器 2FA 配置失败（校验未通过）")
        return False

    except Exception as e:
        print(f"[错误] 更新浏览器配置异常: {e}")
        return False


async def _click_cant_scan(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """点击 Can't scan it? 进入文本密钥视图"""
    keywords = [
        "Can't scan it?",
        "Can't scan it",
        "Can't scan",
        "Can\u2019t scan it?",
        "Can\u2019t scan it",
        "Can\u2019t scan",
        "Cannot scan",
        "Enter a setup key",
        "Use a setup key",
        "手动输入",
        "无法扫描",
    ]

    scopes = []
    try:
        dialog = await page.query_selector('[role="dialog"]')
        if dialog and await dialog.is_visible():
            scopes.append(dialog)
    except Exception:
        pass
    scopes.append(page)

    for keyword in keywords:
        for scope in scopes:
            try:
                loc = scope.get_by_text(keyword, exact=False).first
                if await loc.count() == 0:
                    continue
                if not await loc.is_visible():
                    continue
                try:
                    await loc.click(force=True)
                except Exception:
                    target = await loc.evaluate_handle(
                        """
                        el => {
                          let node = el;
                          while (node && node !== document.body) {
                            const role = node.getAttribute && node.getAttribute('role');
                            const jsaction = node.getAttribute && node.getAttribute('jsaction');
                            if (node.tagName === 'BUTTON' || node.tagName === 'A' || role === 'button') {
                              return node;
                            }
                            if (jsaction && jsaction.includes('click')) {
                              return node;
                            }
                            node = node.parentElement;
                          }
                          return el;
                        }
                        """
                    )
                    await target.as_element().click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Can't scan it?")
                print("[信息] 已点击 Can't scan it?")
                return True
            except Exception:
                continue

    try:
        cant_scan_loc = page.locator("text=/Can[\\u2019']t scan it\\?/i").first
        if await cant_scan_loc.count() > 0 and await cant_scan_loc.first.is_visible():
            await cant_scan_loc.first.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Can't scan it?")
            print("[信息] 已点击 Can't scan it?")
            return True
    except Exception:
        pass

    return False


def _extract_secret_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r'[A-Za-z2-7]{4}(?:\s+[A-Za-z2-7]{4}){3,7}',
        r'[A-Za-z2-7]{16,32}',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            clean = re.sub(r'[\s-]', '', match.strip())
            if 16 <= len(clean) <= 32 and re.match(r'^[A-Za-z2-7]+$', clean):
                return clean
    return None


def _extract_secret_from_block(text: str) -> Optional[str]:
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    keyword_re = re.compile(r'(setup key|secret key|key|secret|enter key|setup)', re.I)
    candidates = []
    for idx, line in enumerate(lines):
        if keyword_re.search(line):
            candidates.append(line)
            if idx + 1 < len(lines):
                candidates.append(lines[idx + 1])
            if idx + 2 < len(lines):
                candidates.append(lines[idx + 2])
    seen = set()
    for line in candidates:
        if line in seen:
            continue
        seen.add(line)
        secret = _extract_secret_from_text(line)
        if secret:
            return secret
    cleaned = re.sub(r'\\b\\d+px\\b', ' ', text, flags=re.I)
    return _extract_secret_from_text(cleaned)


async def _find_code_input(page: Page) -> Optional[Locator]:
    selectors = [
        'input[placeholder*="Code"]',
        'input[placeholder*="code"]',
        'input[aria-label*="Code"]',
        'input[aria-label*="code"]',
        'input[type="tel"]',
        'input[inputmode="numeric"]',
        'input[autocomplete="one-time-code"]',
        'input[name*="code"]',
        'input[name*="otp"]',
        'input[type="text"][maxlength="6"]',
    ]
    dialog_loc = None
    try:
        dialog_loc = page.locator('[role="dialog"]').first
        if await dialog_loc.count() == 0 or not await dialog_loc.is_visible():
            dialog_loc = None
    except Exception:
        dialog_loc = None

    scopes = [dialog_loc, page] if dialog_loc else [page]
    for scope in scopes:
        try:
            placeholder_loc = scope.get_by_placeholder(re.compile("code", re.I)).first
            if await placeholder_loc.count() > 0 and await placeholder_loc.is_visible():
                return placeholder_loc
        except Exception:
            pass
        try:
            label_loc = scope.get_by_label(re.compile("code|验证码", re.I)).first
            if await label_loc.count() > 0 and await label_loc.is_visible():
                return label_loc
        except Exception:
            pass
        for selector in selectors:
            try:
                loc = scope.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        if scope is dialog_loc:
            try:
                loc = scope.locator('input[type="text"]').first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                pass
    for frame in page.frames:
        try:
            placeholder_loc = frame.get_by_placeholder(re.compile("code", re.I)).first
            if await placeholder_loc.count() > 0 and await placeholder_loc.is_visible():
                return placeholder_loc
        except Exception:
            pass
        try:
            label_loc = frame.get_by_label(re.compile("code|验证码", re.I)).first
            if await label_loc.count() > 0 and await label_loc.is_visible():
                return label_loc
        except Exception:
            pass
        for selector in selectors:
            try:
                loc = frame.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
    return None


async def _click_action_button(page: Page, keywords: list[str],
                               log_callback: Optional[Callable] = None) -> bool:
    search_scopes = []
    try:
        dialog = page.locator('[role="dialog"]')
        if await dialog.count() > 0 and await dialog.first.is_visible():
            search_scopes.append(dialog.first)
    except Exception:
        pass
    search_scopes.append(page)

    for keyword in keywords:
        for scope in search_scopes:
            try:
                loc = scope.locator(
                    f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}")'
                ).first
                if await loc.count() > 0 and await loc.is_visible():
                    try:
                        await loc.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await loc.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback(f"已点击 {keyword}")
                    print(f"[信息] 点击: {keyword}")
                    return True
            except Exception:
                continue
        try:
            role_btn = page.get_by_role("button", name=re.compile(keyword, re.I)).first
            if await role_btn.count() > 0 and await role_btn.is_visible():
                try:
                    await role_btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                await role_btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback(f"已点击 {keyword}")
                print(f"[信息] 点击: {keyword}")
                return True
        except Exception:
            pass
        for frame in page.frames:
            try:
                loc = frame.locator(
                    f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}")'
                ).first
                if await loc.count() > 0 and await loc.is_visible():
                    try:
                        await loc.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await loc.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback(f"已点击 {keyword}")
                    print(f"[信息] 点击: {keyword}")
                    return True
            except Exception:
                continue
            try:
                role_btn = frame.get_by_role("button", name=re.compile(keyword, re.I)).first
                if await role_btn.count() > 0 and await role_btn.is_visible():
                    try:
                        await role_btn.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await role_btn.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback(f"已点击 {keyword}")
                    print(f"[信息] 点击: {keyword}")
                    return True
            except Exception:
                pass
    return False


async def _is_turn_on_visible(page: Page) -> bool:
    selectors = [
        'button:has-text("Turn on")',
        'button:has-text("Turn on 2-Step")',
        '[role="button"]:has-text("Turn on")',
        '[role="button"]:has-text("Turn on 2-Step")',
        'text=/Turn on 2.?Step/i',
        'text=/Turn on 2.?Step Verification/i',
        'h2:has-text("Turn on 2-Step Verification")',
        'h2:has-text("Turn on 2-Step")',
        'button[aria-label*="Turn on 2-Step Verification"]',
        'button[aria-label*="Turn on 2-Step"]',
        'button[aria-label*="Turn on"]',
        # 西班牙语
        'button:has-text("Activar")',
        '[role="button"]:has-text("Activar")',
        'text=/Activar la verificación en dos pasos/i',
        # 荷兰语
        'button:has-text("Tweestapsverificatie aanzetten")',
        '[role="button"]:has-text("Tweestapsverificatie aanzetten")',
        'button:has-text("Aanzetten")',
        '[role="button"]:has-text("Aanzetten")',
        'button:has-text("Inschakelen")',
        '[role="button"]:has-text("Inschakelen")',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
    try:
        role_btn = page.get_by_role(
            "button",
            name=re.compile("Turn on 2.?Step|Turn on|Activar|Aanzetten|Inschakelen", re.I),
        )
        if await role_btn.count() > 0 and await role_btn.first.is_visible():
            return True
    except Exception:
        pass
    try:
        heading = page.get_by_role("heading", name=re.compile("Turn on 2.?Step", re.I))
        if await heading.count() > 0 and await heading.first.is_visible():
            return True
    except Exception:
        pass
    return False


async def _has_2sv_success_text(page: Page) -> bool:
    selectors = [
        "text=/You're now protected with 2-Step Verification/i",
        "text=/You’re now protected with 2-Step Verification/i",
        'text=/2-Step Verification is on/i',
        'text=/2-Step Verification is turned on/i',
        'text=/Tweestapsverificatie/i',
        'text=/verificación en dos pasos/i',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


async def _click_done_if_present(page: Page, log_callback: Optional[Callable] = None) -> bool:
    if not await _has_2sv_success_text(page):
        return False
    done_keywords = ["Done", "Klaar", "Listo", "Fatto", "OK"]
    for keyword in done_keywords:
        selectors = [
            f'button:has-text("{keyword}")',
            f'[role="button"]:has-text("{keyword}")',
        ]
        for selector in selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback(f"已点击 {keyword}")
                    print(f"[信息] 点击: {keyword}")
                    return True
            except Exception:
                continue
    return False


async def _click_turn_on(page: Page, log_callback: Optional[Callable] = None) -> bool:
    selectors = [
        'button:has-text("Turn on 2-Step Verification")',
        'button:has-text("Turn on 2-Step")',
        'button:has-text("Turn on")',
        '[role="button"]:has-text("Turn on 2-Step Verification")',
        '[role="button"]:has-text("Turn on 2-Step")',
        '[role="button"]:has-text("Turn on")',
        'button[aria-label*="Turn on 2-Step Verification"]',
        'button[aria-label*="Turn on 2-Step"]',
        'button[aria-label*="Turn on"]',
        # 西班牙语
        'button:has-text("Activar la verificación en dos pasos")',
        'button:has-text("Activar")',
        '[role="button"]:has-text("Activar la verificación en dos pasos")',
        '[role="button"]:has-text("Activar")',
        # 荷兰语
        'button:has-text("Tweestapsverificatie aanzetten")',
        '[role="button"]:has-text("Tweestapsverificatie aanzetten")',
        'button:has-text("Aanzetten")',
        '[role="button"]:has-text("Aanzetten")',
        'button:has-text("Inschakelen")',
        '[role="button"]:has-text("Inschakelen")',
    ]
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                try:
                    await btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    await btn.click(force=True)
                except Exception:
                    try:
                        wrapper = await btn.evaluate_handle(
                            "el => el.closest('div[jsaction*=\"click:cOuCgd\"]') || el"
                        )
                        await wrapper.as_element().click(force=True)
                    except Exception:
                        await page.evaluate("el => el.click()", btn)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Turn on")
                print("[信息] 点击 Turn on")
                return True
        except Exception:
            continue
    try:
        role_btn = page.get_by_role(
            "button",
            name=re.compile("Turn on 2.?Step|Turn on|Activar|Aanzetten|Inschakelen", re.I),
        )
        if await role_btn.count() > 0 and await role_btn.first.is_visible():
            await role_btn.first.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Turn on")
            print("[信息] 点击 Turn on")
            return True
    except Exception:
        pass
    try:
        if await _click_action_button(
            page,
            ["Turn on 2-Step Verification", "Turn on", "Activar"],
            log_callback,
        ):
            return True
    except Exception:
        pass
    try:
        header = page.get_by_role("heading", name=re.compile("Turn on 2.?Step", re.I)).first
        if await header.count() > 0 and await header.is_visible():
            container = await header.evaluate_handle(
                """
                el => el.closest('section, div') || el.parentElement || el
                """
            )
            if container and container.as_element():
                btn = await container.as_element().query_selector('button')
                if btn and await btn.is_visible():
                    await btn.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback("已点击 Turn on")
                    print("[信息] 点击 Turn on")
                    return True
    except Exception:
        pass
    try:
        text_btn = page.locator('button, [role="button"], a').filter(
            has_text=re.compile("Turn on 2.?Step", re.I)
        ).first
        if await text_btn.count() > 0 and await text_btn.is_visible():
            await text_btn.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Turn on")
            print("[信息] 点击 Turn on")
            return True
    except Exception:
        pass
    return False


async def _click_skip_if_present(page: Page, log_callback: Optional[Callable] = None) -> bool:
    selectors = [
        'button:has-text("Skip")',
        '[role="button"]:has-text("Skip")',
        'text=Skip',
        # 中文
        'button:has-text("跳过")',
        '[role="button"]:has-text("跳过")',
        'text=跳过',
        # 西班牙语
        'button:has-text("Omitir")',
        '[role="button"]:has-text("Omitir")',
        # 荷兰语
        'button:has-text("Overslaan")',
        '[role="button"]:has-text("Overslaan")',
    ]
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Skip")
                print("[信息] 点击 Skip")
                return True
        except Exception:
            continue
    try:
        role_btn = page.get_by_role("button", name=re.compile("Skip|Omitir|Overslaan|跳过", re.I))
        if await role_btn.count() > 0 and await role_btn.first.is_visible():
            await role_btn.first.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Skip")
            print("[信息] 点击 Skip")
            return True
    except Exception:
        pass
    return False


async def _handle_add_phone_dialog(page: Page, log_callback: Optional[Callable] = None) -> bool:
    skip_pattern = re.compile("Skip|Omitir|Overslaan|Not now|Later|跳过", re.I)
    dialog_pattern = re.compile("phone number|2-Step Verification|2-Step", re.I)
    for _ in range(8):
        try:
            dialog = page.locator('[role="dialog"], [role="alertdialog"]').filter(has_text=dialog_pattern)
            if await dialog.count() == 0 or not await dialog.first.is_visible():
                return False
            btn = dialog.get_by_role("button", name=skip_pattern).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Skip 跳过添加电话号码")
                print("[信息] 已点击 Skip 跳过添加电话号码")
                try:
                    await dialog.first.wait_for(state="hidden", timeout=3000)
                except Exception:
                    pass
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


async def _dismiss_add_second_steps_dialog(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """处理“Add second steps to your account”阻塞弹窗"""
    try:
        text_loc = page.locator('text=/Add second steps to your account/i')
        if await text_loc.count() == 0 or not await text_loc.first.is_visible():
            text_loc = page.locator('text=/add second steps/i')
            if await text_loc.count() == 0 or not await text_loc.first.is_visible():
                return False
    except Exception:
        return False

    btn_selectors = [
        'button:has-text("Go back")',
        'button:has-text("Back")',
        '[role="button"]:has-text("Go back")',
        '[role="button"]:has-text("Back")',
    ]
    for selector in btn_selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Go back 关闭弹窗")
                print("[信息] 点击 Go back")
                return True
        except Exception:
            continue
    try:
        role_btn = page.get_by_role("button", name=re.compile("Go back|Back", re.I)).first
        if await role_btn.count() > 0 and await role_btn.is_visible():
            await role_btn.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Go back 关闭弹窗")
            print("[信息] 点击 Go back")
            return True
    except Exception:
        pass
    return False


async def _ensure_two_step_page(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """确保当前位于两步验证页面"""
    def _on_two_step_page(url: str) -> bool:
        lowered = (url or "").lower()
        return "signinoptions" in lowered or "two-step-verification" in lowered

    if _on_two_step_page(page.url):
        return True

    for _ in range(2):
        try:
            await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception:
            pass

        if _on_two_step_page(page.url):
            return True

        try:
            await page.goto("https://myaccount.google.com/security?hl=en&pli=1", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception:
            pass

        try:
            link = page.locator('a[href*="signinoptions/twosv"], a[href*="two-step-verification"]').first
            if await link.count() > 0 and await link.is_visible():
                await link.scroll_into_view_if_needed()
                await link.click(force=True)
                await asyncio.sleep(2)
        except Exception:
            pass

        if _on_two_step_page(page.url):
            return True

    return _on_two_step_page(page.url)


async def _ensure_2sv_enabled(page: Page, secret: str, password: str,
                              log_callback: Optional[Callable] = None) -> Tuple[bool, str]:
    if await _has_2sv_success_text(page):
        await _click_done_if_present(page, log_callback)
        return True, "2FA 已开启"
    await _handle_add_phone_dialog(page, log_callback)
    try:
        await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
    except Exception:
        pass

    for _ in range(3):
        if await _has_2sv_success_text(page):
            await _click_done_if_present(page, log_callback)
            return True, "2FA 已开启"
        await _handle_add_phone_dialog(page, log_callback)
        if not await _is_turn_on_visible(page):
            if await _click_done_if_present(page, log_callback):
                return True, "2FA 已开启"
            return True, "未检测到 Turn on"

        clicked = await _click_turn_on(page, log_callback)
        if not clicked:
            await asyncio.sleep(2)
            if not await _is_turn_on_visible(page):
                if await _click_done_if_present(page, log_callback):
                    return True, "2FA 已开启"
                return True, "未检测到 Turn on"
            return False, "点击 Turn on 失败"

        dismissed = await _dismiss_add_second_steps_dialog(page, log_callback)
        if dismissed:
            await asyncio.sleep(1)
            continue

        for _ in range(3):
            await _click_skip_if_present(page, log_callback)
            await asyncio.sleep(1)

        await _handle_add_phone_dialog(page, log_callback)
        await handle_password_verification(page, password, log_callback)
        await asyncio.sleep(2)

        code_input = await _find_code_input(page)
        if code_input:
            if not secret:
                return False, "需要验证码但缺少密钥"
            totp = pyotp.TOTP(secret)
            code = totp.now()
            await code_input.fill(code)
            await asyncio.sleep(1)
            await _click_action_button(
                page,
                ["Verify", "Next", "Confirm", "Done", "Turn on", "确认", "验证", "完成", "开启", "Aanzetten", "Inschakelen"],
                log_callback,
            )
            await asyncio.sleep(2)

        for _ in range(3):
            await _click_skip_if_present(page, log_callback)
            await asyncio.sleep(1)

        await _handle_add_phone_dialog(page, log_callback)
        if await _click_done_if_present(page, log_callback):
            return True, "2FA 已开启"

        if not await _is_turn_on_visible(page):
            return True, "2FA 已开启"

        try:
            await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception:
            pass

    if await _is_turn_on_visible(page):
        return False, "2FA 未开启（仍显示 Turn on）"
    return True, "2FA 已开启"


def save_secret_to_file(email: str, new_secret: str, browser_id: str = "") -> None:
    """
    保存新密钥到文件

    Args:
        email: 邮箱地址
        new_secret: 新的 2FA 密钥
        browser_id: 浏览器 ID（可选）
    """
    file_path = os.path.join(get_base_path(), "new_2fa_secrets.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = f"{timestamp} | {email} | {new_secret}"
    if browser_id:
        line += f" | {browser_id}"
    line += "\n"

    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(line)
        print(f"[成功] 已保存到文件: {file_path}")
    except Exception as e:
        print(f"[错误] 保存文件失败: {e}")


async def handle_password_verification(page: Page, password: str, log_callback: Optional[Callable] = None) -> bool:
    """
    处理密码验证页面

    Args:
        page: Playwright 页面对象
        password: 账号密码
        log_callback: 日志回调函数

    Returns:
        是否验证成功
    """
    try:
        # 检查是否需要输入密码
        password_input = await page.query_selector('input[type="password"]')
        if password_input:
            if log_callback:
                log_callback("需要输入密码验证...")
            print("[信息] 检测到密码验证页面")

            await password_input.fill(password)
            await asyncio.sleep(0.5)

            # 点击下一步按钮
            next_button = await page.query_selector('button[type="submit"], #passwordNext button')
            if next_button:
                await next_button.click()
                await asyncio.sleep(2)
            else:
                # 尝试按 Enter
                await password_input.press('Enter')
                await asyncio.sleep(2)

            return True
    except Exception as e:
        print(f"[警告] 密码验证处理异常: {e}")

    return False


async def handle_recovery_challenge(page: Page, backup_email: str, log_callback: Optional[Callable] = None) -> bool:
    """
    处理账号恢复验证（使用备用邮箱）

    Args:
        page: Playwright 页面对象
        backup_email: 备用邮箱地址
        log_callback: 日志回调函数

    Returns:
        是否成功通过验证
    """
    try:
        await asyncio.sleep(1)

        # 检查是否需要身份验证（多种检测方式）
        page_text = await page.content()
        needs_recovery = (
            'recovery' in page.url or
            'Confirm' in page_text or
            'verify' in page_text.lower() or
            'Try another way' in page_text
        )

        # 检查是否有恢复链接
        recovery_link = await page.query_selector('a[href*="recovery"]')
        if recovery_link:
            needs_recovery = True

        if not needs_recovery:
            return False

        if log_callback:
            log_callback("检测到账号恢复验证...")

        # 先点击恢复链接进入恢复流程
        if recovery_link:
            print("[信息] 点击恢复链接...")
            await recovery_link.click()
            await asyncio.sleep(3)

        # 查找并点击备用邮箱选项（通常显示为部分隐藏的邮箱）
        # 备用邮箱格式通常是 V....0@hightl.site
        email_prefix = backup_email[:1]  # 第一个字符
        email_options = await page.query_selector_all(f'div:has-text("{email_prefix}"), li:has-text("{email_prefix}"), [data-challengetype]')

        for option in email_options:
            try:
                text = await option.inner_text()
                if '@' in text and email_prefix.lower() in text.lower():
                    print(f"[信息] 点击备用邮箱选项: {text}")
                    await option.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        # 查找邮箱输入框并填写
        email_input = await page.query_selector('input[type="email"], input[name="knowledgePreregisteredEmailResponse"], input[type="text"]')
        if email_input:
            if log_callback:
                log_callback(f"正在输入备用邮箱: {backup_email}")
            await email_input.fill(backup_email)
            await asyncio.sleep(0.5)

            # 点击下一步
            next_btn = await page.query_selector('button:has-text("Next"), button:has-text("下一步"), button[type="submit"]')
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(3)
                print("[成功] 已提交备用邮箱验证")

                # 截图调试
                await _safe_screenshot(page, "debug_after_recovery.png", log_callback)
                return True

        return False

    except Exception as e:
        print(f"[错误] 账号恢复验证失败: {e}")
        return False


async def handle_2fa_challenge(page: Page, secret: str, log_callback: Optional[Callable] = None) -> bool:
    """
    处理 2FA 验证挑战（输入现有的验证码）

    Args:
        page: Playwright 页面对象
        secret: 现有的 2FA 密钥
        log_callback: 日志回调函数

    Returns:
        是否成功通过验证
    """
    try:
        # 检查是否在验证页面
        code_input_selectors = [
            'input[name="totpPin"]',
            'input[type="tel"]',
            'input[aria-label*="code"]',
            'input[aria-label*="Enter code"]',
            'input[placeholder*="code"]',
        ]

        code_input = None
        for selector in code_input_selectors:
            code_input = await page.query_selector(selector)
            if code_input:
                break

        if not code_input:
            # 可能不需要验证
            print("[信息] 未检测到验证码输入框")
            return True

        if log_callback:
            log_callback("正在输入现有 2FA 验证码...")

        # 生成验证码
        clean_secret = secret.replace(' ', '').strip()
        totp = pyotp.TOTP(clean_secret)
        code = totp.now()
        print(f"[信息] 生成验证码: {code}")

        # 输入验证码
        await code_input.fill(code)
        await asyncio.sleep(1)

        # 点击 Next 按钮
        next_button = await page.query_selector('button:has-text("Next"), button:has-text("下一步"), #totpNext button')
        if next_button:
            await next_button.click()
            print("[信息] 已提交验证码")
            await asyncio.sleep(3)
            return True
        else:
            # 尝试按 Enter
            await code_input.press('Enter')
            await asyncio.sleep(3)
            return True

    except Exception as e:
        print(f"[错误] 处理 2FA 验证失败: {e}")
        return False


async def navigate_to_authenticator_settings(page: Page, secret: str = "", log_callback: Optional[Callable] = None) -> bool:
    """
    导航到 Authenticator 设置页面

    Google 的 2FA 页面结构：先选择 Authenticator，点击 Next，可能需要验证，才能进入管理页面
    """
    try:
        await asyncio.sleep(2)

        # 截图调试
        await _safe_screenshot(page, "debug_2fa_page.png", log_callback)
        print("[调试] 已截图: debug_2fa_page.png")

        # 查找并点击 Authenticator 选项
        authenticator_keywords = [
            "Google Authenticator",
            "Authenticator app",
            "Authenticator 应用",
        ]

        found = False
        for keyword in authenticator_keywords:
            elements = await page.query_selector_all(f'text="{keyword}"')
            if elements:
                # 找到父容器并点击（整行可点击）
                element = elements[0]
                parent = await element.evaluate_handle('el => el.closest("[role=radio], [role=checkbox], li, label, div[jscontroller]")')
                if parent:
                    await parent.as_element().click()
                else:
                    await element.click()
                print(f"[信息] 已选择: {keyword}")
                found = True
                await asyncio.sleep(1)
                break

        if not found:
            print("[警告] 未找到 Authenticator 选项")
            return False

        # 点击 Next 按钮
        next_button = await page.query_selector('button:has-text("Next"), button:has-text("下一步")')
        if next_button:
            await next_button.click()
            print("[信息] 已点击 Next 按钮")
            await asyncio.sleep(3)

            # 检查是否需要 2FA 验证
            if secret:
                await handle_2fa_challenge(page, secret, log_callback)

            await _safe_screenshot(page, "debug_after_next.png", log_callback)
            return True
        else:
            print("[警告] 未找到 Next 按钮")
            return False

    except Exception as e:
        print(f"[错误] 导航到 Authenticator 设置失败: {e}")
        return False


async def delete_existing_authenticator(page: Page, secret: str = "", log_callback: Optional[Callable] = None) -> bool:
    """
    删除现有的 Authenticator App

    Args:
        page: Playwright 页面对象
        secret: 现有的 2FA 密钥（用于验证）
        log_callback: 日志回调函数

    Returns:
        是否删除成功（或不存在）
    """
    if log_callback:
        log_callback("正在查找现有的 Authenticator...")

    try:
        # 先导航到 Authenticator 设置页面
        nav_success = await navigate_to_authenticator_settings(page, secret, log_callback)
        if not nav_success:
            print("[警告] 导航到 Authenticator 设置失败")

        await asyncio.sleep(2)
        await _safe_screenshot(page, "debug_2fa_settings.png", log_callback)
        print("[调试] 已截图: debug_2fa_settings.png")

        # 检查当前页面是否是 2FA 管理主页面（需要点击 Authenticator 链接进入详情）
        # 查找 Authenticator 详情链接
        auth_link = await page.query_selector('a[href*="authenticator"], a:has-text("Authenticator")')
        if auth_link:
            print("[信息] 找到 Authenticator 详情链接，正在点击...")
            await auth_link.click()
            await asyncio.sleep(3)
            await _safe_screenshot(page, "debug_auth_detail.png", log_callback)
            print("[调试] 已截图: debug_auth_detail.png")

        # 在 Authenticator 详情页查找删除按钮
        delete_selectors = [
            # 文字按钮
            'button:has-text("Remove")',
            'button:has-text("Delete")',
            'button:has-text("移除")',
            'button:has-text("删除")',
            '[role="button"]:has-text("Remove")',
            '[role="button"]:has-text("Delete")',
            # 链接形式
            'a:has-text("Remove")',
            'a:has-text("Delete")',
            # 图标按钮 - 通过 aria-label
            '[aria-label*="Remove"]',
            '[aria-label*="Delete"]',
            '[aria-label*="remove"]',
            '[aria-label*="delete"]',
            # 垃圾桶图标
            'button:has(svg[viewBox])',
            '[role="button"]:has(svg)',
        ]

        delete_button = None
        for selector in delete_selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    delete_button = elements[0]
                    print(f"[信息] 找到删除按钮: {selector}")
                    break
            except:
                continue

        if delete_button:
            if log_callback:
                log_callback("正在删除现有的 Authenticator...")
            await delete_button.click()
            await asyncio.sleep(2)

            await _safe_screenshot(page, "debug_2fa_after_delete_click.png", log_callback)

            # 确认删除对话框
            confirm_selectors = [
                'button:has-text("Remove")',
                'button:has-text("Delete")',
                'button:has-text("确认")',
                'button:has-text("移除")',
                '[role="alertdialog"] button',
                '[role="dialog"] button:last-child',
            ]

            for selector in confirm_selectors:
                try:
                    confirm_button = await page.query_selector(selector)
                    if confirm_button:
                        text = await confirm_button.inner_text()
                        if "cancel" not in text.lower() and "取消" not in text:
                            await confirm_button.click()
                            await asyncio.sleep(2)
                            print("[成功] 已删除现有的 Authenticator")
                            return True
                except:
                    continue

        # 调试：打印页面上所有按钮
        buttons = await page.query_selector_all('button, [role="button"], a')
        print(f"[调试] 页面上有 {len(buttons)} 个可点击元素")
        for i, btn in enumerate(buttons[:15]):
            try:
                text = await btn.inner_text()
                aria = await btn.get_attribute('aria-label')
                href = await btn.get_attribute('href')
                print(f"[调试] 元素 {i}: text='{text[:30] if text else ''}', aria='{aria}', href='{href}'")
            except:
                pass

        print("[警告] 未能找到删除按钮")
        return False

    except Exception as e:
        print(f"[错误] 删除 Authenticator 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def add_new_authenticator(page: Page, existing_secret: str = "", log_callback: Optional[Callable] = None) -> Optional[str]:
    """
    添加新的 Authenticator App 并获取密钥

    Args:
        page: Playwright 页面对象
        existing_secret: 现有的 2FA 密钥（用于验证）
        log_callback: 日志回调函数

    Returns:
        新的 2FA 密钥，失败返回 None
    """
    if log_callback:
        log_callback("正在添加新的 Authenticator...")

    try:
        # 等待页面稳定
        await asyncio.sleep(2)

        # 检查当前 URL，如果不在 2FA 页面则导航
        current_url = page.url
        if 'two-step-verification' not in current_url and 'twosv' not in current_url:
            try:
                await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until='domcontentloaded')
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[警告] 导航可能被重定向: {e}")
                await asyncio.sleep(3)

        # 处理可能的 2FA 验证
        if existing_secret:
            await handle_2fa_challenge(page, existing_secret, log_callback)
            await asyncio.sleep(2)

        await _safe_screenshot(page, "debug_before_add.png", log_callback)
        print("[调试] 已截图: debug_before_add.png")

        # 首先查找并点击 Authenticator 行（多语言支持）
        # 页面结构：div.iAwpk 包含 Authenticator 图标和文字，是可点击的整行
        authenticator_row_selectors = [
            # 通过文字内容查找整行
            'div.iAwpk:has-text("Authenticator")',
            'div:has(img[src*="authenticator"]):has-text("Authenticator")',
            # 通过类名和结构
            '[class*="iAwpk"]:has-text("Authenticator")',
            # 链接形式
            'a[href*="authenticator"]',
            'a:has-text("Authenticator")',
            # 通用文字匹配
            'div:has-text("Authenticator"):has(svg)',
        ]

        auth_row_clicked = False
        for selector in authenticator_row_selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0:
                    print(f"[信息] 找到 Authenticator 行: {selector}")
                    try:
                        await loc.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await loc.click(force=True)
                    auth_row_clicked = True
                    await asyncio.sleep(3)
                    break
            except Exception as e:
                print(f"[调试] 选择器 {selector} 失败: {e}")
                continue

        if not auth_row_clicked:
            # 备用方案：通过文字内容查找
            all_elements = await page.query_selector_all('div, a, span')
            for el in all_elements:
                try:
                    text = await el.inner_text()
                    if 'Authenticator' in text and len(text) < 100:
                        # 尝试点击父元素（整行）
                        parent = await el.evaluate_handle('el => el.closest("div.iAwpk, div[class*=\\"iAwpk\\"], a")')
                        if parent:
                            await parent.as_element().click()
                        else:
                            await el.click()
                        print(f"[信息] 通过文字匹配点击 Authenticator 行: {text[:50]}")
                        auth_row_clicked = True
                        await asyncio.sleep(3)
                        break
                except:
                    continue

        if auth_row_clicked:
            # 可能需要 2FA 验证
            if existing_secret:
                await handle_2fa_challenge(page, existing_secret, log_callback)
                await asyncio.sleep(2)

        await _safe_screenshot(page, "debug_auth_page.png", log_callback)
        print("[调试] 已截图: debug_auth_page.png")

        # 查找添加/设置/更换设备按钮 - 多语言支持
        add_keywords = [
            "Change authenticator app",
            "Change authenticator",
            "Add authenticator app",
            "Add authenticator",
            "Set up",
            "Add",
            "Change phone",
            "Change device",
            "设置",
            "添加",
            "更换手机",
            "更换设备",
            "Get codes",
            "获取验证码",
            # 荷兰语
            "toevoegen",
            "Instellen",
            "Wijzigen",
        ]

        add_button_clicked = False
        search_scopes = []
        try:
            dialog = await page.query_selector('[role="dialog"]')
            if dialog and await dialog.is_visible():
                search_scopes.append(dialog)
        except Exception:
            pass
        search_scopes.append(page)

        for keyword in add_keywords:
            if add_button_clicked:
                break
            selectors = [
                f'button:has-text("{keyword}")',
                f'[role="button"]:has-text("{keyword}")',
                f'a:has-text("{keyword}")',
            ]
            for scope in search_scopes:
                for selector in selectors:
                    try:
                        loc = scope.locator(selector).first
                        if await loc.count() > 0:
                            await loc.wait_for(state="visible", timeout=2000)
                            await loc.scroll_into_view_if_needed()
                            for _ in range(2):
                                try:
                                    await loc.click(force=True)
                                    add_button_clicked = True
                                    print(f"[信息] 找到添加/设置按钮: {keyword}")
                                    break
                                except Exception:
                                    await asyncio.sleep(0.3)
                            if add_button_clicked:
                                break
                    except Exception:
                        continue
                if add_button_clicked:
                    break

        if not add_button_clicked:
            # 调试：打印页面元素
            elements = await page.query_selector_all('button, [role="button"], a')
            print(f"[调试] 页面上有 {len(elements)} 个可点击元素")
            for i, el in enumerate(elements[:20]):
                try:
                    text = await el.inner_text()
                    href = await el.get_attribute('href')
                    print(f"[调试] 元素 {i}: text='{text[:40] if text else ''}', href='{href}'")
                except:
                    pass

            print("[错误] 未找到添加 Authenticator 的按钮")
            await _safe_screenshot(page, "debug_add_auth_not_found.png", log_callback)
            return None

        await asyncio.sleep(3)

        # 可能需要 2FA 验证
        if existing_secret:
            await handle_2fa_challenge(page, existing_secret, log_callback)
            await asyncio.sleep(2)

        await _safe_screenshot(page, "debug_after_add_click.png", log_callback)
        print("[调试] 已截图: debug_after_add_click.png")

        # 可能需要选择设备类型或继续
        continue_keywords = ["Next", "Continue", "下一步", "继续", "Set up", "设置"]
        for keyword in continue_keywords:
            next_button = await page.query_selector(f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}")')
            if next_button and await next_button.is_visible():
                await next_button.click()
                await asyncio.sleep(2)
                break

        # 等待 QR 码页面
        await asyncio.sleep(2)

        # 点击 "Can't scan it?" 获取文本密钥
        await _click_cant_scan(page, log_callback)

        # 提取密钥 - 通常是一个长字符串，格式类似 "XXXX XXXX XXXX XXXX" 或 "XXXXXXXXXXXXXXXX"
        # 查找包含密钥的元素
        secret = None

        # 方法1: 查找明显的密钥显示区域
        key_selectors = [
            '[data-secret]',
            '[class*="secret"]',
            '[class*="key"]',
            'code',
            'pre',
        ]

        for selector in key_selectors:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                secret = _extract_secret_from_text(text)
                if secret:
                    print(f"[成功] 找到密钥: {secret}")
                    break

        # 方法2: 搜索可见文本（避免从 HTML 属性中误匹配）
        if not secret:
            for _ in range(8):
                try:
                    dialog = await page.query_selector('[role="dialog"]')
                    if dialog and await dialog.is_visible():
                        dialog_text = await dialog.inner_text()
                        secret = _extract_secret_from_block(dialog_text)
                        if secret:
                            print(f"[成功] 从对话框文本提取密钥: {secret}")
                            break
                except Exception:
                    pass

                try:
                    body_text = await page.inner_text('body')
                    secret = _extract_secret_from_block(body_text)
                    if secret:
                        print(f"[成功] 从页面文本提取密钥: {secret}")
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        # 方法3: 查找所有文本元素
        if not secret:
            all_text_elements = await page.query_selector_all('span, div, p')
            for element in all_text_elements:
                try:
                    text = await element.inner_text()
                    secret = _extract_secret_from_text(text)
                    if secret:
                        print(f"[成功] 从文本元素提取密钥: {secret}")
                        break
                except:
                    continue

        if not secret:
            print("[错误] 未能提取到 2FA 密钥")
            await _safe_screenshot(page, "debug_secret_not_found.png", log_callback)
            return None

        # 点击 Next 进入验证码输入
        next_keywords = ["Next", "Continue", "Done", "确认", "下一步", "继续", "完成"]
        clicked_next = await _click_action_button(page, next_keywords, log_callback)
        if not clicked_next:
            print("[警告] 未找到 Next 按钮，继续流程")

        return secret

    except Exception as e:
        print(f"[错误] 添加 Authenticator 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


async def verify_new_secret(page: Page, secret: str, log_callback: Optional[Callable] = None) -> bool:
    """
    使用新密钥验证 Authenticator 设置

    Args:
        page: Playwright 页面对象
        secret: 2FA 密钥
        log_callback: 日志回调函数

    Returns:
        是否验证成功
    """
    if log_callback:
        log_callback("正在验证新密钥...")

    try:
        # 生成验证码
        totp = pyotp.TOTP(secret)
        code = totp.now()
        print(f"[信息] 生成验证码: {code}")

        # 查找验证码输入框
        code_input = await _find_code_input(page)
        if not code_input:
            try:
                await page.wait_for_selector(
                    'input[placeholder*="Code"], input[aria-label*="Code"], input[type="tel"], '
                    'input[inputmode="numeric"], input[autocomplete="one-time-code"]',
                    timeout=5000,
                )
            except Exception:
                pass
            code_input = await _find_code_input(page)

        if not code_input:
            # 尝试推进到验证码步骤
            await _click_action_button(
                page,
                ["Next", "Continue", "Verify", "确认", "验证", "下一步", "继续", "Done", "完成"],
                log_callback,
            )
            await asyncio.sleep(2)
            code_input = await _find_code_input(page)

        if code_input:
            await code_input.fill(code)
            await asyncio.sleep(1)

            # 点击验证/确认按钮
            verify_clicked = await _click_action_button(
                page,
                ["Verify", "Next", "确认", "验证", "下一步", "Done", "完成"],
                log_callback,
            )
            if verify_clicked:
                await asyncio.sleep(3)

                # 检查是否成功
                # 如果成功，页面应该返回到两步验证页面或显示成功消息
                success_keywords = ["success", "done", "成功", "完成", "已添加", "Added"]
                page_text = await page.content()
                for keyword in success_keywords:
                    if keyword.lower() in page_text.lower():
                        print("[成功] 验证成功!")
                        return True

                # 如果没有错误消息，也可能是成功了
                error_keywords = ["error", "invalid", "wrong", "错误", "无效"]
                has_error = False
                for keyword in error_keywords:
                    if keyword.lower() in page_text.lower():
                        has_error = True
                        break

                if not has_error:
                    print("[成功] 验证可能成功（无错误消息）")
                    return True

            print("[警告] 未找到验证按钮或验证失败")
        else:
            print("[信息] 未找到验证码输入框，可能不需要验证")
            return True

    except Exception as e:
        print(f"[错误] 验证异常: {e}")

    return False


async def _reset_2fa_impl(
    playwright: Playwright,
    browser_id: str,
    account_info: dict,
    ws_endpoint: str,
    log_callback: Optional[Callable] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    重置 2FA 的核心实现

    Returns:
        (success, message, new_secret)
    """
    browser = None
    try:
        chromium = playwright.chromium
        browser = await chromium.connect_over_cdp(ws_endpoint)
        default_context = browser.contexts[0]
        page = default_context.pages[0] if default_context.pages else await default_context.new_page()

        email = account_info.get('email', '')
        password = account_info.get('password', '')

        if log_callback:
            log_callback(f"正在处理账号: {email}")

        # 预热
        await asyncio.sleep(2)

        # 1. 导航到两步验证页面
        if log_callback:
            log_callback("正在导航到两步验证设置...")

        print(f"[信息] 导航到: {TWO_STEP_VERIFICATION_URL}")
        await _ensure_two_step_page(page, log_callback)
        await asyncio.sleep(2)

        # 2. 处理登录流程（基于页面元素而非 URL）
        try:
            # 检查是否有邮箱输入框（说明需要登录）
            email_input = await page.query_selector('input[type="email"]')
            if email_input:
                if log_callback:
                    log_callback("需要登录，正在输入邮箱...")
                await email_input.fill(email)
                await asyncio.sleep(0.5)

                # 点击下一步
                next_btn = await page.query_selector('#identifierNext button, button:has-text("Next"), button:has-text("下一步")')
                if next_btn:
                    await next_btn.click()
                await asyncio.sleep(3)

            # 检查是否有密码输入框
            password_input = await page.query_selector('input[type="password"]:visible')
            if not password_input:
                password_input = await page.wait_for_selector('input[type="password"]', timeout=5000)

            if password_input:
                if log_callback:
                    log_callback("正在输入密码...")
                await password_input.fill(password)
                await asyncio.sleep(0.5)

                # 点击下一步
                next_btn = await page.query_selector('#passwordNext button, button:has-text("Next"), button:has-text("下一步")')
                if next_btn:
                    await next_btn.click()
                await asyncio.sleep(3)

            # 处理 2FA 验证
            existing_secret = account_info.get('secret', '')
            if existing_secret:
                await handle_2fa_challenge(page, existing_secret, log_callback)
                await asyncio.sleep(2)

            # 处理账号恢复验证（备用邮箱）
            backup_email = account_info.get('backup', '')
            if backup_email:
                await handle_recovery_challenge(page, backup_email, log_callback)
                await asyncio.sleep(2)

        except Exception as e:
            print(f"[信息] 登录流程: {e}")

        # 3. 登录后设置语言为英文
        try:
            if log_callback:
                log_callback("正在设置语言为英文...")
            lang_ok, lang_msg = await set_language_to_english(
                page,
                password=password,
                backup_email=account_info.get('backup', ''),
            )
            if log_callback:
                level = "✅" if lang_ok else "⚠️"
                log_callback(f"{level} 语言设置: {lang_msg}")
        except Exception as lang_error:
            if log_callback:
                log_callback(f"⚠️ 语言设置失败: {lang_error}")

        # 4. 检查是否需要密码验证
        await handle_password_verification(page, password, log_callback)
        await asyncio.sleep(2)

        # 确保在正确的页面
        if not await _ensure_two_step_page(page, log_callback):
            await handle_password_verification(page, password, log_callback)
            await asyncio.sleep(2)

        # 5. 直接添加新的 Authenticator（不删除旧的！）
        # 正确流程：添加新的时用旧密钥验证，新的设置成功后旧的自动失效
        existing_secret = account_info.get('secret', '')
        new_secret = await add_new_authenticator(page, existing_secret, log_callback)

        if not new_secret:
            return False, "无法获取新的 2FA 密钥", None

        # 6. 验证新密钥
        verify_success = await verify_new_secret(page, new_secret, log_callback)

        ensure_secret = new_secret or existing_secret
        ensure_ok, ensure_msg = await _ensure_2sv_enabled(page, ensure_secret, password, log_callback)

        if verify_success and ensure_ok:
            if log_callback:
                log_callback(f"2FA 重置成功! 新密钥: {new_secret}")
            return True, f"2FA 重置成功，{ensure_msg}", new_secret
        if verify_success and not ensure_ok:
            return False, f"2FA 重置成功但未开启: {ensure_msg}", new_secret
        if not verify_success and ensure_ok:
            return True, f"2FA 密钥已获取（验证状态未知），{ensure_msg}", new_secret
        return False, f"2FA 密钥已获取但未开启: {ensure_msg}", new_secret

    except Exception as e:
        print(f"[错误] 重置 2FA 异常: {e}")
        import traceback
        traceback.print_exc()
        return False, f"异常: {str(e)}", None
    finally:
        # 确保断开 CDP 连接，释放资源
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


async def reset_2fa(
    browser_id: str,
    log_callback: Optional[Callable] = None,
    close_after: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    重置 Google 账号的 2FA

    Args:
        browser_id: 比特浏览器窗口 ID
        log_callback: 日志回调函数

    Returns:
        (success, message, new_secret)
    """
    # 获取浏览器信息
    target_browser = get_browser_info(browser_id)
    if not target_browser:
        browsers = get_browser_list(page=0, pageSize=1000)
        for b in browsers:
            if b.get('id') == browser_id:
                target_browser = b
                break

    if not target_browser:
        return False, f"找不到浏览器: {browser_id}", None

    # 解析账号信息
    account_info = {}
    remark = target_browser.get('remark', '')
    parts = remark.split('----')

    if len(parts) >= 2:
        account_info = {
            'email': parts[0].strip(),
            'password': parts[1].strip(),
        }
        if len(parts) >= 3:
            account_info['backup'] = parts[2].strip()
        if len(parts) >= 4:
            account_info['secret'] = parts[3].strip()
    else:
        return False, "remark 格式不正确，无法获取账号信息", None

    # 打开浏览器
    print(f"[信息] 正在打开浏览器 {browser_id}...")
    res = openBrowser(browser_id)
    if not res or not res.get('success', False):
        return False, f"无法打开浏览器: {res}", None

    ws_endpoint = res.get('data', {}).get('ws')
    if not ws_endpoint:
        closeBrowser(browser_id)
        return False, "无法获取 WebSocket 端点", None

    try:
        async with async_playwright() as playwright:
            success, message, new_secret = await _reset_2fa_impl(
                playwright, browser_id, account_info, ws_endpoint, log_callback
            )

            # 如果成功获取了新密钥，保存它
            if new_secret:
                email = account_info.get('email', 'unknown')

                # 保存到文件
                save_secret_to_file(email, new_secret, browser_id)

                # 更新比特浏览器配置
                update_browser_2fa(browser_id, new_secret, log_callback)

            return success, message, new_secret

    finally:
        if close_after:
            print(f"[信息] 正在关闭浏览器 {browser_id}...")
            closeBrowser(browser_id)
        else:
            print(f"[信息] 保持浏览器打开: {browser_id}")


def reset_2fa_sync(
    browser_id: str,
    log_callback: Optional[Callable] = None,
    close_after: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    同步版本的 2FA 重置函数

    Args:
        browser_id: 比特浏览器窗口 ID
        log_callback: 日志回调函数

    Returns:
        (success, message, new_secret)
    """
    return asyncio.run(reset_2fa(browser_id, log_callback, close_after))


if __name__ == "__main__":
    # 测试
    test_browser_id = "9a78355dd45b470586f2fc821f684ce0"

    def print_log(msg: str):
        print(f"[LOG] {msg}")

    print("=" * 50)
    print("Google 2FA 重置测试")
    print("=" * 50)
    print(f"测试浏览器 ID: {test_browser_id}")
    print()

    success, message, new_secret = reset_2fa_sync(test_browser_id, print_log)

    print()
    print("=" * 50)
    print(f"结果: {'成功' if success else '失败'}")
    print(f"消息: {message}")
    if new_secret:
        print(f"新密钥: {new_secret}")

        # 验证新密钥是否有效
        totp = pyotp.TOTP(new_secret)
        code = totp.now()
        print(f"当前验证码: {code}")
    print("=" * 50)
