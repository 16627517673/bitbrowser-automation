"""
账号管理 API
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import DBManager
from create_window import get_browser_list
from ..schemas import (
    Account, AccountCreate, AccountUpdate, AccountListResponse,
    AccountStatus, ImportRequest, ExportResponse
)

router = APIRouter()


def _split_account_line(line: str, separator: str) -> List[str]:
    if separator and separator in line:
        parts = line.split(separator)
    else:
        parts = None
        for sep in ['----', '---', '|', ',', ';', '\t']:
            if sep in line:
                parts = line.split(sep)
                break
        if parts is None:
            parts = line.split()
    return [p.strip() for p in parts if p.strip()]


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[AccountStatus] = None,
    search: Optional[str] = None,
):
    """获取账号列表（分页、筛选、搜索）"""
    all_accounts = DBManager.get_all_accounts()

    # 筛选状态
    if status:
        all_accounts = [a for a in all_accounts if a.get("status") == status.value]

    # 搜索邮箱
    if search:
        search_lower = search.lower()
        all_accounts = [a for a in all_accounts if search_lower in a.get("email", "").lower()]

    # 分页
    total = len(all_accounts)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_accounts[start:end]

    try:
        browsers = get_browser_list(page=0, pageSize=1000) or []
        browser_map = {}
        for b in browsers:
            email = (b.get("userName") or "").strip().lower()
            if email and email not in browser_map:
                browser_map[email] = b

        for item in items:
            email = (item.get("email") or "").strip()
            if not email:
                continue
            key = email.lower()
            browser = browser_map.get(key)
            if browser:
                browser_id = browser.get("id")
                if browser_id and item.get("browser_id") != browser_id:
                    DBManager.save_browser_config(email, browser_id, browser)
                item["browser_id"] = browser_id
            else:
                if item.get("browser_id"):
                    DBManager.clear_browser_id(email)
                item["browser_id"] = None
    except Exception:
        pass

    return AccountListResponse(total=total, items=items)


@router.get("/stats")
async def get_stats():
    """获取账号统计信息"""
    all_accounts = DBManager.get_all_accounts()
    stats = {
        "total": len(all_accounts),
        "pending": 0,
        "link_ready": 0,
        "verified": 0,
        "subscribed": 0,
        "ineligible": 0,
        "error": 0,
        "with_browser": 0,
    }

    for account in all_accounts:
        status = account.get("status", "pending")
        if status in stats:
            stats[status] += 1
        if account.get("browser_id"):
            stats["with_browser"] += 1

    return stats


@router.get("/{email}", response_model=Account)
async def get_account(email: str):
    """获取单个账号详情"""
    account = DBManager.get_account_by_email(email)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    return account


@router.post("", response_model=Account)
async def create_account(data: AccountCreate):
    """创建新账号"""
    existing = DBManager.get_account_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="账号已存在")

    DBManager.upsert_account(
        email=data.email,
        password=data.password,
        recovery_email=data.recovery_email,
        secret_key=data.secret_key,
        status="pending"
    )

    return DBManager.get_account_by_email(data.email)


@router.put("/{email}", response_model=Account)
async def update_account(email: str, data: AccountUpdate):
    """更新账号信息"""
    existing = DBManager.get_account_by_email(email)
    if not existing:
        raise HTTPException(status_code=404, detail="账号不存在")

    DBManager.upsert_account(
        email=email,
        password=data.password,
        recovery_email=data.recovery_email,
        secret_key=data.secret_key,
        status=data.status.value if data.status else None,
        message=data.message
    )

    return DBManager.get_account_by_email(email)


@router.delete("/{email}")
async def delete_account(email: str):
    """删除账号"""
    existing = DBManager.get_account_by_email(email)
    if not existing:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 使用数据库连接删除
    from database import lock
    import sqlite3

    with lock:
        conn = DBManager.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE email = ?", (email,))
        conn.commit()
        conn.close()

    return {"message": "删除成功"}


@router.post("/import")
async def import_accounts(data: ImportRequest):
    """批量导入账号"""
    lines = data.content.strip().split("\n")
    imported = 0
    errors = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = _split_account_line(line, data.separator)
        if len(parts) < 1:
            continue

        email = parts[0].strip()
        password = parts[1].strip() if len(parts) > 1 else None
        recovery_email = parts[2].strip() if len(parts) > 2 else None
        secret_key = parts[3].strip() if len(parts) > 3 else None

        try:
            DBManager.upsert_account(
                email=email,
                password=password,
                recovery_email=recovery_email,
                secret_key=secret_key,
                status="pending"
            )
            imported += 1
        except Exception as e:
            errors.append(f"{email}: {str(e)}")

    return {"imported": imported, "errors": errors}


@router.get("/export/all", response_model=ExportResponse)
async def export_accounts(status: Optional[AccountStatus] = None):
    """导出账号"""
    if status:
        accounts = DBManager.get_accounts_by_status(status.value)
    else:
        accounts = DBManager.get_all_accounts()

    lines = []
    for acc in accounts:
        parts = [acc.get("email", "")]
        if acc.get("password"):
            parts.append(acc["password"])
        if acc.get("recovery_email"):
            parts.append(acc["recovery_email"])
        if acc.get("secret_key"):
            parts.append(acc["secret_key"])
        lines.append("----".join(parts))

    return ExportResponse(content="\n".join(lines), count=len(lines))
