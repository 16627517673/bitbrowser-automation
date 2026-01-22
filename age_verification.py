"""
Google 年龄验证自动化
访问 https://myaccount.google.com/age-verification 进行年龄验证
"""
import asyncio
import os
import time
import pyotp
from playwright.async_api import async_playwright, Playwright
from bit_api import openBrowser, closeBrowser
from google_recovery import handle_recovery_email_challenge, detect_manual_verification
from set_language import set_language_to_english
from create_window import get_browser_list, get_browser_info
from database import DBManager
from typing import Callable, Optional, Tuple, Dict

# 年龄验证页面 URL
AGE_VERIFICATION_URL = "https://myaccount.google.com/age-verification?utm_source=p0&pli=1"

def _mask_card(number: str) -> str:
    if not number:
        return "****"
    return f"****{number[-4:]}"

def _normalize_country(value: str) -> str:
    if not value:
        return ""
    val = value.strip()
    if val.upper() in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
        return "United States"
    return val

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

def _load_cards_from_file(file_path: str, default_country: str = "United States") -> list[Dict[str, str]]:
    if not os.path.exists(file_path):
        return []
    cards: list[Dict[str, str]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            number = parts[0]
            exp = ""
            exp_month = ""
            exp_year = ""
            cvv = ""
            idx = 0
            if "/" in parts[1]:
                exp = parts[1]
                cvv = parts[2] if len(parts) > 2 else ""
                idx = 3
            else:
                exp_month = parts[1]
                exp_year = parts[2] if len(parts) > 2 else ""
                cvv = parts[3] if len(parts) > 3 else ""
                idx = 4
            zip_code = parts[idx] if len(parts) > idx else ""
            country = parts[idx + 1] if len(parts) > idx + 1 else default_country
            cards.append({
                "number": number,
                "exp": exp,
                "exp_month": exp_month,
                "exp_year": exp_year,
                "cvv": cvv,
                "zip": zip_code,
                "country": country,
            })
    return cards


def _get_config_card_info() -> Optional[Dict[str, str]]:
    try:
        from database import DBManager
        with DBManager.get_db() as conn:
            cursor = conn.cursor()
            def _get(key: str) -> str:
                cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else ""
            return {
                "number": _get("card_number") or "",
                "exp_month": _get("card_exp_month") or "",
                "exp_year": _get("card_exp_year") or "",
                "cvv": _get("card_cvv") or "",
                "zip": _get("card_zip") or "",
            }
    except Exception:
        return None

async def _has_card_number_input(page) -> bool:
    selectors = [
        'input[autocomplete="cc-number"]',
        'input[aria-label*="Card number"]',
        'input[placeholder*="Card number"]',
        'input[name*="cardnumber"]',
        'input[name*="cardNumber"]',
    ]
    for frame in page.frames:
        for selector in selectors:
            try:
                loc = frame.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
    return False

async def _wait_for_card_inputs(page, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if await _has_card_number_input(page):
            return True
        await asyncio.sleep(0.5)
    return False

def _collect_payment_frames(page) -> list[object]:
    frames = []
    for frame in page.frames:
        url = (frame.url or "").lower()
        name = (frame.name or "").lower()
        if any(k in url for k in ["payments.google.com", "pay.google.com", "buyflow", "instrumentmanager", "payment"]):
            frames.append(frame)
            continue
        if any(k in name for k in ["paymentsmodaliframe", "ucc-"]):
            frames.append(frame)
    return frames

async def _click_add_credit_card(page, log: Callable[[str], None], log_not_found: bool = True) -> bool:
    keywords = [
        "+ Add credit card",
        "Add credit card",
        "Add a credit card",
        "Add card",
        "Add a card",
        "Add payment card",
        "Add payment method",
        "添加信用卡",
        "添加银行卡",
        "添加卡",
        "新增信用卡",
        "新增银行卡",
    ]
    selectors = [
        'button:has-text("Add credit card")',
        '[role="button"]:has-text("Add credit card")',
        'button:has-text("Add card")',
        '[role="button"]:has-text("Add card")',
        'button:has-text("Add payment method")',
        '[role="button"]:has-text("Add payment method")',
        'button[aria-label*="Add credit card"]',
        'button[aria-label*="Add card"]',
        '[role="button"][aria-label*="Add credit card"]',
        '[role="button"][aria-label*="Add card"]',
    ]

    async def try_click_in(scope) -> bool:
        for selector in selectors:
            try:
                loc = scope.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.scroll_into_view_if_needed()
                    await loc.click(force=True)
                    log(f"点击添加信用卡: {selector}")
                    return True
            except Exception:
                continue
        for keyword in keywords:
            try:
                loc = scope.get_by_text(keyword, exact=False).first
                if await loc.count() > 0 and await loc.is_visible():
                    target = await loc.evaluate_handle(
                        """
                        el => {
                          let node = el;
                          while (node && node !== document.body) {
                            if (
                              node.tagName === 'BUTTON' ||
                              node.getAttribute('role') === 'button' ||
                              node.hasAttribute('jsaction') ||
                              node.hasAttribute('data-ur')
                            ) {
                              return node;
                            }
                            node = node.parentElement;
                          }
                          return el;
                        }
                        """
                    )
                    await target.as_element().scroll_into_view_if_needed()
                    try:
                        await target.as_element().click(force=True)
                    except Exception:
                        await scope.evaluate("el => el.click()", target)
                    log(f"点击添加信用卡: {keyword}")
                    return True
            except Exception:
                continue
        return False

    if await try_click_in(page):
        return True
    for frame in _collect_payment_frames(page):
        if await try_click_in(frame):
            return True
    for frame in page.frames:
        if frame != page.main_frame and await try_click_in(frame):
            return True
    if log_not_found:
        log("未找到 Add credit card 按钮")
    return False

async def _click_accept_button(page, log: Callable[[str], None]) -> bool:
    keywords = [
        "Accept",
        "Continue",
        "Verify",
        "Confirm",
        "Submit",
        "Save and submit",
        "Save",
        "同意",
        "继续",
        "确认",
        "提交",
        "保存",
    ]
    for keyword in keywords:
        for scope in [page, *_collect_payment_frames(page)]:
            try:
                btn = scope.locator(f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}")').first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True)
                    log(f"点击按钮: {keyword}")
                    return True
            except Exception:
                continue
    return False

def _find_buyflow_frame(page) -> Optional[object]:
    """优先找付款/年龄验证的 buyflow frame"""
    for frame in page.frames:
        url = (frame.url or "").lower()
        if "payments.google.com" in url or "pay.google.com" in url:
            if any(k in url for k in ["buyflow", "instrumentmanager", "payment", "payments"]):
                return frame
    for frame in page.frames:
        url = (frame.url or "").lower()
        if "payments.google.com" in url or "pay.google.com" in url:
            return frame
    return None

async def _wait_for_buyflow_frame(page, timeout: float = 15.0) -> Optional[object]:
    start = time.time()
    while time.time() - start < timeout:
        frame = _find_buyflow_frame(page)
        if frame:
            return frame
        await asyncio.sleep(0.5)
    return None

async def _select_country_in_frame(page, frame, country_label: str, log: Callable[[str], None]) -> bool:
    async def _first_visible(locator):
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
        return None

    async def _combo_text(combo) -> str:
        try:
            return (await combo.inner_text()).strip()
        except Exception:
            return ""

    async def _is_selected(combo) -> bool:
        text = await _combo_text(combo)
        return country_label.lower() in text.lower()

    async def _click_option() -> bool:
        try:
            listbox = await _first_visible(frame.locator('[role="listbox"]'))
            if listbox:
                option = listbox.locator('[role="option"]').filter(has_text=country_label).first
                if await option.count() > 0 and await option.first.is_visible():
                    await option.first.scroll_into_view_if_needed()
                    await option.first.click(force=True)
                    return True
        except Exception:
            pass

        option = frame.locator('[role="option"]').filter(has_text=country_label).first
        if await option.count() > 0 and await option.first.is_visible():
            await option.first.scroll_into_view_if_needed()
            await option.first.click(force=True)
            return True
        return False

    # 1) native select
    try:
        select = await _first_visible(frame.locator(
            'select[autocomplete="country"], select[aria-label*="Country"], select[aria-label*="Country/region"], select[name*="country"]'
        ))
        if select:
            try:
                await select.select_option(label=country_label)
            except Exception:
                await select.select_option(value=country_label)
            return True
    except Exception:
        pass

    # 1.5) 任意 select 中包含目标国家
    try:
        changed = await frame.evaluate(
            """(country) => {
                const selects = Array.from(document.querySelectorAll('select'));
                for (const sel of selects) {
                    const opts = Array.from(sel.options || []);
                    const target = opts.find(o => (o.textContent || '').trim() === country);
                    if (target) {
                        sel.value = target.value;
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        sel.dispatchEvent(new Event('input', { bubbles: true }));
                        return true;
                    }
                }
                return false;
            }""",
            country_label,
        )
        if changed:
            return True
    except Exception:
        pass

    # 2) custom combobox
    combo_candidates = [
        frame.locator('[role="combobox"][aria-label*="Country"], [role="combobox"][aria-label*="Country/region"]').first,
        frame.locator('[role="button"][aria-haspopup="listbox"][aria-label*="Country"]').first,
    ]
    for combo in combo_candidates:
        try:
            if await combo.count() == 0 or not await combo.first.is_visible():
                continue
            combo = combo.first
            aria_label = (await combo.get_attribute("aria-label")) or ""
            if "country" not in aria_label.lower():
                text_hint = await _combo_text(combo)
                if not any(k in text_hint.lower() for k in ["country", "region", "canada", "united states"]):
                    continue
            if await _is_selected(combo):
                return True
            await combo.scroll_into_view_if_needed()
            await combo.click(force=True)
            await asyncio.sleep(0.5)
            if await _click_option():
                return True
            # 尝试键盘检索
            try:
                await page.keyboard.type(country_label, delay=40)
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.5)
            except Exception:
                pass
            if await _is_selected(combo):
                return True
        except Exception:
            continue

    # 3) label-based fallback
    try:
        label = frame.get_by_text("Country/region", exact=False).first
        if await label.count() > 0 and await label.is_visible():
            parent = label.locator("xpath=..")
            for _ in range(3):
                combo = parent.locator('[role="button"], [role="combobox"]').first
                if await combo.count() > 0 and await combo.is_visible():
                    await combo.click(force=True)
                    await asyncio.sleep(0.5)
                    if await _click_option():
                        return True
                parent = parent.locator("xpath=..")
    except Exception:
        pass

    # 4) JS 兜底点击
    try:
        clicked = await frame.evaluate(
            """(country) => {
                const targets = Array.from(document.querySelectorAll('[role="option"], li, div'));
                for (const el of targets) {
                    const text = (el.textContent || '').trim();
                    if (text === country) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
            }""",
            country_label,
        )
        if clicked:
            return True
    except Exception:
        pass

    return False

async def _fill_card_form(page, card_info: Dict[str, str], log: Callable[[str], None]) -> bool:
    """尝试填写信用卡验证表单"""
    if not card_info:
        return False
    if isinstance(card_info, list):
        for idx, info in enumerate(card_info, start=1):
            if not isinstance(info, dict):
                continue
            log(f"尝试第 {idx} 张卡...")
            ok = await _fill_card_form(page, info, log)
            if ok:
                return True
            await asyncio.sleep(2)
        return False

    number = card_info.get("number", "")
    exp_month = card_info.get("exp_month", "")
    exp_year = card_info.get("exp_year", "")
    exp = card_info.get("exp", "")
    cvv = card_info.get("cvv", "")
    zip_code = card_info.get("zip", "")
    cardholder = card_info.get("name", "") or card_info.get("cardholder", "")
    address = card_info.get("address", "")
    city = card_info.get("city", "")
    state = card_info.get("state", "")
    country = card_info.get("country", "")

    if card_info.get("full_address"):
        address = card_info.get("address", address)
        city = card_info.get("city", city)
        state = card_info.get("state", state)
        country = card_info.get("country", country)

    log(f"尝试填写卡信息: {_mask_card(number)}")

    if exp and (not exp_month or not exp_year):
        parts = exp.replace("-", "/").split("/")
        if len(parts) >= 2:
            exp_month = parts[0].strip()
            exp_year = parts[1].strip()[-2:]
    exp_month, exp_year = _normalize_exp_parts(exp_month, exp_year)

    try:
        async def select_country(value: str) -> bool:
            country_label = _normalize_country(value)
            if not country_label:
                return False
            buyflow_frame = await _wait_for_buyflow_frame(page)
            frames = []
            if buyflow_frame:
                frames.append(buyflow_frame)
            for f in page.frames:
                if f not in frames:
                    frames.append(f)
            for frame in frames:
                if await _select_country_in_frame(page, frame, country_label, log):
                    return True
            return False

        try:
            await page.wait_for_selector(
                'input[aria-label*="Card number"], input[autocomplete="cc-number"], iframe[title*="card number" i]',
                timeout=10000,
            )
        except Exception:
            pass

        async def collect_frames():
            frames = []
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                name = frame.name or ""
                url = frame.url or ""
                title = ""
                aria = ""
                name_attr = ""
                try:
                    frame_el = await frame.frame_element()
                    if frame_el:
                        title = (await frame_el.get_attribute("title")) or ""
                        aria = (await frame_el.get_attribute("aria-label")) or ""
                        name_attr = (await frame_el.get_attribute("name")) or ""
                except Exception:
                    pass
                meta = f"{name} {name_attr} {title} {aria} {url}".lower()
                frames.append((frame, meta))
            return frames

        def pick_frame(frames, keywords: list[str]):
            for frame, meta in frames:
                if any(k in meta for k in keywords):
                    return frame
            return None

        async def find_locator(selector: str):
            for frame in page.frames:
                try:
                    loc = frame.locator(selector).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return loc
                except Exception:
                    continue
            return None

        last_filled_input = None
        async def safe_fill(loc, value: str, verify: bool = False) -> bool:
            """填写输入框，可选验证"""
            nonlocal last_filled_input
            if not value:
                return False

            async def get_input_value() -> str:
                """获取输入框当前值（去除空格）"""
                try:
                    current = await loc.input_value()
                    return current.replace(" ", "").replace("-", "")
                except Exception:
                    return ""

            async def do_fill() -> bool:
                try:
                    await loc.click(force=True)
                    await asyncio.sleep(0.1)
                    # 先清空
                    await loc.fill("")
                    await asyncio.sleep(0.1)
                    await loc.fill(value)
                    return True
                except Exception:
                    return False

            async def do_type() -> bool:
                try:
                    await loc.click(force=True)
                    await asyncio.sleep(0.1)
                    # 清空现有内容
                    await loc.press("Control+a")
                    await asyncio.sleep(0.05)
                    await loc.press("Backspace")
                    await asyncio.sleep(0.1)
                    # 逐字符输入，delay 更长以确保稳定
                    await loc.type(value, delay=80)
                    return True
                except Exception:
                    return False

            # 第一次尝试 fill
            if await do_fill():
                last_filled_input = loc
                if verify:
                    await asyncio.sleep(0.3)
                    current = await get_input_value()
                    expected = value.replace(" ", "").replace("-", "")
                    if current == expected:
                        return True
                    log(f"[验证] 输入不完整: 期望 {len(expected)} 位，实际 {len(current)} 位，重试...")
                else:
                    return True

            # 第二次尝试 type
            if await do_type():
                last_filled_input = loc
                if verify:
                    await asyncio.sleep(0.3)
                    current = await get_input_value()
                    expected = value.replace(" ", "").replace("-", "")
                    if current == expected:
                        return True
                    log(f"[验证] 输入仍不完整: 期望 {len(expected)} 位，实际 {len(current)} 位")
                else:
                    return True

            return False

        filled_any = False
        filled_number = False
        filled_exp = False
        filled_cvv = False

        target_country = _normalize_country(country) or "United States"
        if not await _has_card_number_input(page):
            clicked_add = await _click_add_credit_card(page, log)
            if clicked_add:
                await _wait_for_card_inputs(page, timeout=10.0)

        if target_country:
            selected = await select_country(target_country)
            if selected:
                log(f"已选择国家: {target_country}")
                await asyncio.sleep(2.5)
                # 某些流程切换国家后会重置表单，需要等待并再次点击 Add credit card
                for _ in range(3):
                    clicked_add = await _click_add_credit_card(page, log, log_not_found=False)
                    if clicked_add:
                        if await _wait_for_card_inputs(page, timeout=10.0):
                            break
                    if await _has_card_number_input(page):
                        break
                    await asyncio.sleep(1)
            else:
                log(f"未能切换国家，继续尝试填写卡信息")

        frames = await collect_frames()
        card_frame = pick_frame(frames, ["card number", "cardnumber", "cc-number", "card_number", "cardnumberinput"])
        exp_frame = pick_frame(frames, ["expiration", "expiry", "exp", "mm/yy", "expinput"])
        cvv_frame = pick_frame(frames, ["security code", "cvc", "cvv", "csc"])

        buyflow_frame = await _wait_for_buyflow_frame(page)
        preferred_frames = []
        if buyflow_frame:
            preferred_frames.append(buyflow_frame)
        for candidate in (card_frame, exp_frame, cvv_frame):
            if candidate and candidate not in preferred_frames:
                preferred_frames.append(candidate)
        for frame in _collect_payment_frames(page):
            if frame not in preferred_frames:
                preferred_frames.append(frame)
        for frame, _meta in frames:
            if frame not in preferred_frames:
                preferred_frames.append(frame)
        preferred_frames.append(page.main_frame)

        if card_frame:
            try:
                card_input = card_frame.locator('input').first
                if await card_input.count() > 0 and await safe_fill(card_input, number, verify=True):
                    filled_any = True
                    filled_number = True
            except Exception:
                pass

        exp_value = ""
        if exp_month and exp_year:
            exp_value = f"{exp_month}/{exp_year[-2:]}"
        elif exp_month:
            exp_value = exp_month

        if exp_frame and exp_value:
            try:
                exp_input_in_frame = exp_frame.locator('input').first
                if await exp_input_in_frame.count() > 0 and await safe_fill(exp_input_in_frame, exp_value):
                    filled_any = True
                    filled_exp = True
            except Exception:
                pass

        if cvv_frame:
            try:
                cvv_input_in_frame = cvv_frame.locator('input').first
                if await cvv_input_in_frame.count() > 0 and await safe_fill(cvv_input_in_frame, cvv):
                    filled_any = True
                    filled_cvv = True
            except Exception:
                pass

        label_fields = [
            ("Card number", number, "number"),
            ("MM/YY", exp_value, "exp"),
            ("Expiration", exp_value, "exp"),
            ("Security code", cvv, "cvv"),
        ]
        for label, value, field_type in label_fields:
            if not value:
                continue
            try:
                loc = page.get_by_label(label, exact=False).first
                if await loc.count() > 0 and await loc.is_visible():
                    if await safe_fill(loc, value):
                        filled_any = True
                        if field_type == "number":
                            filled_number = True
                        elif field_type == "exp":
                            filled_exp = True
                        elif field_type == "cvv":
                            filled_cvv = True
            except Exception:
                continue

        number_input = await find_locator(
            'input[autocomplete="cc-number"], input[aria-label*="Card number"], input[placeholder*="Card number"], input[name*="cardnumber"], input[name*="cardNumber"]'
        )
        if number_input:
            if await safe_fill(number_input, number, verify=True):
                filled_any = True
                filled_number = True

        exp_input = await find_locator(
            'input[autocomplete="cc-exp"], input[aria-label*="Expiry"], input[aria-label*="Expiration"], input[placeholder*="MM"], input[name*="exp"]'
        )
        if exp_input and exp_value:
            if await safe_fill(exp_input, exp_value):
                filled_any = True
                filled_exp = True

        cvv_input = await find_locator(
            'input[autocomplete="cc-csc"], input[aria-label*="CVC"], input[aria-label*="Security"], input[placeholder*="Security"], input[name*="cvc"], input[name*="cvv"]'
        )
        if cvv_input:
            if await safe_fill(cvv_input, cvv):
                filled_any = True
                filled_cvv = True

        zip_input = await find_locator(
            'input[aria-label*="Billing zip"], input[aria-label*="ZIP"], input[placeholder*="Billing zip"], input[placeholder*="ZIP"], input[autocomplete="postal-code"], input[name*="postal"]'
        )
        if zip_input and zip_code:
            if await safe_fill(zip_input, zip_code):
                filled_any = True

        if zip_input and zip_code and not (filled_number or filled_exp or filled_cvv):
            # 某些场景仅需邮编即可验证
            submit_keywords = [
                "Save and submit", "Save and Submit", "Save", "Continue", "Next", "Verify",
                "Confirm", "Submit", "Pay", "บันทึกและส่ง", "บันทึกและยืนยัน",
            ]
            for keyword in submit_keywords:
                for frame in page.frames:
                    try:
                        btn = frame.locator(f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}")').first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            return True
                    except Exception:
                        continue

        async def find_input_by_keywords(keywords: list[str]):
            for frame, _meta in frames:
                try:
                    inputs = frame.locator('input')
                    count = await inputs.count()
                    for i in range(count):
                        inp = inputs.nth(i)
                        aria = (await inp.get_attribute('aria-label')) or ""
                        placeholder = (await inp.get_attribute('placeholder')) or ""
                        name_attr = (await inp.get_attribute('name')) or ""
                        text = f"{aria} {placeholder} {name_attr}".lower()
                        if any(k in text for k in keywords):
                            return inp
                except Exception:
                    continue
            return None

        if not (filled_number and filled_exp and filled_cvv):
            card_input_kw = await find_input_by_keywords(["card number", "cardnumber", "cc-number"])
            if card_input_kw:
                if await safe_fill(card_input_kw, number, verify=True):
                    filled_any = True
                    filled_number = True
            exp_input_kw = await find_input_by_keywords(["mm/yy", "expiry", "expiration", "exp"])
            if exp_input_kw and exp_value:
                if await safe_fill(exp_input_kw, exp_value):
                    filled_any = True
                    filled_exp = True
            cvv_input_kw = await find_input_by_keywords(["security", "cvc", "cvv"])
            if cvv_input_kw:
                if await safe_fill(cvv_input_kw, cvv):
                    filled_any = True
                    filled_cvv = True

        if not (filled_number and filled_exp and filled_cvv):
            for frame, meta in frames:
                if not any(k in meta for k in ["card", "payment", "instrument", "gpay", "pay.google"]):
                    continue
                try:
                    inputs = frame.locator('input')
                    count = await inputs.count()
                    if count >= 3:
                        labels = []
                        for i in range(min(count, 8)):
                            try:
                                inp = inputs.nth(i)
                                aria = (await inp.get_attribute('aria-label')) or ""
                                placeholder = (await inp.get_attribute('placeholder')) or ""
                                name_attr = (await inp.get_attribute('name')) or ""
                                labels.append((i, f"{aria} {placeholder} {name_attr}".lower()))
                            except Exception:
                                labels.append((i, ""))

                        def _find_index(keywords: list[str]) -> Optional[int]:
                            for idx, text in labels:
                                if any(k in text for k in keywords):
                                    return idx
                            return None

                        number_idx = _find_index(["card number", "number", "cc-number"])
                        exp_idx = _find_index(["mm/yy", "expiry", "expiration", "exp"])
                        cvv_idx = _find_index(["security", "cvc", "cvv"])
                        zip_idx = _find_index(["zip", "postal"])

                        if number_idx is None:
                            number_idx = 0
                        if exp_idx is None:
                            exp_idx = 1 if count > 1 else 0
                        if cvv_idx is None:
                            cvv_idx = 2 if count > 2 else exp_idx

                        if await safe_fill(inputs.nth(number_idx), number, verify=True):
                            filled_any = True
                            filled_number = True
                        if await safe_fill(inputs.nth(exp_idx), exp_value):
                            filled_any = True
                            filled_exp = True
                        if await safe_fill(inputs.nth(cvv_idx), cvv):
                            filled_any = True
                            filled_cvv = True
                        if zip_code and zip_idx is not None:
                            filled_any |= await safe_fill(inputs.nth(zip_idx), zip_code)
                        break
                except Exception:
                    continue
        if not (filled_number and filled_exp and filled_cvv) and frames:
            metas = [meta for _frame, meta in frames]
            log(f"未找到卡号/安全码输入框，frame信息: {' | '.join(metas[:6])}")

        name_input = await find_locator(
            'input[autocomplete="cc-name"], input[aria-label*="Cardholder"], input[placeholder*="Cardholder"], input[placeholder*="Name on card"], input[name*="cardname"]'
        )
        if name_input and cardholder:
            filled_any |= await safe_fill(name_input, cardholder)

        address_input = await find_locator(
            'input[autocomplete="address-line1"], input[aria-label*="Street"], input[placeholder*="Street"], input[name*="address"]'
        )
        if address_input and address:
            filled_any |= await safe_fill(address_input, address)

        city_input = await find_locator(
            'input[autocomplete="address-level2"], input[aria-label*="City"], input[placeholder*="City"], input[name*="city"]'
        )
        if city_input and city:
            filled_any |= await safe_fill(city_input, city)

        state_input = await find_locator(
            'input[autocomplete="address-level1"], input[aria-label*="State"], input[placeholder*="State"], input[name*="state"]'
        )
        if state_input and state:
            filled_any |= await safe_fill(state_input, state)

        zip_input = await find_locator(
            'input[autocomplete="postal-code"], input[aria-label*="ZIP"], input[placeholder*="ZIP"], input[name*="postal"]'
        )
        if zip_input and zip_code:
            filled_any |= await safe_fill(zip_input, zip_code)

        if country:
            for frame in page.frames:
                try:
                    select = frame.locator('select[autocomplete="country"], select[aria-label*="Country"], select[name*="country"]').first
                    if await select.count() > 0 and await select.is_visible():
                        try:
                            await select.select_option(label=country)
                        except Exception:
                            await select.select_option(value=country)
                        filled_any = True
                        break
                except Exception:
                    continue

        if not filled_any:
            return False

        # 提交
        async def _card_error_detected() -> bool:
            error_text_selector = (
                'text=/declined|invalid|try another|try a different|could not|cannot|not accepted|failed|unable to|'
                'problem with your card|card was declined|已拒绝|无效|失败/i'
            )
            try:
                for f in preferred_frames:
                    loc = f.locator(error_text_selector).first
                    if await loc.count() > 0 and await loc.is_visible():
                        log("检测到卡片错误提示，准备尝试其他卡")
                        return True
            except Exception:
                pass
            return False

        await asyncio.sleep(0.5)
        submit_keywords = [
            "Save and submit", "Save and Submit", "Save", "Continue", "Next", "Verify",
            "Confirm", "Submit", "Pay", "บันทึกและส่ง", "บันทึกและยืนยัน",
        ]
        clicked_submit = False
        for keyword in submit_keywords:
            for frame in preferred_frames:
                try:
                    btn = frame.locator(
                        f'button:has-text("{keyword}"), [role="button"]:has-text("{keyword}"), '
                        f'input[type="submit"][value*="{keyword}"]'
                    ).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(force=True)
                        log(f"点击提交按钮: {keyword}")
                        await asyncio.sleep(3)
                        if await _card_error_detected():
                            return False
                        clicked_submit = True
                        break
                except Exception:
                    continue
            if clicked_submit:
                return True

        if not clicked_submit:
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                '[role="button"][type="submit"]',
            ]
            for frame in preferred_frames:
                for selector in submit_selectors:
                    try:
                        btn = frame.locator(selector).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.scroll_into_view_if_needed()
                            await btn.click(force=True)
                            log(f"点击提交按钮: {selector}")
                            await asyncio.sleep(3)
                            if await _card_error_detected():
                                return False
                            return True
                    except Exception:
                        continue

        if not clicked_submit and last_filled_input:
            try:
                await last_filled_input.press("Enter")
                await asyncio.sleep(3)
                if await _card_error_detected():
                    return False
                return True
            except Exception:
                pass
    except Exception as e:
        log(f"填写卡信息失败: {e}")
        return False

    return True


async def _automate_age_verification(
    playwright: Playwright,
    browser_id: str,
    account_info: dict,
    card_info: Optional[Dict[str, str]],
    ws_endpoint: str,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    自动化年龄验证流程

    Args:
        playwright: Playwright 实例
        browser_id: 浏览器 ID
        account_info: 账户信息 (email, password, secret)
        ws_endpoint: WebSocket 端点
        log_callback: 日志回调函数

    Returns:
        (success, message)
    """
    chromium = playwright.chromium

    def log(msg: str) -> None:
        print(msg)
        if log_callback:
            log_callback(msg)

    browser = None
    try:
        browser = await chromium.connect_over_cdp(ws_endpoint)
        default_context = browser.contexts[0]
        page = default_context.pages[0] if default_context.pages else await default_context.new_page()

        log("浏览器预热中...")
        await asyncio.sleep(2)

        # 先检查是否需要登录
        log("正在访问 Google 账户...")
        try:
            await page.goto('https://accounts.google.com', timeout=60000)
        except Exception as e:
            log(f"导航失败: {e}")

        # 检查是否需要登录
        email = account_info.get('email', '')
        try:
            email_input = await page.wait_for_selector('input[type="email"]', timeout=5000)
            if email_input:
                log(f"正在输入账号: {email}")
                await email_input.fill(email)
                await page.click('#identifierNext >> button')

                # 输入密码
                log("等待密码输入...")
                await page.wait_for_selector('input[type="password"]', state='visible', timeout=10000)
                password = account_info.get('password', '')
                log("正在输入密码...")
                await page.fill('input[type="password"]', password)
                await page.click('#passwordNext >> button')

                # 处理 2FA
                log("检查 2FA...")
                try:
                    totp_input = await page.wait_for_selector(
                        'input[name="totpPin"], input[id="totpPin"], input[type="tel"]',
                        timeout=10000
                    )
                    if totp_input:
                        secret = account_info.get('secret', '')
                        if secret:
                            s = secret.replace(" ", "").strip()
                            totp = pyotp.TOTP(s)
                            code = totp.now()
                            log(f"正在输入 2FA 验证码: {code}")
                            await totp_input.fill(code)
                            await page.click('#totpNext >> button')
                        else:
                            backup = account_info.get('backup')
                            handled = await handle_recovery_email_challenge(page, backup, log_callback)
                            if not handled:
                                log("未找到 2FA 密钥")
                except Exception as e:
                    log(f"2FA 步骤跳过或不同的验证方式: {e}")

                # 辅助邮箱验证
                try:
                    backup = account_info.get('backup')
                    await handle_recovery_email_challenge(page, backup, log_callback)
                    if await detect_manual_verification(page):
                        log("需要人工完成验证码")
                        return False, "需要人工完成验证码"
                except Exception:
                    pass

        except Exception as e:
            log(f"可能已登录或登录流程变化: {e}")

        await asyncio.sleep(3)

        # 设置语言为英文（无 2FA 账号也需要）
        try:
            log("正在设置语言为英文...")
            lang_ok, lang_msg = await set_language_to_english(
                page,
                password=account_info.get('password', ''),
                backup_email=account_info.get('backup', ''),
            )
            if not lang_ok:
                backup = account_info.get('backup', '')
                handled = await handle_recovery_email_challenge(page, backup, log_callback)
                if handled:
                    await asyncio.sleep(2)
                    lang_ok, lang_msg = await set_language_to_english(
                        page,
                        password=account_info.get('password', ''),
                        backup_email=account_info.get('backup', ''),
                    )
            if not lang_ok and await detect_manual_verification(page):
                return False, "需要人工完成验证码"
            if lang_ok:
                log(f"✅ {lang_msg}")
            else:
                log(f"⚠️ 语言设置: {lang_msg}")
        except Exception as e:
            log(f"⚠️ 语言设置失败: {e}")

        # 导航到年龄验证页面
        log(f"正在访问年龄验证页面...")
        try:
            await page.goto(AGE_VERIFICATION_URL, timeout=60000)
        except Exception as e:
            log(f"年龄验证页面导航失败: {e}")
            return False, f"导航失败: {e}"

        await asyncio.sleep(3)

        # 检查页面状态
        log("正在检查年龄验证状态...")

        # 已验证的标志文本（多语言）
        verified_phrases = [
            "You're all set",
            "You're all set",  # 使用普通撇号
            "You are all set",
            "all set",
            "Your age has been verified",
            "age has been verified",
            "Age verified",
            "您的年龄已验证",
            "你的年齡已驗證",
            "Tuổi của bạn đã được xác minh",
            "Bạn đã hoàn tất",
            "Usia Anda telah diverifikasi",
            "Su edad ha sido verificada",
            "Votre âge a été vérifié",
            "Xong",
            "完成",
            "已完成",
        ]

        # 需要验证的标志文本
        need_verify_phrases = [
            "Verify your age",
            "Confirm your age",
            "Age verification required",
            "验证您的年龄",
            "确认您的年龄",
            "驗證你的年齡",
            "確認你的年齡",
            "Xác minh tuổi của bạn",
            "Xác nhận tuổi của bạn",
            "Verifikasi usia Anda",
            "Konfirmasi usia Anda",
            "Verifica tu edad",
            "Confirma tu edad",
            "Vérifiez votre âge",
            "Confirmez votre âge",
        ]

        start_time = time.time()
        max_wait = 15  # 最大等待时间
        need_verify_found = False
        need_verify_logged = False

        while time.time() - start_time < max_wait:
            # 获取页面文本内容进行匹配
            try:
                page_content = await page.content()
                page_text = await page.inner_text('body')
            except Exception:
                page_text = ""

            # 检查是否已验证
            for phrase in verified_phrases:
                if phrase.lower() in page_text.lower():
                    log(f"年龄已验证: {phrase}")
                    return True, "年龄已验证"

            # 检查是否需要验证
            for phrase in need_verify_phrases:
                if phrase.lower() in page_text.lower():
                    if not need_verify_logged:
                        log(f"需要年龄验证: {phrase}")
                        need_verify_logged = True
                    # 尝试查找并点击验证按钮
                    try:
                        buttons = page.locator('button, [role="button"]')
                        count = await buttons.count()
                        for i in range(count):
                            btn = buttons.nth(i)
                            text = await btn.inner_text()
                            text_lower = text.lower()
                            if any(kw in text_lower for kw in ['continue', 'verify', '继续', '验证', 'tiếp tục', 'lanjutkan']):
                                log(f"点击按钮: {text}")
                                await btn.click()
                                await asyncio.sleep(2)
                                break
                    except Exception as e:
                        log(f"点击按钮失败: {e}")
                    need_verify_found = True
                    break

            if need_verify_found:
                break

        # 检查是否有验证方式选择页面（信用卡/身份证）
        # 优先选择信用卡验证
        card_verify_phrases = [
            "Verify with payment card",
            "Verify with credit card",
            "payment card",
            "credit card", "debit card",
            "credit_card",
            "ใช้บัตรเครดิต",
            "บัตรเครดิต",
            "บัตรเดบิต",
            "Xác minh bằng thẻ thanh toán",  # 越南语
            "thẻ thanh toán",
            "tarjeta de pago",  # 西班牙语
            "carte de paiement",  # 法语
            "使用付款卡验证",
            "信用卡", "银行卡", "支付卡",
        ]
        for phrase in card_verify_phrases:
            try:
                # 使用 get_by_text 进行更灵活的匹配
                card_option = page.get_by_text(phrase, exact=False).first
                if await card_option.is_visible():
                    log(f"检测到信用卡验证选项: {phrase}")
                    try:
                        target = await card_option.evaluate_handle(
                            'el => el.closest(\"button, [role=button], [role=listitem], div, li\")'
                        )
                        if target:
                            await target.as_element().click(force=True)
                        else:
                            await card_option.click()
                    except Exception:
                        await card_option.click()
                    await asyncio.sleep(3)
                    if card_info:
                        filled = await _fill_card_form(page, card_info, log)
                        if filled:
                            log("已尝试提交卡片验证")
                            await asyncio.sleep(2)
                            await _click_accept_button(page, log)
                            await asyncio.sleep(2)
                    break
            except Exception:
                pass

            # 检查是否有日期输入（出生日期验证）
            date_input = page.locator('input[type="date"], input[aria-label*="birth"], input[aria-label*="出生"]')
            if await date_input.count() > 0:
                log("检测到出生日期输入框，需要手动输入出生日期")
                return False, "需要手动输入出生日期"

            # 检查是否有身份证件上传
            upload_input = page.locator('input[type="file"]')
            if await upload_input.count() > 0:
                log("检测到文件上传，需要上传身份证件")
                return False, "需要上传身份证件"

            await asyncio.sleep(1)

        # 超时 - 截图保存
        screenshot_path = f"age_verification_timeout_{browser_id}.png"
        await page.screenshot(path=screenshot_path)
        log(f"超时，截图已保存: {screenshot_path}")
        return False, "超时，未能确定验证状态"

    except Exception as e:
        log(f"自动化过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False, f"错误: {str(e)}"
    finally:
        # 确保断开 CDP 连接，释放资源
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


async def _async_process_wrapper(
    browser_id: str,
    account_info: dict,
    card_info: Optional[Dict[str, str]],
    ws_endpoint: str,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    async with async_playwright() as playwright:
        return await _automate_age_verification(playwright, browser_id, account_info, card_info, ws_endpoint, log_callback)


def process_age_verification(
    browser_id: str,
    card_info: Optional[Dict[str, str]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    close_after: bool = False,
) -> Tuple[bool, str]:
    """
    处理单个浏览器的年龄验证

    Args:
        browser_id: 浏览器窗口 ID
        log_callback: 日志回调函数

    Returns:
        (success, message)
    """
    print(f"获取浏览器信息: {browser_id}")

    if not card_info or (isinstance(card_info, dict) and not card_info.get("number")):
        config_card = _get_config_card_info()
        if config_card and config_card.get("number"):
            card_info = config_card
            print(f"使用配置卡用于年龄验证: {_mask_card(config_card.get('number', ''))}")

    if card_info is None:
        cards_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.txt")
        cards = _load_cards_from_file(cards_path)
        if cards:
            card_info = cards
            print(f"已加载 {len(cards)} 张卡用于年龄验证")

    target_browser = get_browser_info(browser_id)
    if not target_browser:
        print(f"直接获取失败，尝试列表搜索...")
        browsers = get_browser_list(page=0, pageSize=1000)
        for b in browsers:
            if b.get('id') == browser_id:
                target_browser = b
                break

    if not target_browser:
        return False, f"未找到浏览器: {browser_id}"

    # 解析账户信息
    account_info: dict[str, str] = {}
    remark = target_browser.get('remark', '')
    parts = remark.split('----')
    if len(parts) >= 4:
        account_info = {
            'email': parts[0].strip(),
            'password': parts[1].strip(),
            'backup': parts[2].strip(),
            'secret': parts[3].strip()
        }
    elif len(parts) >= 1:
        account_info['email'] = parts[0].strip()
        if len(parts) >= 2:
            account_info['password'] = parts[1].strip()

    if not account_info.get('email'):
        user_name = target_browser.get('userName') or ""
        if "@" in user_name:
            account_info['email'] = user_name.strip()

    if not account_info.get('secret'):
        browser_secret = target_browser.get('faSecretKey') or ""
        if browser_secret:
            account_info['secret'] = browser_secret.strip()

    # 优先补齐 DB 内的最新信息（setup 2FA 后可能更新了 secret）
    if account_info.get('email'):
        db_account = DBManager.get_account_by_email(account_info['email'])
        if db_account:
            if not account_info.get('password'):
                account_info['password'] = db_account.get('password') or ""
            if not account_info.get('backup'):
                account_info['backup'] = db_account.get('recovery_email') or ""
            db_secret = db_account.get('secret_key')
            if db_secret:
                account_info['secret'] = db_secret

    print(f"打开浏览器 {browser_id}...")
    res = openBrowser(browser_id)
    if not res or not res.get('success', False):
        return False, f"打开浏览器失败: {res}"

    ws_endpoint = res.get('data', {}).get('ws')
    if not ws_endpoint:
        closeBrowser(browser_id)
        return False, "未获取到 WebSocket 端点"

    try:
        result = asyncio.run(_async_process_wrapper(browser_id, account_info, card_info, ws_endpoint, log_callback))
        return result
    finally:
        if close_after:
            print(f"关闭浏览器 {browser_id}...")
            closeBrowser(browser_id)
        else:
            print(f"保持浏览器打开: {browser_id}")


if __name__ == "__main__":
    # 测试用
    import sys
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
    else:
        # 默认获取第一个浏览器
        browsers = get_browser_list()
        if browsers:
            test_id = browsers[0].get('id')
            print(f"使用第一个浏览器: {test_id}")
        else:
            print("未找到浏览器窗口")
            sys.exit(1)

    success, msg = process_age_verification(test_id)
    print(f"结果: {success} - {msg}")
