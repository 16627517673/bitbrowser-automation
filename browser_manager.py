"""
浏览器管理模块
封装指纹浏览器的创建、删除、恢复逻辑
"""
from typing import Optional

from database import DBManager
from create_window import (
    get_browser_info,
    get_browser_list,
    create_browser_window,
    delete_browser_by_id,
)


def save_browser_to_db(email: str, browser_id: str) -> bool:
    """
    获取浏览器配置并保存到数据库

    Args:
        email: 账号邮箱
        browser_id: 浏览器窗口ID

    Returns:
        是否保存成功
    """
    if not email or not browser_id:
        return False

    config = get_browser_info(browser_id)
    if not config:
        print(f"[BrowserManager] 无法获取浏览器配置: {browser_id}")
        return False

    DBManager.save_browser_config(email, browser_id, config)
    return True


def delete_browser_keep_config(email: str) -> bool:
    """
    删除浏览器窗口，但保留配置（用于后续恢复）

    Args:
        email: 账号邮箱

    Returns:
        是否删除成功
    """
    browser_id = DBManager.get_browser_id(email)
    if not browser_id:
        print(f"[BrowserManager] 账号 {email} 没有关联的浏览器窗口")
        return False

    # 删除前先更新一次配置（确保最新）
    save_browser_to_db(email, browser_id)

    # 删除窗口
    success = delete_browser_by_id(browser_id)
    if success:
        # 清除 browser_id，保留 browser_config
        DBManager.clear_browser_id(email)
        print(f"[BrowserManager] 已删除浏览器窗口: {email} ({browser_id})")
        return True
    else:
        print(f"[BrowserManager] 删除浏览器窗口失败: {browser_id}")
        return False


def restore_browser(email: str) -> Optional[str]:
    """
    从数据库恢复浏览器窗口

    Args:
        email: 账号邮箱

    Returns:
        新创建的浏览器窗口ID，失败返回 None
    """
    # 检查是否已有窗口
    existing_id = DBManager.get_browser_id(email)
    if existing_id:
        # 验证窗口是否真实存在
        if get_browser_info(existing_id):
            print(f"[BrowserManager] 账号 {email} 已有窗口: {existing_id}")
            return existing_id
        else:
            # 窗口不存在，清除旧ID
            DBManager.clear_browser_id(email)

    # 数据库无ID时，先检查是否已存在同账号窗口
    try:
        browsers = get_browser_list()
        target = (email or "").strip().lower()
        for browser in browsers or []:
            user = (browser.get("userName") or "").strip().lower()
            if user and user == target:
                browser_id = browser.get("id")
                if browser_id:
                    # 保存配置并绑定ID
                    config = get_browser_info(browser_id) or browser
                    DBManager.save_browser_config(email, browser_id, config)
                    print(f"[BrowserManager] 发现已存在窗口，已重新绑定: {email} -> {browser_id}")
                    return browser_id
    except Exception:
        pass

    # 获取保存的配置
    config = DBManager.get_browser_config(email)
    if not config:
        print(f"[BrowserManager] 账号 {email} 没有保存的浏览器配置")
        return None

    # 获取账号信息
    account = DBManager.get_account_by_email(email)
    if not account:
        print(f"[BrowserManager] 找不到账号: {email}")
        return None

    # 构建账号字典
    account_dict = {
        'email': account['email'],
        'password': account.get('password', ''),
        'backup_email': account.get('recovery_email', ''),
        '2fa_secret': account.get('secret_key', ''),
        'full_line': "----".join(
            [p for p in [
                account.get('email', ''),
                account.get('password', ''),
                account.get('recovery_email', ''),
                account.get('secret_key', ''),
            ] if p]
        ),
    }

    # 使用保存的配置创建新窗口
    device_type = "pc"
    ostype = (config.get('ostype') or config.get('browserFingerPrint', {}).get('ostype') or '').lower()
    if "android" in ostype:
        device_type = "android"

    browser_id, error = create_browser_window(
        account=account_dict,
        template_config=config,
        device_type=device_type,
    )

    if browser_id:
        # 保存新的浏览器ID和配置
        save_browser_to_db(email, browser_id)
        print(f"[BrowserManager] 成功恢复浏览器窗口: {email} -> {browser_id}")
        return browser_id
    else:
        print(f"[BrowserManager] 恢复浏览器窗口失败: {error}")
        return None


def sync_existing_browsers() -> int:
    """
    同步所有现有浏览器窗口到数据库
    遍历比特浏览器中的所有窗口，将配置保存到对应账号

    Returns:
        成功同步的数量
    """
    browsers = get_browser_list()
    if not browsers:
        print("[BrowserManager] 没有找到任何浏览器窗口")
        return 0

    synced = 0
    existing_ids = {b.get('id') for b in browsers if b.get('id')}
    for browser in browsers:
        email = browser.get('userName')
        browser_id = browser.get('id')

        if not email or not browser_id:
            continue

        # 检查数据库中是否有该账号
        account = DBManager.get_account_by_email(email)
        if not account:
            print(f"[BrowserManager] 跳过未知账号: {email}")
            continue

        # 保存配置（优先完整配置）
        config = get_browser_info(browser_id) or browser
        DBManager.save_browser_config(email, browser_id, config)
        synced += 1

    # 清理数据库中已不存在的窗口 ID
    try:
        accounts = DBManager.get_all_accounts()
        cleared = 0
        for acc in accounts:
            acc_browser_id = acc.get("browser_id")
            if acc_browser_id and acc_browser_id not in existing_ids:
                DBManager.clear_browser_id(acc["email"])
                cleared += 1
        if cleared:
            print(f"[BrowserManager] 清理无效 browser_id: {cleared}")
    except Exception:
        pass

    print(f"[BrowserManager] 同步完成，共 {synced} 个窗口")
    return synced


if __name__ == "__main__":
    # 测试：同步现有窗口
    DBManager.init_db()
    sync_existing_browsers()
