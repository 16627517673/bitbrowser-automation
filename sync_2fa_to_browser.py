"""
批量同步 2FA 密钥到比特浏览器

从数据库读取账号的 2FA 密钥，同步更新到比特浏览器的 faSecretKey 字段
"""
import requests
from typing import List, Tuple

from database import DBManager

# 比特浏览器 API
BIT_API_URL = "http://127.0.0.1:54345"
BIT_HEADERS = {'Content-Type': 'application/json'}
NO_PROXY = {'http': None, 'https': None}


def get_no_proxy_session() -> requests.Session:
    """获取不使用代理的 requests session"""
    session = requests.Session()
    session.trust_env = False
    return session


def get_all_browsers() -> List[dict]:
    """获取所有比特浏览器窗口"""
    session = get_no_proxy_session()
    try:
        res = session.post(
            f"{BIT_API_URL}/browser/list",
            json={"page": 0, "pageSize": 1000},
            headers=BIT_HEADERS,
            timeout=10,
            proxies=NO_PROXY
        ).json()

        if res.get('success') or res.get('code') == 0:
            data = res.get('data', {})
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get('list', [])
        return []
    except Exception as e:
        print(f"[错误] 获取浏览器列表失败: {e}")
        return []


def update_browser_2fa(browser_id: str, secret_key: str, remark: str) -> bool:
    """更新浏览器的 2FA 密钥和备注"""
    session = get_no_proxy_session()
    try:
        res = session.post(
            f"{BIT_API_URL}/browser/update/partial",
            json={
                'ids': [browser_id],
                'remark': remark,
                'faSecretKey': secret_key
            },
            headers=BIT_HEADERS,
            timeout=10,
            proxies=NO_PROXY
        ).json()
        return res.get('success') or res.get('code') == 0
    except Exception as e:
        print(f"[错误] 更新浏览器 {browser_id} 失败: {e}")
        return False


def build_remark(email: str, password: str, backup_email: str, secret_key: str) -> str:
    """构建备注字符串"""
    parts = [email, password, backup_email, secret_key]
    # 移除末尾的空值
    while parts and not parts[-1]:
        parts.pop()
    return '----'.join(parts)


def sync_2fa_to_browsers() -> Tuple[int, int, List[str]]:
    """
    批量同步 2FA 密钥到比特浏览器

    Returns:
        (成功数, 失败数, 错误信息列表)
    """
    browsers = get_all_browsers()
    if not browsers:
        return 0, 0, ["无法获取浏览器列表或列表为空"]

    success_count = 0
    fail_count = 0
    errors: List[str] = []

    for browser in browsers:
        browser_id = browser.get('id')
        remark = browser.get('remark', '')
        current_fa_key = browser.get('faSecretKey', '')

        if not browser_id or not remark:
            continue

        # 解析 remark 获取邮箱
        parts = remark.split('----')
        if len(parts) < 1:
            continue

        email = parts[0].strip()
        if not email or '@' not in email:
            continue

        # 从数据库获取账号信息
        account = DBManager.get_account_by_email(email)
        if not account:
            continue

        db_secret = account.get('secret_key', '') or ''

        # 如果数据库中没有密钥，跳过
        if not db_secret:
            continue

        # 如果浏览器已有相同密钥，跳过
        if current_fa_key == db_secret:
            print(f"[跳过] {email}: 密钥已同步")
            continue

        # 构建新的 remark
        password = account.get('password', '') or (parts[1].strip() if len(parts) > 1 else '')
        backup_email = account.get('recovery_email', '') or (parts[2].strip() if len(parts) > 2 else '')
        new_remark = build_remark(email, password, backup_email, db_secret)

        # 更新浏览器
        if update_browser_2fa(browser_id, db_secret, new_remark):
            success_count += 1
            print(f"[成功] {email}: 已同步 2FA 密钥")
        else:
            fail_count += 1
            errors.append(f"{email}: 更新失败")

    return success_count, fail_count, errors


def main() -> None:
    print("=" * 50)
    print("批量同步 2FA 密钥到比特浏览器")
    print("=" * 50)

    success, fail, errors = sync_2fa_to_browsers()

    print()
    print("=" * 50)
    print(f"同步完成: 成功 {success} 个, 失败 {fail} 个")
    if errors:
        print("错误信息:")
        for err in errors:
            print(f"  - {err}")
    print("=" * 50)


if __name__ == "__main__":
    main()
