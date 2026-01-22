"""
任务执行 API
"""
import asyncio
import random
import threading
import uuid
import time
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, BackgroundTasks

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import DBManager
from ..schemas import TaskCreateRequest, TaskType, TaskStatus, TaskProgress, AccountProgressStatus
from ..websocket import get_manager
from .config import get_card_info, get_sheerid_api_key

router = APIRouter()

# 任务状态存储
tasks_store: Dict[str, TaskProgress] = {}

# 任务创建时间记录（用于清理）
_task_timestamps: Dict[str, float] = {}

# 任务存储锁
_tasks_lock = threading.Lock()

# 任务保留时间（秒）：已完成/失败的任务保留 1 小时
TASK_RETENTION_SECONDS = 3600

# 线程池（用于执行阻塞的自动化任务）
executor = ThreadPoolExecutor(max_workers=5)

# 账号进度存储（task_id -> {email -> AccountProgress}）
account_progress_store: Dict[str, Dict[str, dict]] = {}
account_progress_lock = threading.Lock()
browser_lock = threading.Lock()
account_lock = threading.Lock()
account_locks: Dict[str, threading.Lock] = {}


def cleanup_old_tasks() -> int:
    """
    清理过期的任务记录

    Returns:
        清理的任务数量
    """
    now = time.time()
    to_remove = []

    with _tasks_lock:
        for task_id, timestamp in list(_task_timestamps.items()):
            if task_id not in tasks_store:
                to_remove.append(task_id)
                continue

            task = tasks_store[task_id]
            # 只清理已完成或失败的任务
            if task.status in (TaskStatus.completed, TaskStatus.failed):
                if now - timestamp > TASK_RETENTION_SECONDS:
                    to_remove.append(task_id)

        for task_id in to_remove:
            tasks_store.pop(task_id, None)
            _task_timestamps.pop(task_id, None)

    if to_remove:
        print(f"[Task] 已清理 {len(to_remove)} 个过期任务")

    return len(to_remove)


def _is_android_browser(browser: dict) -> bool:
    ostype = (browser.get("ostype") or browser.get("browserFingerPrint", {}).get("ostype") or "").lower()
    os_name = (browser.get("os") or browser.get("browserFingerPrint", {}).get("os") or "").lower()
    return "android" in ostype or "android" in os_name


def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _extract_email_from_remark(remark: str) -> str:
    if not remark:
        return ""
    remark = remark.strip()
    for sep in ("----", "---", "|", ",", ";", "\t"):
        if sep in remark:
            return remark.split(sep)[0].strip().lower()
    parts = remark.split()
    return parts[0].strip().lower() if parts else ""


def _browser_matches_email(browser: dict, email: str) -> bool:
    target = _normalize_email(email)
    if not target or not browser:
        return False
    user = _normalize_email(browser.get("userName"))
    if user:
        return user == target
    remark_email = _extract_email_from_remark(browser.get("remark") or "")
    return remark_email == target if remark_email else False


def ensure_browser_window(email: str, log_callback=None) -> str | None:
    """
    确保账号有浏览器窗口，如果没有则自动创建

    Args:
        email: 账号邮箱
        log_callback: 日志回调函数

    Returns:
        browser_id 或 None（创建失败时）
    """
    from browser_manager import restore_browser, save_browser_to_db
    from create_window import create_browser_window, get_browser_list, delete_browser_by_id, get_browser_info

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    def _get_active_browser_ids() -> set[str]:
        active_emails = set()
        with account_progress_lock:
            for task_progress in account_progress_store.values():
                for acc_email, info in task_progress.items():
                    if info.get("status") in (
                        AccountProgressStatus.pending.value,
                        AccountProgressStatus.running.value,
                    ):
                        active_emails.add(acc_email)
        active_ids = set()
        for acc_email in active_emails:
            account_row = DBManager.get_account_by_email(acc_email)
            if account_row and account_row.get("browser_id"):
                active_ids.add(account_row["browser_id"])
        return active_ids

    account = DBManager.get_account_by_email(email)
    if not account:
        return None

    with browser_lock:
        browser_id = account.get("browser_id")
        if browser_id:
            existing_info = get_browser_info(browser_id)
            if existing_info:
                if not _browser_matches_email(existing_info, email):
                    _log("关联窗口账号不匹配，已解除关联并重新创建窗口...")
                    DBManager.clear_browser_id(email)
                elif _is_android_browser(existing_info):
                    return browser_id
                else:
                    _log("已有关联窗口为非安卓，正在删除并重新创建安卓窗口...")
                    try:
                        delete_browser_by_id(browser_id)
                    except Exception:
                        pass
                    DBManager.clear_browser_id(email)
            else:
                DBManager.clear_browser_id(email)

        restored_id = restore_browser(email)
        if restored_id:
            restored_info = get_browser_info(restored_id)
            if restored_info:
                if not _browser_matches_email(restored_info, email):
                    _log("恢复的窗口账号不匹配，继续创建安卓窗口...")
                    DBManager.clear_browser_id(email)
                elif _is_android_browser(restored_info):
                    return restored_id
                else:
                    _log("恢复的窗口为非安卓，继续创建安卓窗口...")
                    try:
                        delete_browser_by_id(restored_id)
                    except Exception:
                        pass
                    DBManager.clear_browser_id(email)
            else:
                DBManager.clear_browser_id(email)

        # 没有窗口，需要创建
        _log("账号没有浏览器窗口，正在自动创建...")

        # 检查窗口数量限制（比特浏览器免费版限制 10 个窗口）
        MAX_WINDOWS = 10  # 可根据用户配额调整
        browsers = get_browser_list(page=0, pageSize=1000)

        if len(browsers) >= MAX_WINDOWS:
            active_ids = _get_active_browser_ids()
            candidates = [b for b in browsers if b.get('id') not in active_ids]
            if not candidates:
                _log(f"窗口数量已满({len(browsers)}/{MAX_WINDOWS})，且无可安全删除窗口")
                return None
            sorted_browsers = sorted(candidates, key=lambda b: b.get('seq', 0))
            oldest = sorted_browsers[0]
            oldest_id = oldest.get('id')
            oldest_name = oldest.get('userName', oldest.get('name', 'unknown'))
            oldest_email = oldest.get('userName')

            _log(f"窗口数量已满({len(browsers)}/{MAX_WINDOWS})，删除最旧窗口: {oldest_name}")

            if oldest_id:
                delete_browser_by_id(oldest_id)
                if oldest_email:
                    DBManager.clear_browser_id(oldest_email)

            browsers = get_browser_list(page=0, pageSize=1000)

        if not browsers:
            _log("未找到可用模板窗口，无法创建新窗口")
            return None

        android_templates = [b for b in browsers if _is_android_browser(b)]
        if android_templates:
            template_source = android_templates
            template_browser = sorted(template_source, key=lambda b: b.get('seq', 0))[0]
            device_type = "android"
        else:
            template_browser = random.choice(browsers)
            device_type = "android"
            template_name = template_browser.get('name') or template_browser.get('userName') or template_browser.get('id', '')
            _log(f"未找到安卓模板，随机选择窗口作为模板并强制创建安卓窗口: {template_name}")
        template_id = template_browser.get('id')
        if not template_id:
            _log("模板窗口ID为空，无法创建新窗口")
            return None

        # 创建新窗口
        password = account.get("password") or ""
        recovery_email = account.get("recovery_email") or ""
        secret_key = account.get("secret_key") or ""
        full_line = f"{email}----{password}----{recovery_email}----{secret_key}"

        new_browser_id, error = create_browser_window(
            account={
                "email": email,
                "password": password,
                "backup_email": recovery_email,
                "2fa_secret": secret_key,
                "full_line": full_line,
            },
            reference_browser_id=template_id,
            device_type=device_type,
        )

        if new_browser_id:
            # 更新数据库并保存配置
            save_browser_to_db(email, new_browser_id)
            _log(f"浏览器窗口创建成功: {new_browser_id[:8]}...")
            return new_browser_id

        _log(f"浏览器窗口创建失败: {error}")
        return None


def run_task_sync(task_id: str, task_types: List[TaskType], emails: List[str], close_after: bool, concurrency: int = 1):
    """
    同步执行任务（在线程池中运行）
    支持多任务类型：对每个账号按顺序执行所有选中的任务类型
    支持并行执行：使用 ThreadPoolExecutor 并行处理多个账号
    """
    manager = get_manager()
    unique_emails = list(dict.fromkeys(emails))
    total = len(unique_emails)
    task_priority = {
        TaskType.setup_2fa: 0,
        TaskType.reset_2fa: 0,
        TaskType.age_verification: 1,
        TaskType.get_sheerlink: 2,
        TaskType.bind_card: 3,
    }
    ordered_task_types = [
        t for _idx, t in sorted(
            enumerate(task_types),
            key=lambda item: (task_priority.get(item[1], 99), item[0]),
        )
    ]
    # 用于显示的任务类型（取优先级最高）
    display_task_type = ordered_task_types[0] if ordered_task_types else TaskType.setup_2fa

    # 并发数限制在 1-5 之间
    concurrency = max(1, min(5, concurrency))
    max_workers = min(concurrency, total) if total else concurrency

    # 初始化账号进度
    with account_progress_lock:
        account_progress_store[task_id] = {
            email: {
                "email": email,
                "status": AccountProgressStatus.pending.value,
                "current_task": None,
                "message": None,
            }
        for email in unique_emails
        }

    # 统计计数（线程安全）
    stats_lock = threading.Lock()
    stats = {"completed": 0, "failed": 0}

    # 更新任务状态
    with _tasks_lock:
        tasks_store[task_id] = TaskProgress(
            task_id=task_id,
            task_type=display_task_type,
            status=TaskStatus.running,
            total=total,
            completed=0,
        )

    # 创建独立事件循环线程，用于安全推送 WebSocket 消息（避免嵌套事件循环）
    ws_loop = asyncio.new_event_loop()

    def _run_ws_loop():
        asyncio.set_event_loop(ws_loop)
        ws_loop.run_forever()

    ws_thread = threading.Thread(target=_run_ws_loop, daemon=True)
    ws_thread.start()

    def _submit_ws(coro):
        try:
            future = asyncio.run_coroutine_threadsafe(coro, ws_loop)
            return future
        except Exception as e:
            print(f"[Task] 提交 WebSocket 任务失败: {e}")
            return None

    def send_account_progress(email: str, status: str, current_task: str = None, message: str = None):
        """发送单个账号的进度"""
        # 更新本地存储
        with account_progress_lock:
            if task_id in account_progress_store and email in account_progress_store[task_id]:
                account_progress_store[task_id][email].update({
                    "status": status,
                    "current_task": current_task,
                    "message": message,
                })

        with stats_lock:
            completed = stats["completed"]
            failed = stats["failed"]

        future = _submit_ws(
            manager.send_account_progress(
                task_id=task_id,
                email=email,
                status=status,
                current_task=current_task,
                message=message,
                total=total,
                completed=completed,
                failed=failed,
            )
        )
        if future:
            try:
                future.result(timeout=5)
            except Exception as e:
                print(f"[Task] 发送账号进度失败: {e}")

    def send_overall_progress():
        """发送总体进度"""
        with stats_lock:
            completed = stats["completed"]
            failed = stats["failed"]

        with _tasks_lock:
            if task_id in tasks_store:
                tasks_store[task_id].completed = completed + failed

        future = _submit_ws(
            manager.send_task_progress(
                task_id=task_id,
                task_type=display_task_type.value,
                status="running",
                total=total,
                completed=completed + failed,
                message=f"完成: {completed}, 失败: {failed}",
            )
        )
        if future:
            try:
                future.result(timeout=5)
            except Exception:
                pass

    last_log = {"email": None, "level": None, "message": None}
    log_lock = threading.Lock()

    def send_log(level: str, message: str, email: str = None):
        with log_lock:
            if (
                last_log["email"] == email
                and last_log["level"] == level
                and last_log["message"] == message
            ):
                return
            last_log.update({"email": email, "level": level, "message": message})

        future = _submit_ws(manager.send_log(level, message, email))
        if future:
            try:
                future.result(timeout=5)
            except Exception:
                pass

    ordered_labels = []
    for task_type in ordered_task_types:
        ordered_labels.append({
            TaskType.setup_2fa: "设置2FA",
            TaskType.reset_2fa: "修改2FA",
            TaskType.age_verification: "年龄验证",
            TaskType.get_sheerlink: "获取SheerLink",
            TaskType.bind_card: "绑卡订阅",
        }.get(task_type, task_type.value))
    send_log("info", f"任务顺序: {' > '.join(ordered_labels)} | 并发数: {max_workers}", None)

    def process_single_account(email: str):
        """处理单个账号（在线程池中执行）"""
        send_account_progress(email, AccountProgressStatus.running.value, "初始化", f"正在处理 {email}")
        send_log("info", f"开始处理", email)

        with account_lock:
            if email not in account_locks:
                account_locks[email] = threading.Lock()
            lock = account_locks[email]

        with lock:
            account_success = True
            sheerlink_selected = TaskType.get_sheerlink in ordered_task_types
            sheerlink_verified = False
            try:
                # 对每个账号按顺序执行所有选中的任务类型
                total_tasks = len(ordered_task_types)
                for idx, task_type in enumerate(ordered_task_types):
                    is_last_task = idx == total_tasks - 1
                    task_close_after = close_after if is_last_task else False
                    task_label = {
                        TaskType.setup_2fa: "设置2FA",
                        TaskType.reset_2fa: "修改2FA",
                        TaskType.age_verification: "年龄验证",
                        TaskType.get_sheerlink: "获取SheerLink",
                        TaskType.bind_card: "绑卡订阅",
                    }.get(task_type, task_type.value)

                    send_account_progress(email, AccountProgressStatus.running.value, task_label)
                    send_log("info", f"执行任务: {task_label}", email)

                    # 根据任务类型执行不同的操作
                    if task_type == TaskType.get_sheerlink:
                        result = execute_get_sheerlink(
                            email,
                            log_callback=lambda msg: send_log("info", msg, email),
                            close_after=task_close_after,
                        )
                        if result.get("success"):
                            sheerlink_verified = True
                    elif task_type == TaskType.age_verification:
                        result = execute_age_verification(
                            email,
                            log_callback=lambda msg: send_log("info", msg, email),
                            close_after=task_close_after,
                        )
                    elif task_type == TaskType.setup_2fa:
                        result = execute_setup_2fa(
                            email,
                            log_callback=lambda msg: send_log("info", msg, email),
                            close_after=task_close_after,
                        )
                    elif task_type == TaskType.bind_card:
                        if sheerlink_selected and not sheerlink_verified:
                            wait_seconds = 60
                            poll_interval = 2
                            send_log("info", f"等待 SheerID 验证完成（最长 {wait_seconds}s）", email)
                            deadline = time.time() + wait_seconds
                            last_status = None
                            while time.time() < deadline:
                                account = DBManager.get_account_by_email(email)
                                last_status = (account or {}).get("status")
                                if last_status in ("verified", "subscribed"):
                                    sheerlink_verified = True
                                    break
                                time.sleep(poll_interval)
                            if not sheerlink_verified:
                                result = {
                                    "success": False,
                                    "message": f"SheerID 未验证完成，状态: {last_status or 'unknown'}",
                                }
                            else:
                                result = execute_bind_card(
                                    email,
                                    log_callback=lambda msg: send_log("info", msg, email),
                                    close_after=task_close_after,
                                )
                        else:
                            result = execute_bind_card(
                                email,
                                log_callback=lambda msg: send_log("info", msg, email),
                                close_after=task_close_after,
                            )
                    elif task_type == TaskType.reset_2fa:
                        result = execute_reset_2fa(
                            email,
                            log_callback=lambda msg: send_log("info", msg, email),
                            close_after=task_close_after,
                        )
                    else:
                        result = {"success": False, "message": "未知任务类型"}

                    if result.get("success"):
                        send_log("info", f"{task_label} 完成: {result.get('message', '成功')}", email)
                    else:
                        send_log("error", f"{task_label} 失败: {result.get('message', '未知错误')}", email)
                        account_success = False
                        # 某个任务失败时跳过该账号的后续任务
                        break

                # 所有任务执行完后，根据 close_after 决定是否关闭浏览器
                if close_after:
                    try:
                        from bit_api import closeBrowser
                        from database import DBManager
                        account = DBManager.get_account_by_email(email)
                        if account and account.get("browser_id"):
                            closeBrowser(account["browser_id"])
                            send_log("info", "浏览器已关闭", email)
                    except Exception as e:
                        send_log("warning", f"关闭浏览器失败: {e}", email)

                # 更新账号状态
                if account_success:
                    with stats_lock:
                        stats["completed"] += 1
                    send_account_progress(email, AccountProgressStatus.completed.value, None, "完成")
                else:
                    with stats_lock:
                        stats["failed"] += 1
                    send_account_progress(email, AccountProgressStatus.failed.value, None, "失败")

            except Exception as e:
                send_log("error", f"执行出错: {str(e)}", email)
                with stats_lock:
                    stats["failed"] += 1
                send_account_progress(email, AccountProgressStatus.failed.value, None, str(e))

        # 发送总体进度更新
        send_overall_progress()

    # 先推送初始总进度与账号待处理状态，确保前端立即展示
    send_overall_progress()
    for email in unique_emails:
        send_account_progress(email, AccountProgressStatus.pending.value, "等待中")

    try:
        # 使用 ThreadPoolExecutor 并行执行
        with ThreadPoolExecutor(max_workers=max_workers) as account_executor:
            futures = [account_executor.submit(process_single_account, email) for email in unique_emails]
            # 等待所有任务完成
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"[Task] 账号处理异常: {e}")

        # 任务完成
        with _tasks_lock:
            if task_id in tasks_store:
                tasks_store[task_id].status = TaskStatus.completed
                tasks_store[task_id].completed = total
                tasks_store[task_id].message = f"任务完成 - 成功: {stats['completed']}, 失败: {stats['failed']}"

        future = _submit_ws(
            manager.send_task_progress(
                task_id=task_id,
                task_type=display_task_type.value,
                status="completed",
                total=total,
                completed=total,
                message=f"任务完成 - 成功: {stats['completed']}, 失败: {stats['failed']}",
            )
        )
        if future:
            try:
                future.result(timeout=5)
            except Exception:
                pass

    except Exception as e:
        with _tasks_lock:
            if task_id in tasks_store:
                tasks_store[task_id].status = TaskStatus.failed
                tasks_store[task_id].message = str(e)

        future = _submit_ws(
            manager.send_task_progress(
                task_id=task_id,
                task_type=display_task_type.value,
                status="failed",
                total=total,
                completed=tasks_store[task_id].completed,
                message=str(e),
            )
        )
        if future:
            try:
                future.result(timeout=5)
            except Exception:
                pass
    finally:
        try:
            ws_loop.call_soon_threadsafe(ws_loop.stop)
            ws_thread.join(timeout=2)
        finally:
            ws_loop.close()
        # 清理账号进度存储
        with account_progress_lock:
            account_progress_store.pop(task_id, None)


def execute_get_sheerlink(email: str, log_callback=None, close_after: bool = True) -> dict:
    """执行获取 SheerLink 任务"""
    try:
        from run_playwright_google import process_browser

        # 确保有浏览器窗口
        browser_id = ensure_browser_window(email, log_callback)
        if not browser_id:
            return {"success": False, "message": "账号不存在或无法创建浏览器窗口"}

        api_key = get_sheerid_api_key()

        success, message = process_browser(
            browser_id,
            log_callback=log_callback,
            close_after=close_after,
            sheerid_api_key=api_key,
        )
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


def execute_age_verification(email: str, log_callback=None, close_after: bool = True) -> dict:
    """执行年龄验证任务"""
    try:
        from age_verification import process_age_verification

        # 确保有浏览器窗口
        browser_id = ensure_browser_window(email, log_callback)
        if not browser_id:
            return {"success": False, "message": "账号不存在或无法创建浏览器窗口"}

        # 从配置获取卡信息
        card_info = get_card_info()
        if not card_info.get("number"):
            card_info = None

        success, message = process_age_verification(
            browser_id,
            card_info=card_info,
            log_callback=log_callback,
            close_after=close_after,
        )
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


def execute_setup_2fa(email: str, log_callback=None, close_after: bool = True) -> dict:
    """执行设置 2FA 任务"""
    try:
        from setup_2fa import setup_2fa_sync

        # 确保有浏览器窗口
        browser_id = ensure_browser_window(email, log_callback)
        if not browser_id:
            return {"success": False, "message": "账号不存在或无法创建浏览器窗口"}

        success, message, new_secret = setup_2fa_sync(
            browser_id,
            log_callback=log_callback,
            close_after=close_after,
        )
        if new_secret:
            DBManager.upsert_account(email, secret_key=new_secret)
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


def execute_bind_card(email: str, log_callback=None, close_after: bool = True) -> dict:
    """执行绑卡订阅任务"""
    try:
        from auto_bind_card import bind_card_sync

        # 确保有浏览器窗口
        browser_id = ensure_browser_window(email, log_callback)
        if not browser_id:
            return {"success": False, "message": "账号不存在或无法创建浏览器窗口"}

        # 从配置获取卡信息
        card_info = get_card_info()
        # 如果卡信息不完整，使用 None（让 bind_card_sync 使用默认值）
        if not card_info.get("number"):
            card_info = None

        success, message = bind_card_sync(
            browser_id,
            card_info=card_info,
            log_callback=log_callback,
            close_after=close_after,
        )
        if success:
            DBManager.upsert_account(email, status="subscribed")
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


def execute_reset_2fa(email: str, log_callback=None, close_after: bool = True) -> dict:
    """执行重置 2FA 任务"""
    try:
        from reset_2fa import reset_2fa_sync

        # 确保有浏览器窗口
        browser_id = ensure_browser_window(email, log_callback)
        if not browser_id:
            return {"success": False, "message": "账号不存在或无法创建浏览器窗口"}

        success, message, new_secret = reset_2fa_sync(
            browser_id,
            log_callback=log_callback,
            close_after=close_after,
        )
        if success and new_secret:
            DBManager.upsert_account(email, secret_key=new_secret)
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("")
async def create_task(data: TaskCreateRequest, background_tasks: BackgroundTasks):
    """创建并执行任务"""
    if not data.emails:
        raise HTTPException(status_code=400, detail="请选择至少一个账号")

    if not data.task_types:
        raise HTTPException(status_code=400, detail="请选择至少一个任务类型")

    task_id = str(uuid.uuid4())[:8]
    # 用于显示的任务类型（取第一个）
    display_task_type = data.task_types[0]

    # 初始化任务状态并记录时间戳
    with _tasks_lock:
        tasks_store[task_id] = TaskProgress(
            task_id=task_id,
            task_type=display_task_type,
            status=TaskStatus.pending,
            total=len(data.emails),
            completed=0,
        )
        _task_timestamps[task_id] = time.time()

    # 在线程池中执行任务
    executor.submit(run_task_sync, task_id, data.task_types, data.emails, data.close_after, data.concurrency)

    return {"task_id": task_id, "message": "任务已创建"}


@router.get("")
async def list_tasks():
    """获取所有任务状态"""
    # 每次获取列表时触发清理
    cleanup_old_tasks()
    return list(tasks_store.values())


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务状态"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks_store[task_id]


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """取消任务（仅标记，实际任务可能无法中断）"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    tasks_store[task_id].status = TaskStatus.failed
    tasks_store[task_id].message = "已取消"

    return {"message": "任务已标记为取消"}
