"""
Google 账号首次设置 2FA
用于没有 2FA 的账号，为其添加新的 Authenticator
"""
import asyncio
import os
import sys
import re
from typing import Optional, Tuple, Callable

import pyotp
import requests
from playwright.async_api import async_playwright, Playwright, Page

from set_language import set_language_to_english
from google_recovery import handle_recovery_email_challenge, detect_manual_verification
from database import DBManager

# 比特浏览器 API
BIT_API_URL = "http://127.0.0.1:54345"
BIT_HEADERS = {'Content-Type': 'application/json'}

# Google 安全设置页面 URL
SECURITY_URL = "https://myaccount.google.com/security"
TWO_STEP_VERIFICATION_URL = "https://myaccount.google.com/signinoptions/two-step-verification?hl=en&pli=1"

TURN_OFF_SELECTORS = [
    'button:has-text("Turn off")',
    '[role="button"]:has-text("Turn off")',
    'text=/2-Step Verification is on/i',
    'text=/2-Step Verification is turned on/i',
    "text=/You're now protected with 2-Step Verification/i",
    "text=/You’re now protected with 2-Step Verification/i",
    # 西班牙语
    'button:has-text("Desactivar")',
    '[role="button"]:has-text("Desactivar")',
    'text=/La verificación en dos pasos está activada/i',
    # 荷兰语
    'text=/Tweestapsverificatie is ingeschakeld/i',
    'text=/Tweestapsverificatie.*aangezet/i',
]

TURN_ON_PROMPT_SELECTORS = [
    'text=/2-Step Verification is off/i',
    'text=/2-Step Verification is turned off/i',
    'text=/2-Step Verification is disabled/i',
]

def get_base_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_no_proxy_session() -> requests.Session:
    """获取不使用代理的 requests session"""
    session = requests.Session()
    session.trust_env = False
    return session


def open_browser(browser_id: str) -> dict:
    """打开浏览器"""
    session = get_no_proxy_session()
    res = session.post(
        f"{BIT_API_URL}/browser/open",
        json={"id": browser_id},
        headers=BIT_HEADERS,
        timeout=30
    ).json()
    return res


def close_browser(browser_id: str) -> dict:
    """关闭浏览器"""
    session = get_no_proxy_session()
    res = session.post(
        f"{BIT_API_URL}/browser/close",
        json={"id": browser_id},
        headers=BIT_HEADERS,
        timeout=10
    ).json()
    return res


def get_browser_info(browser_id: str) -> Optional[dict]:
    """获取浏览器信息"""
    session = get_no_proxy_session()
    res = session.post(
        f"{BIT_API_URL}/browser/list",
        json={"page": 0, "pageSize": 1000},
        headers=BIT_HEADERS,
        timeout=10
    ).json()

    if res.get('success') or res.get('code') == 0:
        browsers = res.get('data', {})
        if isinstance(browsers, list):
            for b in browsers:
                if b.get('id') == browser_id:
                    return b
        elif isinstance(browsers, dict):
            for b in browsers.get('list', []):
                if b.get('id') == browser_id:
                    return b
    return None


def update_browser_2fa(browser_id: str, new_secret: str,
                       log_callback: Optional[Callable] = None) -> bool:
    """更新比特浏览器配置中的 2FA 密钥"""
    try:
        browser_info = get_browser_info(browser_id)
        if not browser_info:
            return False

        def _log(msg: str) -> None:
            if log_callback:
                log_callback(msg)
            print(msg)

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

        session = get_no_proxy_session()
        res = session.post(
            f"{BIT_API_URL}/browser/update/partial",
            json={'ids': [browser_id], 'remark': new_remark, 'faSecretKey': new_secret},
            headers=BIT_HEADERS,
            timeout=10
        ).json()

        update_ok = res.get('success') or res.get('code') == 0
        if not update_ok:
            _log(f"[警告] 备注+密钥更新失败，准备重试: {res}")

        retry_key_ok = False
        verify_info = get_browser_info(browser_id) or {}
        if verify_info.get('faSecretKey') != new_secret:
            retry_res = session.post(
                f"{BIT_API_URL}/browser/update/partial",
                json={'ids': [browser_id], 'faSecretKey': new_secret},
                headers=BIT_HEADERS,
                timeout=10
            ).json()
            _log(f"[信息] 重试更新密钥: {retry_res}")
            retry_key_ok = retry_res.get('success') or retry_res.get('code') == 0

        retry_remark_ok = False
        verify_info = get_browser_info(browser_id) or {}
        if verify_info.get('remark') != new_remark:
            retry_res = session.post(
                f"{BIT_API_URL}/browser/update/partial",
                json={'ids': [browser_id], 'remark': new_remark},
                headers=BIT_HEADERS,
                timeout=10
            ).json()
            _log(f"[信息] 重试更新备注: {retry_res}")
            retry_remark_ok = retry_res.get('success') or retry_res.get('code') == 0

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
        print(f"[错误] 更新失败: {e}")
        return False


def save_secret_to_file(email: str, new_secret: str, browser_id: str = "") -> None:
    """保存密钥到文件"""
    from datetime import datetime
    file_path = os.path.join(get_base_path(), "new_2fa_secrets.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {email} | {new_secret} | {browser_id}\n"

    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(line)
    print(f"[成功] 已保存到: {file_path}")

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

async def _dismiss_blocking_dialog(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """关闭阻塞性对话框（如要求先添加二步验证方式的提示）"""
    async def _has_add_second_steps_text() -> bool:
        selectors = [
            'text=/Add second steps to your account/i',
            'text=/add second steps/i',
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _click_go_back() -> bool:
        btn_selectors = [
            'button:has-text("Go back")',
            'button:has-text("Back")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            '[role="button"]:has-text("Go back")',
            '[role="button"]:has-text("Back")',
        ]
        for btn_selector in btn_selectors:
            try:
                btn = await page.query_selector(btn_selector)
                if btn and await btn.is_visible():
                    await btn.click(force=True)
                    await asyncio.sleep(2)
                    if log_callback:
                        log_callback("已关闭提示对话框")
                    return True
            except Exception:
                continue
        try:
            role_btn = page.get_by_role("button", name=re.compile("Go back|Back|OK|Got it", re.I)).first
            if await role_btn.count() > 0 and await role_btn.is_visible():
                await role_btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已关闭提示对话框")
                return True
        except Exception:
            pass
        return False

    try:
        if await _has_add_second_steps_text():
            if await _click_go_back():
                return True
    except Exception:
        pass

    dialog_selectors = [
        '[role="dialog"]',
        '[role="alertdialog"]',
    ]
    for selector in dialog_selectors:
        try:
            dialog = await page.query_selector(selector)
            if not dialog or not await dialog.is_visible():
                continue
            text = (await dialog.inner_text()).strip()
            if "add second steps" in text.lower() or "Add second steps to your account" in text:
                if await _click_go_back():
                    return True
        except Exception:
            continue
    return False

async def _is_authenticator_setup_page(page: Page) -> bool:
    url = page.url.lower()
    if any(k in url for k in ["authenticator", "totp", "two-step-verification/enroll"]):
        return True
    selectors = [
        'text=/scan the qr code|qr code|can\\x27t scan|enter a setup key|setup key/i',
        '[data-otp-secret]',
        'img[alt*="QR"]',
        'canvas',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
    return False

async def _has_authenticator_added(page: Page) -> bool:
    """判断是否已添加 Authenticator（页面显示 Added...）"""
    added_selectors = [
        'text=/Added\\s+just\\s+now/i',
        'text=/Added\\s+\\d+\\s+\\w+\\s+ago/i',
        'text=/Added\\s+\\d+\\s+minutes\\s+ago/i',
        'text=/Added\\s+\\d+\\s+hours\\s+ago/i',
        'text=/Added\\s+\\d+\\s+days\\s+ago/i',
    ]
    for selector in added_selectors:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
    return False

async def _is_2sv_enabled(page: Page) -> bool:
    """判断 2-Step Verification 是否已开启"""
    for selector in TURN_OFF_SELECTORS:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
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

async def _is_2sv_off(page: Page) -> bool:
    """判断 2-Step Verification 是否显示为关闭"""
    for selector in TURN_ON_PROMPT_SELECTORS:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True
        except Exception:
            continue
    return False

async def _open_two_step_entry(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """从安全设置页点击进入两步验证入口"""
    selectors = [
        'a[href*="signinoptions/twosv"]',
        'a[href*="two-step-verification"]',
        '[role="link"][href*="signinoptions/twosv"]',
    ]
    for selector in selectors:
        try:
            link = page.locator(selector).first
            if await link.count() > 0 and await link.first.is_visible():
                await link.scroll_into_view_if_needed()
                await link.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已打开两步验证入口")
                return True
        except Exception:
            continue
    try:
        role_link = page.get_by_role("link", name=re.compile("2-Step Verification", re.I))
        if await role_link.count() > 0 and await role_link.first.is_visible():
            await role_link.first.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已打开两步验证入口")
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
            opened = await _open_two_step_entry(page, log_callback)
            if opened:
                await asyncio.sleep(2)
                if _on_two_step_page(page.url):
                    return True
        except Exception:
            pass

    return _on_two_step_page(page.url)

async def _is_turn_on_visible(page: Page) -> bool:
    turn_on_selectors = [
        'button:has-text("Turn on")',
        'button:has-text("Turn on 2-Step")',
        '[role="button"]:has-text("Turn on")',
        '[role="button"]:has-text("Turn on 2-Step")',
        'text=/Turn on 2.?Step/i',
        'text=/Turn on 2.?Step Verification/i',
        'h1:has-text("Turn on 2-Step")',
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
        'button:has-text("Aanzetten")',
        '[role="button"]:has-text("Aanzetten")',
        'text=/Tweestapsverificatie aanzetten/i',
        'button:has-text("Inschakelen")',
        '[role="button"]:has-text("Inschakelen")',
    ]
    for selector in turn_on_selectors:
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

async def _click_turn_on(page: Page, log_callback: Optional[Callable] = None) -> bool:
    """点击 Turn on 按钮（支持多种文案/位置）"""
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

    # 兜底：role/button 定位
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
    """点击 Skip（跳过）按钮"""
    selectors = [
        'button:has-text("Skip")',
        '[role="button"]:has-text("Skip")',
        'text=Skip',
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
        role_btn = page.get_by_role("button", name=re.compile("Skip|Omitir|Overslaan", re.I))
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
    """处理“Add a phone number for 2-Step Verification?”对话框"""
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
                # 等待对话框消失
                try:
                    await dialog.first.wait_for(state="hidden", timeout=3000)
                except Exception:
                    pass
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


async def _handle_verify_identity(page: Page, backup_email: str,
                                  log_callback: Optional[Callable] = None) -> bool:
    """处理首次登录的验证身份页面（选择确认辅助邮箱）"""
    if not backup_email:
        return False

    identity_markers = [
        "验证身份",
        "选择您想要使用的登录方式",
        "Verify it’s you",
        "Verify it's you",
        "Verify your identity",
        "Choose a way to sign in",
        "Try another way",
    ]
    try:
        content = await page.content()
    except Exception:
        content = ""

    if not any(marker in content for marker in identity_markers):
        return False

    if log_callback:
        log_callback("检测到验证身份页面，尝试选择辅助邮箱方式...")

    # 若存在“试试其他方式”，先点开列表
    await _click_action_button(page, ["Try another way", "试试其他方式"], log_callback)

    option_keywords = [
        "确认您的辅助邮箱",
        "确认辅助邮箱",
        "Confirm your recovery email",
        "Confirm your backup email",
        "Confirm your recovery email address",
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
                    if "div:has-text" in selector or "span:has-text" in selector:
                        box = await el.bounding_box()
                        if box and box['height'] > 160:
                            continue
                    await el.click(force=True)
                    clicked = True
                    break
            except Exception:
                continue
        if clicked:
            break

    # 兜底：直接选第三个选项（若存在）
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

    await asyncio.sleep(2)

    # 输入辅助邮箱（如果需要）
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


async def _ensure_2sv_enabled(page: Page, secret: Optional[str], password: Optional[str] = None,
                              log_callback: Optional[Callable] = None) -> Tuple[bool, str]:
    """确保 2-Step Verification 已开启"""
    if await _has_2sv_success_text(page):
        await _click_done_if_present(page, log_callback)
        return True, "2FA 已开启"

    await _handle_add_phone_dialog(page, log_callback)

    # 先检查是否已有 Turn on 按钮
    if not await _is_turn_on_visible(page):
        if await _is_2sv_off(page):
            await _open_two_step_entry(page, log_callback)
            await asyncio.sleep(2)
        if not await _is_turn_on_visible(page):
            try:
                await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)
            except Exception:
                pass
        if await _is_turn_on_visible(page):
            pass
        else:
            if await _is_2sv_enabled(page):
                return True, "2FA 已开启"
            if await _is_2sv_off(page):
                return False, "2FA 未开启（显示为关闭）"
        for selector in TURN_OFF_SELECTORS:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True, "2FA 已开启"
            except Exception:
                continue
        return False, "2FA 状态未知，未发现开关按钮"

    try:
        if await _has_2sv_success_text(page):
            await _click_done_if_present(page, log_callback)
            return True, "2FA 已开启"
        clicked = await _click_turn_on(page, log_callback)
        if not clicked:
            # 尝试对话框内的 Turn on
            await _click_action_button(
                page,
                ["Turn on", "Turn on 2-Step Verification", "Activar", "Aanzetten", "Inschakelen"],
                log_callback,
            )
        await asyncio.sleep(2)
        await _dismiss_blocking_dialog(page, log_callback)
        await _handle_add_phone_dialog(page, log_callback)
        if await _click_done_if_present(page, log_callback):
            return True, "2FA 已开启"
    except Exception as e:
        return False, f"点击 Turn on 失败: {e}"

    # 点击 Turn on 后会跳转到新页面，需要点击 "Turn on 2-Step Verification" 按钮
    # 查找并点击 "Turn on 2-Step Verification" 按钮（蓝色大按钮）
    turn_on_2sv_selectors = [
        'button[aria-label="Turn on 2-Step Verification"]',
        'button:has-text("Turn on 2-Step Verification")',
        '[role="button"]:has-text("Turn on 2-Step Verification")',
        # 荷兰语
        'button:has-text("Tweestapsverificatie aanzetten")',
        '[role="button"]:has-text("Tweestapsverificatie aanzetten")',
        'button:has-text("Aanzetten")',
        '[role="button"]:has-text("Aanzetten")',
        'button:has-text("Inschakelen")',
        '[role="button"]:has-text("Inschakelen")',
    ]
    for _ in range(2):
        clicked_turn_on_2sv = False
        for selector in turn_on_2sv_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    print("[信息] 点击 Turn on 2-Step Verification 按钮")
                    if log_callback:
                        log_callback("点击 Turn on 2-Step Verification")
                    await asyncio.sleep(2)
                    clicked_turn_on_2sv = True
                    break
            except Exception:
                continue

        if not clicked_turn_on_2sv:
            break

        dismissed = await _dismiss_blocking_dialog(page, log_callback)
        if dismissed:
            await asyncio.sleep(1)
            continue
        break

    # 等待 "Add a phone number for 2-Step Verification?" 对话框出现，然后点击 Skip
    # 对话框可能需要几秒才弹出，循环检测并点击 Skip
    skip_selectors = [
        # 对话框内的 Skip 按钮（蓝色填充按钮）
        '[role="dialog"] button:has-text("Skip")',
        '[role="alertdialog"] button:has-text("Skip")',
        # 通用 Skip 按钮
        'button:has-text("Skip")',
        '[role="button"]:has-text("Skip")',
    ]

    for attempt in range(8):
        skip_clicked = False
        for selector in skip_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    print("[信息] 已点击 Skip 跳过添加电话号码")
                    if log_callback:
                        log_callback("已点击 Skip")
                    await asyncio.sleep(2)
                    skip_clicked = True
                    break
            except Exception:
                continue

        if skip_clicked:
            # 检查对话框是否已关闭
            still_visible = False
            for selector in skip_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn and await btn.is_visible():
                        still_visible = True
                        break
                except Exception:
                    continue
            if not still_visible:
                break  # 成功关闭

        # 检查是否已经不需要点击了（对话框不存在）
        any_skip_visible = False
        for selector in skip_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    any_skip_visible = True
                    break
            except Exception:
                continue
        if not any_skip_visible:
            break  # 没有 Skip 按钮，继续下一步

        await asyncio.sleep(1)

    await _handle_add_phone_dialog(page, log_callback)

    if await _has_2sv_success_text(page):
        await _click_done_if_present(page, log_callback)
        return True, "2FA 已开启"

    # 若出现确认对话框，再点一次 Turn on/Next
    await _click_action_button(
        page,
        ["Turn on", "Next", "Continue", "Confirm", "Activar", "Aanzetten", "Inschakelen"],
        log_callback,
    )
    await asyncio.sleep(2)
    await _click_skip_if_present(page, log_callback)
    await asyncio.sleep(1)
    if await _click_done_if_present(page, log_callback):
        return True, "2FA 已开启"

    # 处理可能的密码确认
    if password:
        try:
            pwd_input = await page.query_selector('input[type="password"]')
            if pwd_input and await pwd_input.is_visible():
                await pwd_input.fill(password)
                await asyncio.sleep(0.5)
                await _click_action_button(page, ["Next", "Confirm", "Continue"], log_callback)
                await asyncio.sleep(2)
        except Exception:
            pass
    await _click_skip_if_present(page, log_callback)
    await asyncio.sleep(1)

    # 如出现验证码输入框，尝试验证
    code_input = None
    code_selectors = [
        'input[type="tel"]',
        'input[inputmode="numeric"]',
        'input[autocomplete="one-time-code"]',
        'input[aria-label*="code"]',
        'input[placeholder*="Code"]',
    ]
    for selector in code_selectors:
        try:
            inp = await page.query_selector(selector)
            if inp and await inp.is_visible():
                code_input = inp
                break
        except Exception:
            continue

    if code_input:
        if not secret:
            return False, "需要验证码但缺少密钥"
        totp = pyotp.TOTP(secret)
        code = totp.now()
        await code_input.fill(code)
        await asyncio.sleep(1)
        await _click_action_button(
            page,
            [
                "Verify", "Next", "Turn on", "Confirm", "Done",
                "Verificar", "Siguiente", "Confirmar", "Listo", "Activar",
                "Aanzetten", "Inschakelen",
            ],
            log_callback,
        )
        await asyncio.sleep(2)
        await _click_skip_if_present(page, log_callback)
        await asyncio.sleep(1)
        if await _click_done_if_present(page, log_callback):
            return True, "2FA 已开启"

    if await _has_2sv_success_text(page):
        await _click_done_if_present(page, log_callback)
        return True, "2FA 已开启"

    # 再次检查是否已开启
    if await _is_turn_on_visible(page):
        # 再尝试跳转到 2SV 主页面开启
        try:
            await page.goto(TWO_STEP_VERIFICATION_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
        except Exception:
            pass

        if await _is_turn_on_visible(page):
            # 这里再尝试点击一次
            await _click_turn_on(page, log_callback)
            await asyncio.sleep(3)

        if await _is_turn_on_visible(page):
            return False, "2FA 未开启（仍显示 Turn on）"

    if await _click_done_if_present(page, log_callback):
        return True, "2FA 已开启"

    for selector in TURN_OFF_SELECTORS:
        try:
            loc = page.locator(selector)
            if await loc.count() > 0 and await loc.first.is_visible():
                return True, "2FA 已开启"
        except Exception:
            continue

    return True, "已尝试开启 2FA"

async def _click_action_button(page: Page, keywords: list[str], log_callback: Optional[Callable] = None) -> bool:
    """在对话框优先点击按钮/链接（Next/Continue/Verify 等）"""
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
                        print(f"[信息] 点击: {keyword}")
                        await asyncio.sleep(3)
                        return True
                except Exception:
                    continue
        # 兜底：使用 role/text 定位
        try:
            role_btn = page.get_by_role("button", name=keyword)
            if await role_btn.count() > 0 and await role_btn.first.is_visible():
                await role_btn.first.click(force=True)
                if log_callback:
                    log_callback(f"点击: {keyword}")
                print(f"[信息] 点击: {keyword}")
                await asyncio.sleep(3)
                return True
        except Exception:
            pass
        try:
            text_loc = page.get_by_text(keyword, exact=True)
            if await text_loc.count() > 0 and await text_loc.first.is_visible():
                await text_loc.first.click(force=True)
                if log_callback:
                    log_callback(f"点击: {keyword}")
                print(f"[信息] 点击: {keyword}")
                await asyncio.sleep(3)
                return True
        except Exception:
            pass
    return False


async def _ensure_logged_in(
    page: Page,
    email: str,
    password: str,
    backup_email: str,
    log_callback: Optional[Callable] = None,
) -> Tuple[bool, str]:
    """确保已登录账号，优先完成登录再继续后续步骤。"""
    if log_callback:
        log_callback("检查登录状态...")

    try:
        email_input = await page.query_selector('input[type="email"]')
        if email_input and await email_input.is_visible():
            if log_callback:
                log_callback("正在登录...")
            await email_input.fill(email)
            await asyncio.sleep(0.5)
            next_btn = await page.query_selector('#identifierNext button, button:has-text("Next"), button:has-text("Volgende")')
            if next_btn:
                await next_btn.click()
            await asyncio.sleep(3)

        password_input = await page.query_selector('input[type="password"]')
        if password_input and await password_input.is_visible():
            if log_callback:
                log_callback("正在输入密码...")
            await password_input.fill(password)
            await asyncio.sleep(0.5)
            next_btn = await page.query_selector('#passwordNext button, button:has-text("Next"), button:has-text("Volgende")')
            if next_btn:
                await next_btn.click()
            await asyncio.sleep(3)

        # 处理首次登录验证身份（选择辅助邮箱）
        if backup_email:
            handled = await _handle_verify_identity(page, backup_email, log_callback)
            if handled:
                await asyncio.sleep(2)

        # 如果出现辅助邮箱输入页面，尝试填写
        if backup_email:
            try:
                await handle_recovery_email_challenge(page, backup_email)
            except Exception:
                pass

        if await detect_manual_verification(page):
            return False, "需要人工完成验证码"

    except Exception as e:
        return False, f"登录处理异常: {e}"

    if log_callback:
        log_callback("登录完成，继续...")
    return True, "已登录或无需登录"


async def _click_spanish_configure_authenticator(
    page: Page,
    log_callback: Optional[Callable] = None,
) -> bool:
    """在西班牙语页面点击“Configurar autenticador”按钮。"""
    selectors = [
        'button:has-text("Configurar autenticador")',
        '[role="button"]:has-text("Configurar autenticador")',
        'a:has-text("Configurar autenticador")',
        'button:has(span:has-text("Configurar autenticador"))',
    ]
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click(force=True)
                await asyncio.sleep(2)
                if log_callback:
                    log_callback("已点击 Configurar autenticador")
                print("[信息] 已点击 Configurar autenticador")
                return True
        except Exception:
            continue

    try:
        role_btn = page.get_by_role("button", name=re.compile("Configurar autenticador", re.I))
        if await role_btn.count() > 0 and await role_btn.first.is_visible():
            await role_btn.first.click(force=True)
            await asyncio.sleep(2)
            if log_callback:
                log_callback("已点击 Configurar autenticador")
            print("[信息] 已点击 Configurar autenticador")
            return True
    except Exception:
        pass

    return False

async def setup_2fa_impl(
    playwright: Playwright,
    browser_id: str,
    account_info: dict,
    ws_endpoint: str,
    log_callback: Optional[Callable] = None
) -> Tuple[bool, str, Optional[str]]:
    """设置 2FA 的核心实现"""

    browser = None
    try:
        chromium = playwright.chromium
        browser = await chromium.connect_over_cdp(ws_endpoint)
        default_context = browser.contexts[0]

        # 获取或创建页面，优先使用最后一个活动页面
        if default_context.pages:
            page = default_context.pages[-1]
        else:
            page = await default_context.new_page()

        email = account_info.get('email', '')
        password = account_info.get('password', '')

        if log_callback:
            log_callback(f"正在处理: {email}")

        await asyncio.sleep(2)

        # 1. 先进入登录页并完成登录
        if log_callback:
            log_callback("正在导航到登录页面...")

        try:
            await page.goto("https://accounts.google.com", timeout=60000, wait_until="domcontentloaded")
        except Exception as nav_error:
            print(f"[警告] 登录页导航可能有重定向: {nav_error}")
            await asyncio.sleep(3)

        await asyncio.sleep(2)

        # 2. 先登录（如果需要），再继续后续流程
        login_ok, login_msg = await _ensure_logged_in(
            page,
            email=email,
            password=password,
            backup_email=account_info.get('backup', ''),
            log_callback=log_callback,
        )
        if not login_ok:
            return False, login_msg, None

        # 3. 登录后再设置语言为英文，避免多语言问题
        if log_callback:
            log_callback("正在设置语言为英文...")
        try:
            lang_success, lang_msg = await set_language_to_english(
                page,
                password=password,
                backup_email=account_info.get('backup', ''),
            )
            if lang_success:
                if log_callback:
                    log_callback(f"✅ {lang_msg}")
            else:
                if log_callback:
                    log_callback(f"⚠️ 语言设置: {lang_msg}，继续...")
        except Exception as lang_error:
            if log_callback:
                log_callback(f"⚠️ 语言设置失败: {lang_error}，继续...")

        # 4. 回到两步验证页面
        if log_callback:
            log_callback("正在导航到两步验证设置...")
        await _ensure_two_step_page(page, log_callback)
        await asyncio.sleep(2)

        # 如果两步验证页又要求登录/验证，再补一次
        if log_callback:
            log_callback("两步验证页可能要求重新登录，正在检查...")
        login_ok, login_msg = await _ensure_logged_in(
            page,
            email=email,
            password=password,
            backup_email=account_info.get('backup', ''),
            log_callback=log_callback,
        )
        if not login_ok:
            return False, login_msg, None

        await _safe_screenshot(page, "debug_setup_2fa_page.png", log_callback)

        if await _is_2sv_enabled(page):
            msg = "2FA 已开启，跳过设置"
            if log_callback:
                log_callback(f"✅ {msg}")
            return True, msg, None

        if await _has_authenticator_added(page):
            ok, status_msg = await _ensure_2sv_enabled(
                page,
                account_info.get('secret', '') or None,
                password,
                log_callback,
            )
            if not ok:
                return False, status_msg, None
            msg = f"Authenticator 已添加，{status_msg}"
            if log_callback:
                log_callback(f"✅ {msg}")
            return True, msg, None

        # 3. 若已在 Authenticator 页面，直接点击“Configurar autenticador”
        clicked_direct = False
        if await _click_spanish_configure_authenticator(page, log_callback):
            clicked_direct = True
            await asyncio.sleep(2)
            if len(default_context.pages) > 1:
                page = default_context.pages[-1]
            await _safe_screenshot(page, "debug_after_es_configure.png", log_callback)

        # 4. 优先点击 Authenticator 行（避免先点 Turn on 触发拦截弹窗）
        # 页面结构：div.iAwpk 包含 Authenticator 图标和文字，是可点击的整行
        # 或者是 "+ Authenticator instellen" 按钮
        if log_callback:
            log_callback("正在查找 Authenticator 设置入口...")

        authenticator_row = None
        if clicked_direct:
            authenticator_row = True

        # 优先点击 "Add authenticator app" 操作入口
        add_auth_selectors = [
            'button:has-text("Add authenticator app")',
            '[role="button"]:has-text("Add authenticator app")',
            'a:has-text("Add authenticator app")',
            'text="Add authenticator app"',
            # 西班牙语
            'button:has-text("Configurar autenticador")',
            '[role="button"]:has-text("Configurar autenticador")',
            'a:has-text("Configurar autenticador")',
            'text="Configurar autenticador"',
        ]
        for selector in add_auth_selectors:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    parent = await el.evaluate_handle(
                        'el => el.closest("button, [role=button], [role=link], a, div[jscontroller]")'
                    )
                    authenticator_row = parent.as_element() if parent else el
                    print(f"[信息] 找到 Add authenticator app: {selector}")
                    break
            except Exception:
                continue

        # 方法1: 直接查找 "Authenticator instellen" 按钮（荷兰语）
        instellen_selectors = [
            'button:has-text("Authenticator instellen")',
            'a:has-text("Authenticator instellen")',
            '[role="button"]:has-text("Authenticator instellen")',
            'div:has-text("Authenticator instellen")',
            # 英语
            'button:has-text("Set up Authenticator")',
            'button:has-text("Add Authenticator")',
            # 西班牙语
            'button:has-text("Configurar autenticador")',
            'a:has-text("Configurar autenticador")',
            '[role="button"]:has-text("Configurar autenticador")',
            'div:has-text("Configurar autenticador")',
            # 日语
            'button:has-text("認証システムを設定")',
            'div:has-text("認証システム アプリを追加")',
        ]

        for selector in instellen_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    authenticator_row = btn
                    print(f"[信息] 找到 Authenticator 按钮: {selector}")
                    break
            except Exception as e:
                print(f"[调试] 选择器 {selector} 失败: {e}")
                continue

        # 方法2: 通过 iAwpk 类选择器 + Authenticator 文字
        if not authenticator_row:
            authenticator_row_selectors = [
                'div.iAwpk:has-text("Authenticator")',
                '[class*="iAwpk"]:has-text("Authenticator")',
                'div:has(img[src*="authenticator"]):has-text("Authenticator")',
                # 西班牙语
                'div.iAwpk:has-text("Autenticador")',
                '[class*="iAwpk"]:has-text("Autenticador")',
                # 荷兰语
                'div.iAwpk:has-text("toevoegen")',
                '[class*="iAwpk"]:has-text("toevoegen")',
                # 日语
                'div.iAwpk:has-text("認証システム")',
                '[class*="iAwpk"]:has-text("認証システム")',
            ]

            for selector in authenticator_row_selectors:
                try:
                    row = await page.query_selector(selector)
                    if row and await row.is_visible():
                        authenticator_row = row
                        print(f"[信息] 找到 Authenticator 行: {selector}")
                        break
                except Exception as e:
                    print(f"[调试] 选择器 {selector} 失败: {e}")
                    continue

        # 方法0: 检查是否有模态对话框，优先在对话框内点击 Authenticator
        # Google 会弹出 "To turn on 2-Step Verification, first add second steps below" 对话框
        dialog_selectors = [
            '[role="dialog"] :text("Authenticator")',
            '[role="dialog"] div:has-text("Authenticator")',
            '.uW2Fw-Sx9Kwc div:has-text("Authenticator")',  # Google 模态框 class
            '[jscontroller] div:has-text("Authenticator"):not(:has(div:has-text("Authenticator")))',  # 最内层
        ]
        for selector in dialog_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        box = await el.bounding_box()
                        if box and 30 < box['height'] < 150:  # 对话框内的行
                            authenticator_row = el
                            print(f"[信息] 在模态对话框中找到 Authenticator: {selector}")
                            break
                if authenticator_row:
                    break
            except:
                continue

        # 方法2: 通过文字内容查找（多语言）
        if not authenticator_row:
            auth_row_keywords = [
                "Authenticator-app toevoegen",  # 荷兰语
                "Authenticator instellen",       # 荷兰语
                "Add Authenticator",             # 英语
                "Set up Authenticator",          # 英语
                "添加身份验证器",                  # 中文
                "设置 Authenticator",             # 中文
                "Authenticator app",             # 通用
                # 西班牙语
                "Configurar autenticador",
                "Aplicación Authenticator",
                "Aplicación de autenticación",
            ]

            for keyword in auth_row_keywords:
                try:
                    # 查找包含关键词的可点击元素
                    elements = await page.query_selector_all(f'div:has-text("{keyword}")')
                    for el in elements:
                        if await el.is_visible():
                            # 检查是否是行级元素（不是整个页面）
                            box = await el.bounding_box()
                            if box and box['height'] < 200:  # 行高度不应太大
                                authenticator_row = el
                                print(f"[信息] 找到 Authenticator 入口: {keyword}")
                                break
                    if authenticator_row:
                        break
                except:
                    continue

        # 方法3: 查找设置按钮（备选）
        if not authenticator_row:
            setup_keywords = [
                "Authenticator instellen",  # Dutch
                "Get started",
                "Turn on",
                "Set up",
                "Add authenticator",
                "开始使用",
                "开启",
            ]

            for keyword in setup_keywords:
                buttons = await page.query_selector_all(f'button:has-text("{keyword}")')
                if not buttons:
                    buttons = await page.query_selector_all(f'a:has-text("{keyword}")')
                if not buttons:
                    buttons = await page.query_selector_all(f'[role="button"]:has-text("{keyword}")')

                for btn in buttons:
                    try:
                        if await btn.is_visible():
                            authenticator_row = btn
                            print(f"[信息] 找到设置按钮: {keyword}")
                            break
                    except:
                        continue
                if authenticator_row:
                    break

        if authenticator_row and authenticator_row is not True:
            # 使用 force=True 强制点击，因为可能被模态对话框遮挡
            try:
                await authenticator_row.click(force=True)
            except Exception as e:
                print(f"[调试] 普通点击失败，尝试 JS 点击: {e}")
                await page.evaluate("el => el.click()", authenticator_row)
            await asyncio.sleep(3)
            print("[信息] 已点击 Authenticator 入口")

            # 检查是否有新页面打开，使用最新的页面
            if len(default_context.pages) > 1:
                page = default_context.pages[-1]
                print(f"[信息] 切换到新页面: {page.url[:60]}")

            # 可能需要再点击 "Set up authenticator" 按钮进入设置（图2/3的步骤）
            setup_btn = None
            setup_btn_selectors = [
                # 英语 - 多种变体
                'button:has-text("Set up authenticator")',
                'button:has-text("Set up Authenticator")',
                'a:has-text("Set up authenticator")',
                '[role="button"]:has-text("Set up authenticator")',
                'text="Set up authenticator"',
                'text="+ Set up authenticator"',
                # 带加号的按钮
                'button:has-text("+ Set up")',
                # 西班牙语
                'button:has-text("Configurar autenticador")',
                'a:has-text("Configurar autenticador")',
                '[role="button"]:has-text("Configurar autenticador")',
                'text="Configurar autenticador"',
                # 荷兰语
                'button:has-text("Authenticator instellen")',
                'button:has-text("+ Authenticator instellen")',
                # 中文
                'button:has-text("设置 Authenticator")',
                'button:has-text("设置身份验证器")',
                # 日语
                'button:has-text("認証システムを設定")',
            ]

            for selector in setup_btn_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn and await btn.is_visible():
                        setup_btn = btn
                        print(f"[信息] 找到 Set up authenticator 按钮: {selector}")
                        break
                except Exception as e:
                    print(f"[调试] 选择器 {selector} 失败: {e}")
                    continue

            if setup_btn:
                try:
                    # 先尝试普通点击（不用 force，让 jsaction 正常触发）
                    await setup_btn.click(timeout=5000)
                    print("[信息] 已点击 Set up authenticator 按钮")
                except Exception as e:
                    print(f"[调试] 普通点击失败，尝试 JS dispatchEvent: {e}")
                    # 使用 dispatchEvent 触发真实点击事件
                    await page.evaluate("""
                        el => {
                            el.dispatchEvent(new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                        }
                    """, setup_btn)
                await asyncio.sleep(3)

                # 等待页面变化 - QR 码页面或 "Can't scan" 链接出现
                try:
                    await page.wait_for_selector(
                        "text=/Can't scan|Enter a setup key|无法扫描/i",
                        timeout=5000
                    )
                    print("[信息] 已进入 QR 码页面")
                except Exception:
                    pass  # 继续执行，可能已经在正确页面

                # 再次检查页面
                if len(default_context.pages) > 1:
                    page = default_context.pages[-1]
            else:
                clicked_es = await _click_spanish_configure_authenticator(page, log_callback)
                if not clicked_es:
                    print("[警告] 未找到 Set up authenticator 按钮，可能已在设置页面")
        elif not authenticator_row:
            # 西班牙语页面可能直接显示“Configurar autenticador”
            if await _click_spanish_configure_authenticator(page, log_callback):
                await asyncio.sleep(2)
                await _safe_screenshot(page, "debug_after_es_configure.png", log_callback)

            # 如果找不到 Authenticator，再尝试点击 Turn on 2-Step Verification
            if log_callback:
                log_callback("未找到 Authenticator，尝试点击 Turn on 2-Step Verification...")

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            turn_on_btn = None
            turn_on_selectors = [
                # 精确文本匹配
                'button:has-text("Turn on 2-Step Verification")',
                # 使用 text 选择器
                'text=Turn on 2-Step Verification',
                # 蓝色填充按钮的多种可能类名
                'button.VfPpkd-LgbsSe-OWXEXe-k8QpJ',
                'button.VfPpkd-LgbsSe.VfPpkd-LgbsSe-OWXEXe-k8QpJ',
                # 链接形式
                'a:has-text("Turn on 2-Step Verification")',
                # 通用：页面上包含 "Turn on" 的按钮
                '[role="button"]:has-text("Turn on")',
            ]

            for selector in turn_on_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn and await btn.is_visible():
                        turn_on_btn = btn
                        print(f"[信息] 找到 Turn on 按钮: {selector}")
                        break
                except Exception as e:
                    print(f"[调试] 选择器 {selector} 失败: {e}")
                    continue

            # 如果仍未找到，尝试使用 locator API
            if not turn_on_btn:
                try:
                    locator = page.get_by_role("button", name="Turn on 2-Step Verification")
                    if await locator.count() > 0:
                        turn_on_btn = await locator.first.element_handle()
                        print("[信息] 使用 locator API 找到 Turn on 按钮")
                except Exception as e:
                    print(f"[调试] locator API 失败: {e}")

            if turn_on_btn:
                await turn_on_btn.click()
                await asyncio.sleep(3)
                print("[信息] 已点击 Turn on 2-Step Verification")
                await _safe_screenshot(page, "debug_after_turn_on.png", log_callback)
                await _dismiss_blocking_dialog(page, log_callback)
            else:
                await _safe_screenshot(page, "debug_turn_on_not_found.png", log_callback)
                print("[错误] 未找到 Turn on 按钮，无法继续设置2FA")
                return False, "未找到 Authenticator 入口或 Turn on 按钮", None

        await _safe_screenshot(page, "debug_after_setup_click.png", log_callback)

        # 4. 可能需要再次点击确认或选择设备类型
        # 有些流程需要选择 Android/iPhone
        device_selectors = [
            'div:has-text("Android")',
            'div:has-text("iPhone")',
            '[role="radio"]',
        ]
        for selector in device_selectors:
            try:
                device = await page.query_selector(selector)
                if device and await device.is_visible():
                    await device.click()
                    await asyncio.sleep(1)
                    print(f"[信息] 选择设备类型")
                    break
            except:
                continue

        # 点击 Next/Continue（多语言）
        next_keywords = ["Next", "Continue", "Volgende", "Siguiente", "Continuar", "下一步", "继续"]
        for keyword in next_keywords:
            next_btn = await page.query_selector(f'button:has-text("{keyword}")')
            if next_btn and await next_btn.is_visible():
                await next_btn.click()
                await asyncio.sleep(3)
                print(f"[信息] 点击: {keyword}")
                break

        await _safe_screenshot(page, "debug_qr_page.png", log_callback)
        print("[调试] 已截图: debug_qr_page.png")

        if not await _is_authenticator_setup_page(page):
            # 可能已添加 Authenticator，直接返回
            if await _has_authenticator_added(page):
                ok, status_msg = await _ensure_2sv_enabled(
                    page,
                    account_info.get('secret', '') or None,
                    password,
                    log_callback,
                )
                if not ok:
                    return False, status_msg, None
                msg = f"Authenticator 已添加，{status_msg}"
                if log_callback:
                    log_callback(f"✅ {msg}")
                return True, msg, None

            await _safe_screenshot(page, "debug_not_in_auth_setup.png", log_callback)
            msg = "未进入 Authenticator 设置页面"
            if log_callback:
                log_callback(f"❌ {msg}")
            return False, msg, None

        # 5. 点击 "Can't scan it?" 获取文本密钥（多语言）
        # 先截图查看当前状态
        await _safe_screenshot(page, "debug_before_cant_scan.png", log_callback)

        cant_scan_keywords = [
            # 荷兰语 - 精确匹配
            "Kun je de code niet scannen?",
            "Kun je de code niet scannen",
            # 英语
            "Can't scan it?",
            "Can't scan it",
            "Can't scan",
            "Cannot scan",
            "Can\u2019t scan it?",
            "Can\u2019t scan it",
            "Enter a setup key",
            "Use a setup key",
            # 西班牙语
            "¿No puedes escanearlo?",
            "No puedes escanearlo",
            "Introducir una clave de configuración",
            "Ingresar una clave de configuración",
            "Usar una clave de configuración",
            # 德语
            "Code kann nicht gescannt werden",
            # 法语
            "Impossible de scanner",
            # 日语
            "スキャンできない",
            "コードをスキャンできない",
            # 中文
            "无法扫描",
            "手动输入",
        ]

        link_found = False
        for attempt in range(2):
            link_found = False
            for keyword in cant_scan_keywords:
                try:
                    # 尝试多种选择器
                    selectors = [
                        f'button:has-text("{keyword}")',
                        f'a:has-text("{keyword}")',
                        f'span:has-text("{keyword}")',
                        f'[role="link"]:has-text("{keyword}")',
                        f'[role="button"]:has-text("{keyword}")',
                    ]
                    for selector in selectors:
                        link = await page.query_selector(selector)
                        if link and await link.is_visible():
                            print(f"[信息] 找到链接: {keyword} (选择器: {selector})")
                            await link.click()
                            await asyncio.sleep(2)
                            link_found = True
                            break
                    if link_found:
                        break
                except Exception as e:
                    print(f"[调试] 查找 '{keyword}' 失败: {e}")
                    continue

            if not link_found:
                # 尝试直接在对话框内点击 "Can't scan it?"
                try:
                    cant_scan_loc = page.locator("text=/Can[\\u2019']t scan it\\?|Can[\\u2019']t scan it/i").first
                    if await cant_scan_loc.count() > 0 and await cant_scan_loc.is_visible():
                        await cant_scan_loc.click()
                        await asyncio.sleep(2)
                        link_found = True
                        print("[信息] 使用正则定位点击 Can't scan it?")
                except Exception as e:
                    print(f"[调试] 正则定位 Can't scan it? 失败: {e}")

            if not link_found:
                # 尝试用 locator API 更精确查找
                print("[调试] 尝试使用 locator API 查找...")
                try:
                    cant_scan_locator = page.get_by_text("Kun je de code niet scannen", exact=False)
                    if await cant_scan_locator.count() > 0:
                        await cant_scan_locator.first.click()
                        await asyncio.sleep(2)
                        link_found = True
                        print("[信息] 使用 locator API 成功点击")
                except Exception as e:
                    print(f"[调试] locator API 失败: {e}")

            if link_found:
                break

            # 仍未找到，尝试进入更换/设置页面后重试一次
            change_clicked = await _click_action_button(
                page,
                ["Change authenticator app", "Set up authenticator app", "Set up authenticator"],
                log_callback,
            )
            if change_clicked:
                await asyncio.sleep(2)
                continue
            break

        secret_view_ready = link_found
        if not secret_view_ready:
            try:
                hint_loc = page.locator('text=/Enter a setup key|setup key/i')
                if await hint_loc.count() > 0 and await hint_loc.first.is_visible():
                    secret_view_ready = True
            except Exception:
                pass

        if not secret_view_ready:
            if await _has_authenticator_added(page):
                ok, status_msg = await _ensure_2sv_enabled(
                    page,
                    account_info.get('secret', '') or None,
                    password,
                    log_callback,
                )
                if not ok:
                    return False, status_msg, None
                msg = f"Authenticator 已存在，{status_msg}"
                if log_callback:
                    log_callback(f"✅ {msg}")
                return True, msg, None
            print("[警告] 未找到 'Can't scan' 链接，且未进入密钥页面")
            return False, "未进入密钥页面", None

        await _safe_screenshot(page, "debug_secret_page.png", log_callback)
        print("[调试] 已截图: debug_secret_page.png")

        # 6. 提取密钥
        secret = None
        page_content = await page.content()

        # 已知的误匹配文本（页面 UI 元素，不是密钥）
        false_positives = {
            "DOORGAANNAARHOOFDCONTENT",  # 荷兰语 "继续到主内容"
            "SKIPTOMAINCONTEN",
            "GOOGLEACCOUNT",
            "AUTHENTICATOR",
            "VERIFICATIONCODE",
            "ENTERCODE",
            "SETUPKEY",
            "ACCOUNTINSTELLINGENVOORGOOGLE",  # 荷兰语 "Google账户设置"
            "TERUGNAARVORIGEPAGINA",  # 荷兰语 "返回上一页"
            "BELANGRIJKEACCOUNTMELDING",  # 荷兰语 "重要账户通知"
        }

        # 查找 Base32 格式的密钥（保留原始大小写）
        # Google 密钥格式通常是: xxxx xxxx xxxx xxxx xxxx xxxx xxxx xxxx (32字符，每4字符用空格分隔)
        patterns = [
            r'[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}\s+[A-Za-z2-7]{4}',
            r'[A-Za-z2-7]{4}[\s]?[A-Za-z2-7]{4}[\s]?[A-Za-z2-7]{4}[\s]?[A-Za-z2-7]{4}(?:[\s]?[A-Za-z2-7]{4})*',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, page_content)
            for match in matches:
                clean_match = re.sub(r'[\s-]', '', match)
                clean_upper = clean_match.upper()
                if 16 <= len(clean_match) <= 32 and re.match(r'^[A-Za-z2-7]+$', clean_match):
                    # 排除已知的误匹配
                    if clean_upper not in false_positives and not any(fp in clean_upper for fp in false_positives):
                        secret = clean_match
                        print(f"[成功] 找到密钥: {secret}")
                        break
                    else:
                        print(f"[调试] 跳过误匹配: {clean_match}")
            if secret:
                break

        if not secret:
            # 尝试查找特定的密钥容器元素
            secret_selectors = [
                'div[data-credential-id]',
                '[data-otp-secret]',
                'code',
                'pre',
                '.secret-key',
                '[class*="secret"]',
            ]
            for selector in secret_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        text = await el.inner_text()
                        clean = re.sub(r'[\s-]', '', text.strip())
                        clean_upper = clean.upper()
                        if re.match(r'^[A-Za-z2-7]{16,32}$', clean) and clean_upper not in false_positives:
                            secret = clean
                            print(f"[成功] 从 {selector} 找到密钥: {secret}")
                            break
                except:
                    continue
                if secret:
                    break

        if not secret:
            # 尝试查找所有文本元素，特别注意带空格的密钥格式
            all_elements = await page.query_selector_all('span, div, code, pre, p')
            for el in all_elements:
                try:
                    text = await el.inner_text()
                    text = text.strip()
                    # 密钥通常是独立显示的，格式为 xxxx xxxx xxxx... 或连续字符
                    if 20 < len(text) < 60:
                        clean = re.sub(r'[\s-]', '', text.strip())
                        clean_upper = clean.upper()
                        if re.match(r'^[A-Za-z2-7]{16,32}$', clean):
                            if clean_upper not in false_positives and not any(fp in clean_upper for fp in false_positives):
                                secret = clean
                                print(f"[成功] 找到密钥: {secret}")
                                break
                except:
                    continue

        if not secret:
            # 打印页面元素用于调试
            elements = await page.query_selector_all('button, a, span, div')
            print(f"[调试] 页面上有 {len(elements)} 个元素")
            for i, el in enumerate(elements[:30]):
                try:
                    text = await el.inner_text()
                    if text and len(text) < 100:
                        print(f"[调试] 元素 {i}: {text[:60]}")
                except:
                    pass

            return False, "未能提取到 2FA 密钥", None

        # 7. 点击 Next 继续（多语言）
        next_keywords = ["Next", "Volgende", "下一步", "继续", "Weiter", "Suivant", "Siguiente", "次へ"]
        clicked_next = await _click_action_button(page, next_keywords, log_callback)
        if not clicked_next:
            # 输出对话框内可点击元素，便于排查
            try:
                dialog = await page.query_selector('[role="dialog"]')
                scope = dialog if dialog else page
                elements = await scope.query_selector_all('button, [role="button"], a')
                print(f"[调试] 未点击 Next，当前可点击元素数: {len(elements)}")
                for i, el in enumerate(elements[:15]):
                    try:
                        text = (await el.inner_text())[:40]
                        aria = await el.get_attribute('aria-label')
                        print(f"[调试] 元素 {i}: text='{text}', aria='{aria}'")
                    except Exception:
                        pass
            except Exception:
                pass

        # 7.5 可能需要输入密码验证身份
        try:
            pwd_input = await page.query_selector('input[type="password"]')
            if pwd_input and await pwd_input.is_visible():
                if log_callback:
                    log_callback("正在验证身份...")
                await pwd_input.fill(password)
                await asyncio.sleep(0.5)
                print("[信息] 输入密码验证身份")

                # 点击下一步
                for keyword in next_keywords:
                    next_btn = await page.query_selector(f'button:has-text("{keyword}")')
                    if next_btn and await next_btn.is_visible():
                        await next_btn.click()
                        await asyncio.sleep(5)
                        print(f"[信息] 点击密码确认: {keyword}")
                        break
        except Exception as e:
            print(f"[信息] 密码验证可能已跳过: {e}")

        # 8. 输入验证码确认（图4的最后一步 - 关键！）
        totp = pyotp.TOTP(secret)
        code = totp.now()
        print(f"[信息] 生成验证码: {code}")
        if log_callback:
            log_callback(f"输入验证码: {code}")

        # 等待验证码输入框出现
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector(
                'input[type="tel"], input[inputmode="numeric"], input[autocomplete="one-time-code"]',
                timeout=10000
            )
        except Exception:
            pass
        await _safe_screenshot(page, "debug_before_code_input.png", log_callback)

        # 查找验证码输入框 - 多种选择器
        code_input = None
        code_input_selectors = [
            'input[type="tel"]',
            'input[name*="code"]',
            'input[name*="otp"]',
            'input[name*="totp"]',
            'input[aria-label*="code"]',
            'input[aria-label*="Code"]',
            'input[placeholder*="code"]',
            'input[placeholder*="Code"]',
            'input[inputmode="numeric"]',
            'input[autocomplete="one-time-code"]',
            'input[type="text"]',  # 最后尝试通用文本框
        ]

        for selector in code_input_selectors:
            try:
                inp = await page.query_selector(selector)
                if inp and await inp.is_visible():
                    code_input = inp
                    print(f"[信息] 找到验证码输入框: {selector}")
                    break
            except:
                continue

        if code_input:
            if log_callback:
                log_callback("正在验证新密钥...")
            await code_input.fill(code)
            print(f"[信息] 已填入验证码: {code}")
            await asyncio.sleep(1)

            await _safe_screenshot(page, "debug_after_code_input.png", log_callback)

            # 点击 Next/Verify 按钮完成验证（多语言）
            verify_keywords = [
                "Next", "Volgende", "下一步", "次へ",  # Next 优先
                "Verify", "Verifiëren", "验证",
                "Done", "Klaar", "完成",
                "Confirm", "Bevestigen", "确认", "確認",
                "Turn on", "Inschakelen", "Aanzetten", "开启",  # 可能的最终确认
            ]

            clicked = await _click_action_button(page, verify_keywords, log_callback)
            if not clicked:
                # 尝试回车提交
                try:
                    await code_input.press("Enter")
                    print("[信息] 使用 Enter 提交验证码")
                    clicked = True
                    await asyncio.sleep(3)
                except Exception as e:
                    print(f"[警告] 未找到验证/下一步按钮且回车失败: {e}")
        else:
            print("[警告] 未找到验证码输入框")
            # 打印页面上的输入框用于调试
            all_inputs = await page.query_selector_all('input')
            print(f"[调试] 页面上有 {len(all_inputs)} 个输入框")
            for i, inp in enumerate(all_inputs[:10]):
                try:
                    inp_type = await inp.get_attribute('type')
                    inp_name = await inp.get_attribute('name')
                    inp_visible = await inp.is_visible()
                    print(f"[调试] 输入框 {i}: type={inp_type}, name={inp_name}, visible={inp_visible}")
                except:
                    pass

        await _safe_screenshot(page, "debug_final.png", log_callback)

        # 检查是否设置成功（查看页面是否有成功提示或返回到设置页）
        await asyncio.sleep(2)
        page_url = page.url
        print(f"[信息] 最终页面 URL: {page_url}")

        # 未找到输入框或未能提交验证码，直接判定失败
        if not code_input:
            msg = "未找到验证码输入框，2FA 未完成"
            if log_callback:
                log_callback(f"❌ {msg}")
            return False, msg, None
        if not clicked:
            msg = "未找到验证按钮，2FA 未完成"
            if log_callback:
                log_callback(f"❌ {msg}")
            return False, msg, None

        # 检查是否出现可见的错误提示
        error_pattern = r"wrong code|invalid code|try again|incorrect|code is invalid|couldn't verify"
        try:
            error_loc = page.locator(f'text=/{error_pattern}/i')
            if await error_loc.count() > 0 and await error_loc.first.is_visible():
                msg = "验证码验证失败"
                if log_callback:
                    log_callback(f"❌ {msg}")
                return False, msg, None
        except Exception:
            pass

        # 如果验证码输入框仍可见，视为未完成
        try:
            for selector in code_input_selectors:
                inp = await page.query_selector(selector)
                if inp and await inp.is_visible():
                    msg = "验证码步骤仍在进行，2FA 未完成"
                    if log_callback:
                        log_callback(f"❌ {msg}")
                    return False, msg, None
        except Exception:
            pass

        # 成功提示（toast 或列表状态）
        success_selectors = [
            'text=/Authenticator app has been set up/i',
            'text=/Added just now/i',
            'text=/Authenticator app added/i',
        ]
        for selector in success_selectors:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0 and await loc.first.is_visible():
                    break
            except Exception:
                continue

        ok, status_msg = await _ensure_2sv_enabled(page, secret, password, log_callback)
        if not ok:
            if log_callback:
                log_callback(f"已生成密钥但开启失败: {status_msg}")
            return False, status_msg, secret

        if log_callback:
            log_callback(f"2FA 设置成功! 密钥: {secret}")

        return True, f"2FA 设置成功，{status_msg}", secret

    except Exception as e:
        print(f"[错误] 设置 2FA 异常: {e}")
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


async def setup_2fa(
    browser_id: str,
    log_callback: Optional[Callable] = None,
    close_after: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """为账号设置 2FA"""

    browser_info = get_browser_info(browser_id)
    if not browser_info:
        return False, f"找不到浏览器: {browser_id}", None

    remark = browser_info.get('remark', '')
    parts = remark.split('----')

    account_info = {
        'email': parts[0].strip() if len(parts) > 0 else '',
        'password': parts[1].strip() if len(parts) > 1 else '',
        'backup': parts[2].strip() if len(parts) > 2 else '',
    }
    secret = parts[3].strip() if len(parts) > 3 else ''
    if not secret and account_info['email']:
        account = DBManager.get_account_by_email(account_info['email'])
        if account and account.get('secret_key'):
            secret = account.get('secret_key') or ''
    account_info['secret'] = secret

    if not account_info['email'] or not account_info['password']:
        return False, "账号信息不完整", None

    print(f"[信息] 正在打开浏览器 {browser_id}...")
    res = open_browser(browser_id)

    if not res.get('success'):
        return False, f"无法打开浏览器: {res}", None

    ws_endpoint = res.get('data', {}).get('ws')
    if not ws_endpoint:
        close_browser(browser_id)
        return False, "无法获取 WebSocket 端点", None

    try:
        async with async_playwright() as playwright:
            success, message, new_secret = await setup_2fa_impl(
                playwright, browser_id, account_info, ws_endpoint, log_callback
            )

            if new_secret:
                email = account_info.get('email', 'unknown')
                save_secret_to_file(email, new_secret, browser_id)
                update_browser_2fa(browser_id, new_secret, log_callback)

            return success, message, new_secret
    finally:
        if close_after:
            print(f"[信息] 正在关闭浏览器...")
            close_browser(browser_id)
        else:
            print(f"[信息] 保持浏览器打开: {browser_id}")


def setup_2fa_sync(
    browser_id: str,
    log_callback: Optional[Callable] = None,
    close_after: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """同步版本"""
    return asyncio.run(setup_2fa(browser_id, log_callback, close_after))


if __name__ == "__main__":
    # 测试
    test_browser_id = "65b33437b6834a2d8830400ab3fe7695"

    def print_log(msg: str):
        print(f"[LOG] {msg}")

    print("=" * 50)
    print("Google 2FA 设置测试")
    print("=" * 50)

    success, message, new_secret = setup_2fa_sync(test_browser_id, print_log)

    print()
    print("=" * 50)
    print(f"结果: {'成功' if success else '失败'}")
    print(f"消息: {message}")
    if new_secret:
        print(f"新密钥: {new_secret}")
        totp = pyotp.TOTP(new_secret)
        print(f"当前验证码: {totp.now()}")
    print("=" * 50)
