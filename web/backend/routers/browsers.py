"""
浏览器管理 API
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import DBManager
from browser_manager import (
    save_browser_to_db,
    delete_browser_keep_config,
    restore_browser,
    sync_existing_browsers,
)
from create_window import (
    get_browser_list,
    get_browser_info,
    create_browser_window,
    delete_browser_by_id,
    open_browser_by_id,
)
from ..schemas import BrowserInfo, BrowserCreateRequest

router = APIRouter()


@router.get("", response_model=List[BrowserInfo])
async def list_browsers():
    """获取所有浏览器窗口列表"""
    browsers = get_browser_list()
    if browsers is None:
        raise HTTPException(status_code=503, detail="无法连接到比特浏览器 API")
    return browsers


@router.get("/sync")
async def sync_browsers():
    """同步浏览器窗口到数据库"""
    count = sync_existing_browsers()
    return {"synced": count}


@router.get("/{browser_id}")
async def get_browser(browser_id: str):
    """获取浏览器详情"""
    info = get_browser_info(browser_id)
    if not info:
        raise HTTPException(status_code=404, detail="浏览器窗口不存在")
    return info


@router.post("")
async def create_browser(data: BrowserCreateRequest):
    """创建新浏览器窗口"""
    # 获取账号信息
    account = DBManager.get_account_by_email(data.email)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 检查是否已有窗口
    existing_id = DBManager.get_browser_id(data.email)
    if existing_id and get_browser_info(existing_id):
        raise HTTPException(status_code=400, detail="账号已有关联的浏览器窗口")

    # 获取模板配置
    template_config = None
    if data.template_browser_id:
        template_config = get_browser_info(data.template_browser_id)

    # 构建账号字典
    account_dict = {
        'email': account['email'],
        'password': account.get('password', ''),
        'backup_email': account.get('recovery_email', ''),
        '2fa_secret': account.get('secret_key', ''),
    }

    # 创建窗口
    browser_id, error = create_browser_window(
        account=account_dict,
        template_config=template_config,
        device_type=data.device_type,
    )

    if not browser_id:
        raise HTTPException(status_code=500, detail=f"创建失败: {error}")

    # 保存到数据库
    save_browser_to_db(data.email, browser_id)

    return {"browser_id": browser_id, "email": data.email}


@router.delete("/{browser_id}")
async def delete_browser(browser_id: str, keep_config: bool = True):
    """删除浏览器窗口"""
    # 查找关联的邮箱
    all_accounts = DBManager.get_all_accounts()
    email = None
    for acc in all_accounts:
        if acc.get("browser_id") == browser_id:
            email = acc["email"]
            break

    if keep_config and email:
        # 保留配置删除
        success = delete_browser_keep_config(email)
    else:
        # 直接删除
        success = delete_browser_by_id(browser_id)
        if success and email:
            DBManager.clear_browser_id(email)

    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    return {"message": "删除成功"}


@router.post("/{browser_id}/open")
async def open_browser(browser_id: str):
    """打开浏览器窗口"""
    result = open_browser_by_id(browser_id)
    if not result:
        raise HTTPException(status_code=500, detail="打开失败")
    return result


@router.post("/restore/{email}")
async def restore_browser_window(email: str):
    """从数据库恢复浏览器窗口"""
    browser_id = restore_browser(email)
    if not browser_id:
        raise HTTPException(status_code=500, detail="恢复失败，可能没有保存的配置")
    return {"browser_id": browser_id, "email": email}


@router.post("/sync-2fa")
async def sync_2fa_to_browsers():
    """批量同步 2FA 密钥到比特浏览器"""
    import sys
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

    from sync_2fa_to_browser import sync_2fa_to_browsers as do_sync

    success, fail, errors = do_sync()
    return {
        "success": success,
        "failed": fail,
        "errors": errors,
        "message": f"同步完成: 成功 {success} 个, 失败 {fail} 个"
    }


@router.post("/batch/create")
async def batch_create_browsers(emails: List[str], device_type: str = "pc"):
    """批量创建浏览器窗口"""
    results = []
    for email in emails:
        try:
            account = DBManager.get_account_by_email(email)
            if not account:
                results.append({"email": email, "success": False, "error": "账号不存在"})
                continue

            existing_id = DBManager.get_browser_id(email)
            if existing_id and get_browser_info(existing_id):
                results.append({"email": email, "success": False, "error": "已有窗口"})
                continue

            account_dict = {
                'email': account['email'],
                'password': account.get('password', ''),
                'backup_email': account.get('recovery_email', ''),
                '2fa_secret': account.get('secret_key', ''),
            }

            browser_id, error = create_browser_window(
                account=account_dict,
                device_type=device_type,
            )

            if browser_id:
                save_browser_to_db(email, browser_id)
                results.append({"email": email, "success": True, "browser_id": browser_id})
            else:
                results.append({"email": email, "success": False, "error": error})
        except Exception as e:
            results.append({"email": email, "success": False, "error": str(e)})

    return {"results": results}
