"""
配置管理 API
管理 SheerID API Key 和卡信息等配置
"""
import threading
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import DBManager
from ..schemas import ConfigUpdate, ConfigResponse

router = APIRouter()

# 线程锁，保护配置读写操作
_config_lock = threading.Lock()


def get_config(key: str) -> Optional[str]:
    """从数据库获取配置值（线程安全）"""
    with _config_lock:
        with DBManager.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None


def set_config(key: str, value: str) -> None:
    """设置配置值到数据库（线程安全）"""
    with _config_lock:
        with DBManager.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()


def init_config_table() -> None:
    """初始化配置表"""
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


# 初始化配置表
init_config_table()


@router.get("", response_model=ConfigResponse)
async def get_all_config():
    """获取所有配置"""
    config_keys = [
        "sheerid_api_key",
        "card_number",
        "card_exp_month",
        "card_exp_year",
        "card_cvv",
        "card_zip",
    ]

    result = {}
    for key in config_keys:
        value = get_config(key)
        result[key] = value or ""

    return ConfigResponse(**result)


@router.put("")
async def update_config(data: ConfigUpdate):
    """更新配置"""
    updated = []

    if data.sheerid_api_key is not None:
        set_config("sheerid_api_key", data.sheerid_api_key)
        updated.append("sheerid_api_key")

    if data.card_number is not None:
        set_config("card_number", data.card_number)
        updated.append("card_number")

    if data.card_exp_month is not None:
        set_config("card_exp_month", data.card_exp_month)
        updated.append("card_exp_month")

    if data.card_exp_year is not None:
        set_config("card_exp_year", data.card_exp_year)
        updated.append("card_exp_year")

    if data.card_cvv is not None:
        set_config("card_cvv", data.card_cvv)
        updated.append("card_cvv")

    if data.card_zip is not None:
        set_config("card_zip", data.card_zip)
        updated.append("card_zip")

    return {"message": "配置已更新", "updated": updated}


def get_card_info() -> Dict[str, str]:
    """获取卡信息（供任务执行使用）"""
    return {
        "number": get_config("card_number") or "",
        "exp_month": get_config("card_exp_month") or "",
        "exp_year": get_config("card_exp_year") or "",
        "cvv": get_config("card_cvv") or "",
        "zip": get_config("card_zip") or "",
    }


def get_sheerid_api_key() -> str:
    """获取 SheerID API Key（供任务执行使用）"""
    return get_config("sheerid_api_key") or ""
