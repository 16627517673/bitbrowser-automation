"""
比特浏览器窗口批量创建工具 - PyQt6 GUI版本
支持输入模板窗口ID，批量创建窗口，自动读取accounts.txt和proxies.txt
支持自定义平台URL和额外URL
支持列表显示现有窗口，并支持批量删除
UI布局调整：左侧操作区，右侧日志区
"""
import sys
import os
import threading
import pyotp
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSplitter,
    QAbstractItemView, QSpinBox, QToolBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QIcon
from create_window import (
    read_accounts, read_proxies, get_browser_list, get_browser_info,
    delete_browsers_by_name, delete_browser_by_id, open_browser_by_id, create_browser_window, get_next_window_name
)
from run_playwright_google import process_browser
from age_verification import process_age_verification
from sheerid_verifier import SheerIDVerifier
from setup_2fa import setup_2fa_sync
from auto_bind_card import bind_card_sync
from sheerid_gui import SheerIDWindow
import re

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)




DEFAULT_TEMPLATE_CONFIG = {
  "platform": "",
  "platformIcon": "",
  "url": "",
  "name": "默认模板",
  "userName": "",
  "password": "",
  "cookie": "",
  "otherCookie": "",
  "isGlobalProxyInfo": False,
  "isIpv6": False,
  "proxyMethod": 2,
  "proxyType": "noproxy",
  "ipCheckService": "ip2location",
  "host": "",
  "port": "",
  "proxyUserName": "",
  "proxyPassword": "",
  "enableSocks5Udp": False,
  "isIpNoChange": False,
  "isDynamicIpChangeIp": True,
  "status": 0,
  "isDelete": 0,
  "isMostCommon": 0,
  "isRemove": 0,
  "abortImage": False,
  "abortMedia": False,
  "stopWhileNetError": False,
  "stopWhileCountryChange": False,
  "syncTabs": False,
  "syncCookies": False,
  "syncIndexedDb": False,
  "syncBookmarks": False,
  "syncAuthorization": True,
  "syncHistory": False,
  "syncGoogleAccount": False,
  "allowedSignin": False,
  "syncSessions": False,
  "workbench": "localserver",
  "clearCacheFilesBeforeLaunch": True,
  "clearCookiesBeforeLaunch": False,
  "clearHistoriesBeforeLaunch": False,
  "randomFingerprint": True,
  "muteAudio": False,
  "disableGpu": False,
  "enableBackgroundMode": False,
  "syncExtensions": False,
  "syncUserExtensions": False,
  "syncLocalStorage": False,
  "credentialsEnableService": False,
  "disableTranslatePopup": False,
  "stopWhileIpChange": False,
  "disableClipboard": False,
  "disableNotifications": False,
  "memorySaver": False,
  "isRandomFinger": True,
  "isSynOpen": 1,
  "coreProduct": "chrome",
  "ostype": "PC",
  "os": "Win32",
  "coreVersion": "140"
}

class WorkerThread(QThread):
    """通用后台工作线程"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)  # result data

    def __init__(self, task_type, **kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs
        self.is_running = True

    def stop(self):
        self.is_running = False

    def log(self, message):
        self.log_signal.emit(message)

    def msleep(self, ms):
        """可中断的sleep"""
        t = ms
        while t > 0 and self.is_running:
            time.sleep(0.1)
            t -= 100

    def run(self):
        if self.task_type == 'create':
            self.run_create()
        elif self.task_type == 'delete':
            self.run_delete()
        elif self.task_type == 'open':
            self.run_open()
        elif self.task_type == '2fa':
            self.run_2fa()
        elif self.task_type == 'sheerlink':
            self.run_sheerlink()
        elif self.task_type == 'verify_sheerid':
            self.run_verify_sheerid()
        elif self.task_type == 'age_verification':
            self.run_age_verification()
        elif self.task_type == 'setup_2fa':
            self.run_setup_2fa()
        elif self.task_type == 'bind_card':
            self.run_bind_card()

    def run_sheerlink(self):
        """执行SheerLink提取任务 (多线程) + 统计"""
        ids_to_process = self.kwargs.get('ids', [])
        thread_count = self.kwargs.get('thread_count', 1)
        
        if not ids_to_process:
             self.finished_signal.emit({'type': 'sheerlink', 'count': 0})
             return
        
        self.log(f"\n[开始] 提取 SheerID Link 任务，共 {len(ids_to_process)} 个窗口，并发数: {thread_count}...")
        
        # Stats counters
        stats = {
            'link_unverified': 0,
            'link_verified': 0,
            'subscribed': 0,
            'ineligible': 0,
            'timeout': 0,
            'error': 0
        }
        
        success_count = 0
        
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_to_id = {}
            for bid in ids_to_process:
                # Callback to log progress with ID prefix
                # Using default arg b=bid to capture loop variable value
                callback = lambda msg, b=bid: self.log_signal.emit(f"[{b}] {msg}")
                future = executor.submit(process_browser, bid, log_callback=callback)
                future_to_id[future] = bid
            
            finished_tasks = 0
            for future in as_completed(future_to_id):
                if not self.is_running:
                    self.log('[用户操作] 任务已停止 (等待当前线程完成)')
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                bid = future_to_id[future]
                finished_tasks += 1
                try:
                    success, msg = future.result()
                    if success:
                        self.log(f"[成功] ({finished_tasks}/{len(ids_to_process)}) {bid}: {msg}")
                        success_count += 1
                    else:
                        self.log(f"[失败] ({finished_tasks}/{len(ids_to_process)}) {bid}: {msg}")
                        
                    # Stats Logic
                    if "Verified Link" in msg or "Get Offer" in msg or "Offer Ready" in msg:
                        stats['link_verified'] += 1
                    elif "Unverified Link" in msg or "Link Found" in msg or "提取成功" in msg:
                        stats['link_unverified'] += 1
                    elif "Subscribed" in msg or "已绑卡" in msg:
                        stats['subscribed'] += 1
                    elif "无资格" in msg or "not available" in msg:
                        stats['ineligible'] += 1
                    elif "超时" in msg or "Timeout" in msg:
                        stats['timeout'] += 1
                    else:
                        stats['error'] += 1
                        
                except Exception as e:
                    self.log(f"[异常] ({finished_tasks}/{len(ids_to_process)}) {bid}: {e}")
                    stats['error'] += 1

        # Final Report
        summary_msg = (
            f"📊 任务统计报告:\n"
            f"--------------------------------\n"
            f"🔗 有资格待验证:   {stats['link_unverified']}\n"
            f"✅ 已过验证未绑卡: {stats['link_verified']}\n"
            f"💳 已过验证已绑卡: {stats['subscribed']}\n"
            f"❌ 无资格 (不可用): {stats['ineligible']}\n"
            f"⏳ 超时/错误:      {stats['timeout'] + stats['error']}\n"
            f"--------------------------------\n"
            f"总计处理: {finished_tasks}/{len(ids_to_process)}"
        )
        self.log(f"\n{summary_msg}")
        self.finished_signal.emit({'type': 'sheerlink', 'count': success_count, 'summary': summary_msg})

    def run_verify_sheerid(self):
        links = self.kwargs.get('links', [])
        thread_count = self.kwargs.get('thread_count', 1)
        
        self.log(f"\n[开始] 批量验证 {len(links)} 个链接 (并发: {thread_count})...")
        
        tasks = []
        vid_map = {} # ID -> Original Line
        
        for line in links:
            line = line.strip()
            if not line: continue
            
            vid = None
            # 优先提取参数中的 verificationId
            match_param = re.search(r'verificationId=([a-zA-Z0-9]+)', line)
            if match_param:
                vid = match_param.group(1)
            else:
                # 兜底：提取路径中的 ID
                match_path = re.search(r'verify/([a-zA-Z0-9]+)', line)
                if match_path:
                    vid = match_path.group(1)
            
            if vid:
                tasks.append(vid)
                vid_map[vid] = line
        
        if not tasks:
            self.log("[错误] 未找到有效的 verificationId")
            self.finished_signal.emit({'type': 'verify_sheerid', 'count': 0})
            return

        batches = [tasks[i:i + 5] for i in range(0, len(tasks), 5)]
        
        success_count = 0
        fail_count = 0
        
        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        path_success = os.path.join(base_path, "sheerID_verified_success.txt")
        path_fail = os.path.join(base_path, "sheerID_verified_failed.txt")

        # Define Callback
        def status_callback(vid, msg):
             self.log(f"[检测] {vid[:6]}...: {msg}")

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
             futures = []
             for batch in batches:
                 futures.append(executor.submit(self._verify_batch_wrapper, batch, status_callback))
             
             for future in as_completed(futures):
                 if not self.is_running:
                     self.log('[用户操作] 任务已停止')
                     executor.shutdown(wait=False, cancel_futures=True)
                     break
                 
                 try:
                     results = future.result()
                     for vid, res in results.items():
                         status = res.get("currentStep") or res.get("status")
                         msg = res.get("message", "")
                         
                         original_line = vid_map.get(vid, vid)
                         
                         if status == "success":
                             success_count += 1
                             self.log(f"[验证成功] {vid}")
                             with open(path_success, 'a', encoding='utf-8') as f:
                                 bind_url = res.get("bindUrl") or res.get("_bindUrl")
                                 if bind_url:
                                     f.write(f"{original_line} | Success | {bind_url}\n")
                                 else:
                                     f.write(f"{original_line} | Success\n")
                             if bind_url:
                                 try:
                                     from account_manager import AccountManager
                                     AccountManager.save_bind_link(original_line, bind_url)
                                 except Exception as e:
                                     self.log(f"[警告] 保存绑卡链接失败: {e}")
                         else:
                             fail_count += 1
                             self.log(f"[验证失败] {vid}: {msg}")
                             with open(path_fail, 'a', encoding='utf-8') as f:
                                 f.write(f"{original_line} | {msg}\n")
                 except Exception as e:
                     self.log(f"[异常] Batch error: {e}")

        self.log(f"[完成] 验证结束. 成功: {success_count}, 失败: {fail_count}")
        self.finished_signal.emit({'type': 'verify_sheerid', 'count': success_count})

    def _verify_batch_wrapper(self, batch_ids, callback=None):
        """已废弃：SheerID 验证功能请使用 Web 界面"""
        self.log("[错误] SheerID 验证功能已移至 Web 界面，请使用 http://localhost:8000")
        return []

    def run_age_verification(self):
        """执行年龄验证任务 (多线程)"""
        ids_to_process = self.kwargs.get('ids', [])
        thread_count = self.kwargs.get('thread_count', 1)

        if not ids_to_process:
            self.finished_signal.emit({'type': 'age_verification', 'count': 0})
            return

        self.log(f"\n[开始] 年龄验证任务，共 {len(ids_to_process)} 个窗口，并发数: {thread_count}...")

        success_count = 0
        fail_count = 0

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_to_id = {}
            for bid in ids_to_process:
                callback = lambda msg, b=bid: self.log_signal.emit(f"[{b}] {msg}")
                future = executor.submit(process_age_verification, bid, log_callback=callback)
                future_to_id[future] = bid

            finished_tasks = 0
            for future in as_completed(future_to_id):
                if not self.is_running:
                    self.log('[用户操作] 任务已停止')
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                bid = future_to_id[future]
                finished_tasks += 1
                try:
                    success, msg = future.result()
                    if success:
                        self.log(f"[成功] ({finished_tasks}/{len(ids_to_process)}) {bid}: {msg}")
                        success_count += 1
                    else:
                        self.log(f"[失败] ({finished_tasks}/{len(ids_to_process)}) {bid}: {msg}")
                        fail_count += 1
                except Exception as e:
                    self.log(f"[异常] {bid}: {e}")
                    fail_count += 1

        self.log(f"\n[完成] 年龄验证结束. 成功: {success_count}, 失败: {fail_count}")
        self.finished_signal.emit({'type': 'age_verification', 'count': success_count})

    def run_setup_2fa(self):
        """为没有 2FA 的账号设置新的 Authenticator"""
        ids_to_process = self.kwargs.get('ids', [])

        if not ids_to_process:
            self.finished_signal.emit({'type': 'setup_2fa', 'count': 0, 'secrets': {}})
            return

        self.log(f"\n[开始] 设置 2FA 任务，共 {len(ids_to_process)} 个窗口...")
        self.log("⚠️ 注意: 此操作将为没有 2FA 的账号添加 Authenticator")

        success_count = 0
        fail_count = 0
        secrets = {}

        for i, bid in enumerate(ids_to_process, 1):
            if not self.is_running:
                self.log('[用户操作] 任务已停止')
                break

            self.log(f"\n--- ({i}/{len(ids_to_process)}) 处理窗口: {bid} ---")

            try:
                # 使用 log_callback 将日志输出到 GUI
                def log_cb(msg: str, browser_id: str = bid) -> None:
                    self.log_signal.emit(f"[{browser_id[:8]}] {msg}")

                success, message, new_secret = setup_2fa_sync(bid, log_callback=log_cb)

                if success and new_secret:
                    self.log(f"[成功] {bid}: 2FA 设置成功，密钥: {new_secret[:8]}...")
                    success_count += 1
                    secrets[bid] = new_secret
                else:
                    self.log(f"[失败] {bid}: {message}")
                    fail_count += 1

            except Exception as e:
                self.log(f"[异常] {bid}: {e}")
                fail_count += 1

        self.log(f"\n[完成] 2FA 设置结束. 成功: {success_count}, 失败: {fail_count}")
        self.finished_signal.emit({'type': 'setup_2fa', 'count': success_count, 'secrets': secrets})

    def run_bind_card(self):
        """执行绑卡订阅任务"""
        ids_to_process = self.kwargs.get('ids', [])
        card_info = self.kwargs.get('card_info', None)

        if not ids_to_process:
            self.finished_signal.emit({'type': 'bind_card', 'count': 0})
            return

        self.log(f"\n[开始] 绑卡订阅任务，共 {len(ids_to_process)} 个窗口...")
        if card_info:
            self.log(f"卡号: **** **** **** {card_info.get('number', '')[-4:]}")

        success_count = 0
        fail_count = 0

        for i, bid in enumerate(ids_to_process, 1):
            if not self.is_running:
                self.log('[用户操作] 任务已停止')
                break

            self.log(f"\n--- ({i}/{len(ids_to_process)}) 处理窗口: {bid} ---")

            try:
                def log_cb(msg: str, browser_id: str = bid) -> None:
                    self.log_signal.emit(f"[{browser_id[:8]}] {msg}")

                success, message = bind_card_sync(bid, card_info=card_info, log_callback=log_cb)

                if success:
                    self.log(f"[成功] {bid}: {message}")
                    success_count += 1
                else:
                    self.log(f"[失败] {bid}: {message}")
                    fail_count += 1

            except Exception as e:
                self.log(f"[异常] {bid}: {e}")
                fail_count += 1

        self.log(f"\n[完成] 绑卡订阅结束. 成功: {success_count}, 失败: {fail_count}")
        self.finished_signal.emit({'type': 'bind_card', 'count': success_count})

    def run_open(self):
        """执行批量打开任务"""
        ids_to_open = self.kwargs.get('ids', [])
        if not ids_to_open:
            self.finished_signal.emit({'type': 'open', 'success_count': 0})
            return

        self.log(f"\n[开始] 准备打开 {len(ids_to_open)} 个窗口...")
        success_count = 0
        
        for i, browser_id in enumerate(ids_to_open, 1):
            if not self.is_running:
                self.log('[用户操作] 打开任务已停止')
                break
            
            self.log(f"正在打开 ({i}/{len(ids_to_open)}): {browser_id}")
            if open_browser_by_id(browser_id):
                self.log(f"[成功] 正在启动窗口 {browser_id}")
                success_count += 1
            else:
                self.log(f"[失败] 启动窗口 {browser_id} request失败")
            
            # 必需延迟防止API过载
            self.msleep(1000)
        
        self.log(f"[完成] 打开任务结束，成功请求 {success_count}/{len(ids_to_open)} 个")
        self.finished_signal.emit({'type': 'open', 'success_count': success_count})

    def run_2fa(self):
        """生成并保存2FA验证码"""
        try:
            self.log("正在通过API获取窗口列表和密钥...")
            
            # 1. 获取当前窗口列表 (尝试获取更多以涵盖所有)
            browsers = get_browser_list(page=0, pageSize=100)
            if not browsers:
                self.log("未获取到窗口列表")
                self.finished_signal.emit({'type': '2fa', 'codes': {}})
                return

            codes_map = {}
            file_lines = []
            
            count = 0
            for browser in browsers:
                if not self.is_running:
                    break
                
                # 优先从备注获取密钥 (第4段)
                secret = None
                remark = browser.get('remark', '')
                if remark:
                    parts = remark.split('----')
                    if len(parts) >= 4:
                        secret = parts[3].strip()
                
                # 如果备注没有，再尝试从字段获取
                if not secret:
                    secret = browser.get('faSecretKey')

                if secret and secret.strip():
                    try:
                        # 清理密钥
                        s = secret.strip().replace(" ", "")
                        totp = pyotp.TOTP(s)
                        code = totp.now()
                        
                        bid = browser.get('id')
                        codes_map[bid] = code
                        file_lines.append(f"{code}----{s}")
                        count += 1
                    except Exception as e:
                       # pass
                       pass
            
            # 保存到文件
            if file_lines:
                # Use absolute path relative to executable
                base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                save_path = os.path.join(base_path, '2fa_codes.txt')
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(file_lines))
                self.log(f"已保存 {len(file_lines)} 个验证码到 {save_path}")
            
            self.log(f"2FA刷新完成，共生成 {count} 个")
            self.finished_signal.emit({'type': '2fa', 'codes': codes_map})
            
        except Exception as e:
            self.log(f"2FA处理异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.finished_signal.emit({'type': '2fa', 'codes': {}})

    def run_delete(self):
        """执行批量删除任务"""
        ids_to_delete = self.kwargs.get('ids', [])
        if not ids_to_delete:
            self.finished_signal.emit({'success_count': 0, 'total': 0})
            return

        self.log(f"\n[开始] 准备删除 {len(ids_to_delete)} 个窗口...")
        success_count = 0
        
        for i, browser_id in enumerate(ids_to_delete, 1):
            if not self.is_running:
                self.log('[用户操作] 删除任务已停止')
                break
            
            self.log(f"正在删除 ({i}/{len(ids_to_delete)}): {browser_id}")
            if delete_browser_by_id(browser_id):
                self.log(f"[成功] 删除窗口 {browser_id}")
                success_count += 1
            else:
                self.log(f"[失败] 删除窗口 {browser_id} 失败")
        
        self.log(f"[完成] 删除任务结束，成功删除 {success_count}/{len(ids_to_delete)} 个")
        self.finished_signal.emit({'type': 'delete', 'success_count': success_count})

    def run_create(self):
        """执行创建任务"""
        template_id = self.kwargs.get('template_id')
        template_config = self.kwargs.get('template_config')
        
        platform_url = self.kwargs.get('platform_url')
        extra_url = self.kwargs.get('extra_url')
        name_prefix = self.kwargs.get('name_prefix')

        try:
            # 读取账户信息
            accounts_file = 'accounts.txt'
            accounts = read_accounts(accounts_file)
            
            if not accounts:
                self.log("[错误] 未找到有效的账户信息")
                self.log("请确保 accounts.txt 文件存在且格式正确")
                self.log("格式：邮箱----密码----辅助邮箱----2FA密钥")
                self.finished_signal.emit({'type': 'create', 'success_count': 0})
                return
            
            self.log(f"[信息] 找到 {len(accounts)} 个账户")
            
            # 读取代理信息
            proxies_file = 'proxies.txt'
            proxies = read_proxies(proxies_file)
            self.log(f"[信息] 找到 {len(proxies)} 个代理")
            
            # 获取参考窗口信息
            if template_config:
                reference_config = template_config
                ref_name = reference_config.get('name', '默认模板')
                self.log(f"[信息] 使用内置默认模板")
            else:
                reference_config = get_browser_info(template_id)
                if not reference_config:
                    self.log(f"[错误] 无法获取模板窗口配置")
                    self.finished_signal.emit({'type': 'create', 'success_count': 0})
                    return
                ref_name = reference_config.get('name', '未知')
                self.log(f"[信息] 使用模板窗口: {ref_name} (ID: {template_id})")
            
            # 显示平台和URL信息
            if platform_url:
                self.log(f"[信息] 平台URL: {platform_url}")
            if extra_url:
                self.log(f"[信息] 额外URL: {extra_url}")
            
            # 删除名称为"本地代理_2"的所有窗口（如果参考窗口是"本地代理_1"）
            if ref_name.startswith('本地代理_'):
                try:
                    next_name = get_next_window_name(ref_name)
                    # 如果下一个名称是"本地代理_2"，则尝试删除旧的"本地代理_2"
                    if next_name == "本地代理_2":
                        self.log(f"\n[步骤] 正在清理旧的'本地代理_2'窗口...")
                        deleted_count = delete_browsers_by_name("本地代理_2")
                        if deleted_count > 0:
                            self.log(f"[清理] 已删除 {deleted_count} 个旧窗口")
                except:
                    pass
            
            # 为每个账户创建窗口
            success_count = 0
            for i, account in enumerate(accounts, 1):
                if not self.is_running:
                    self.log("\n[用户操作] 创建任务已停止")
                    break
                
                self.log(f"\n{'='*40}")
                self.log(f"[进度] ({i}/{len(accounts)}) 创建: {account['email']}")
                
                # 获取对应的代理（如果有）
                proxy = proxies[i - 1] if i - 1 < len(proxies) else None
                
                browser_id, error_msg = create_browser_window(
                    account, 
                    template_id if not template_config else None,
                    proxy,
                    platform=platform_url if platform_url else None,
                    extra_url=extra_url if extra_url else None,
                    template_config=template_config,
                    name_prefix=name_prefix
                )
                
                if browser_id:
                    success_count += 1
                    self.log(f"[成功] 窗口创建成功！ID: {browser_id}")
                else:
                    self.log(f"[失败] 窗口创建失败: {error_msg}")
            
            self.log(f"\n{'='*40}")
            self.log(f"[完成] 总共创建 {success_count}/{len(accounts)} 个窗口")
            
            self.finished_signal.emit({'type': 'create', 'success_count': success_count})
            
        except Exception as e:
            self.log(f"[错误] 创建过程中发生异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.finished_signal.emit({'type': 'create', 'success_count': 0})


class BrowserWindowCreatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 设置窗口图标
        try:
            icon_path = resource_path("beta-1.svg")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        self.ensure_data_files()
        self.worker_thread = None
        self.init_ui()

    def ensure_data_files(self):
        """Ensure necessary data files exist"""
        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        files = ["sheerIDlink.txt", "无资格号.txt", "2fa_codes.txt", "已绑卡号.txt", "已验证未绑卡.txt", "超时或其他错误.txt"]
        for f in files:
            path = os.path.join(base_path, f)
            if not os.path.exists(path):
                try:
                    with open(path, 'w', encoding='utf-8') as file:
                        pass
                except Exception as e:
                    print(f"Failed to create {f}: {e}")
        
    def init_function_panel(self):
        """初始化左侧功能区"""
        self.function_panel = QWidget()
        self.function_panel.setFixedWidth(250)
        self.function_panel.setVisible(False) # 默认隐藏
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.function_panel.setLayout(layout)
        
        # 1. 标题
        title = QLabel("🔥 功能工具箱")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; background-color: #f0f0f0;")
        layout.addWidget(title)
        
        # 2. 分区工具箱
        self.toolbox = QToolBox()
        self.toolbox.setStyleSheet("""
            QToolBox::tab {
                background: #e1e1e1;
                border-radius: 5px;
                color: #555;
                font-weight: bold;
            }
            QToolBox::tab:selected {
                background: #d0d0d0;
                color: black;
            }
        """)
        layout.addWidget(self.toolbox)
        
        # --- 谷歌分区 ---
        google_page = QWidget()
        google_layout = QVBoxLayout()
        google_layout.setContentsMargins(5,10,5,10)
        
        # Move btn_sheerlink here
        self.btn_sheerlink = QPushButton("一键获取 G-SheerLink")
        self.btn_sheerlink.setFixedHeight(40)
        self.btn_sheerlink.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sheerlink.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding-left: 15px; 
                font-weight: bold; 
                color: white;
                background-color: #4CAF50;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.btn_sheerlink.clicked.connect(self.action_get_sheerlink)
        google_layout.addWidget(self.btn_sheerlink)
        
        # New Button: Verify SheerID
        self.btn_verify_sheerid = QPushButton("批量验证 SheerID Link")
        self.btn_verify_sheerid.setFixedHeight(40)
        self.btn_verify_sheerid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_verify_sheerid.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding-left: 15px; 
                font-weight: bold; 
                color: white;
                background-color: #2196F3;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.btn_verify_sheerid.clicked.connect(self.action_verify_sheerid)
        google_layout.addWidget(self.btn_verify_sheerid)

        # 年龄验证按钮
        self.btn_age_verify = QPushButton("🎂 批量年龄验证")
        self.btn_age_verify.setFixedHeight(40)
        self.btn_age_verify.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_age_verify.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 15px;
                font-weight: bold;
                color: white;
                background-color: #9C27B0;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        self.btn_age_verify.clicked.connect(self.action_age_verification)
        google_layout.addWidget(self.btn_age_verify)

        # 设置 2FA 按钮（为没有 2FA 的账号添加 Authenticator）
        self.btn_setup_2fa = QPushButton("🔐 设置新 2FA")
        self.btn_setup_2fa.setFixedHeight(40)
        self.btn_setup_2fa.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_setup_2fa.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 15px;
                font-weight: bold;
                color: white;
                background-color: #E91E63;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #C2185B; }
        """)
        self.btn_setup_2fa.setToolTip("为没有 2FA 的 Google 账号设置新的 Authenticator")
        self.btn_setup_2fa.clicked.connect(self.action_setup_2fa)
        google_layout.addWidget(self.btn_setup_2fa)

        # 一键绑卡订阅按钮
        self.btn_bind_card = QPushButton("🔗 一键绑卡订阅")
        self.btn_bind_card.setFixedHeight(40)
        self.btn_bind_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bind_card.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding-left: 15px; 
                font-weight: bold; 
                color: white;
                background-color: #FF9800;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        self.btn_bind_card.clicked.connect(self.action_bind_card)
        google_layout.addWidget(self.btn_bind_card)
        
        # 一键全自动处理按钮
        self.btn_auto_all = QPushButton("🚀 一键全自动处理")
        self.btn_auto_all.setFixedHeight(40)
        self.btn_auto_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_all.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding-left: 15px; 
                font-weight: bold; 
                color: white;
                background-color: #9C27B0;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        self.btn_auto_all.clicked.connect(self.action_auto_all)
        google_layout.addWidget(self.btn_auto_all)
        
        google_layout.addStretch()
        google_page.setLayout(google_layout)
        self.toolbox.addItem(google_page, "Google 专区")
        
        # --- 微软分区 ---
        ms_page = QWidget()
        self.toolbox.addItem(ms_page, "Microsoft 专区")
        
        # --- 脸书分区 ---
        fb_page = QWidget()
        self.toolbox.addItem(fb_page, "Facebook 专区")
        
        # --- Telegram分区 ---
        tg_page = QWidget()
        tg_layout = QVBoxLayout()
        tg_layout.addWidget(QLabel("功能开发中..."))
        tg_layout.addStretch()
        tg_page.setLayout(tg_layout)
        self.toolbox.addItem(tg_page, "Telegram 专区")
        
        # 默认展开谷歌
        self.toolbox.setCurrentIndex(0)

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("比特浏览器窗口管理工具")
        self.setWindowIcon(QIcon(resource_path("beta-1.svg")))
        self.resize(1300, 800)
        
        # Init Side Panel
        self.init_function_panel()
        
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局 - 水平
        main_layout = QHBoxLayout()
        main_layout.setSpacing(5)
        main_widget.setLayout(main_layout)
        
        # 1. Add Function Panel (Leftmost)
        main_layout.addWidget(self.function_panel)
        
        # ================== 左侧区域 (控制 + 列表) ==================
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        
        # --- Top Bar: Toggle Logic + Title + Global Settings ---
        top_bar_layout = QHBoxLayout()
        
        # Toggle Button
        self.btn_toggle_tools = QPushButton("工具箱 📂")
        self.btn_toggle_tools.setCheckable(True)
        self.btn_toggle_tools.setChecked(False) 
        self.btn_toggle_tools.setFixedHeight(30)
        self.btn_toggle_tools.setStyleSheet("""
            QPushButton { background-color: #607D8B; color: white; border-radius: 4px; padding: 5px 10px; }
            QPushButton:checked { background-color: #455A64; }
        """)
        self.btn_toggle_tools.clicked.connect(lambda checked: self.function_panel.setVisible(checked))
        top_bar_layout.addWidget(self.btn_toggle_tools)
        
        # Title
        title_label = QLabel("控制面板")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setContentsMargins(10,0,10,0)
        top_bar_layout.addWidget(title_label)
        
        top_bar_layout.addStretch()
        
        # Global Thread Spinbox
        top_bar_layout.addWidget(QLabel("🔥 全局并发数:"))
        self.thread_spinbox = QSpinBox()
        self.thread_spinbox.setRange(1, 50)
        self.thread_spinbox.setValue(1)
        self.thread_spinbox.setFixedSize(70, 30)
        self.thread_spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thread_spinbox.setStyleSheet("font-size: 14px; font-weight: bold; color: #E91E63;")
        self.thread_spinbox.setToolTip("所有多线程任务的并发数量 (1-50)")
        top_bar_layout.addWidget(self.thread_spinbox)
        
        left_layout.addLayout(top_bar_layout)
        
        # 2. 配置区域
        config_group = QGroupBox("创建参数配置")
        config_layout = QVBoxLayout()
        
        # 模板ID
        input_layout1 = QHBoxLayout()
        input_layout1.addWidget(QLabel("模板窗口ID:"))
        self.template_id_input = QLineEdit()
        self.template_id_input.setPlaceholderText("请输入模板窗口ID")
        input_layout1.addWidget(self.template_id_input)
        config_layout.addLayout(input_layout1)

        # 窗口名前缀
        input_layout_prefix = QHBoxLayout()
        input_layout_prefix.addWidget(QLabel("窗口前缀:"))
        self.name_prefix_input = QLineEdit()
        self.name_prefix_input.setPlaceholderText("可选，默认按模板名或'默认模板'命名")
        input_layout_prefix.addWidget(self.name_prefix_input)
        config_layout.addLayout(input_layout_prefix)
        
        # URL配置
        input_layout2 = QHBoxLayout()
        input_layout2.addWidget(QLabel("平台URL:"))
        self.platform_url_input = QLineEdit()
        self.platform_url_input.setPlaceholderText("可选，平台URL")
        input_layout2.addWidget(self.platform_url_input)
        config_layout.addLayout(input_layout2)
        
        input_layout3 = QHBoxLayout()
        input_layout3.addWidget(QLabel("额外URL:"))
        self.extra_url_input = QLineEdit()
        self.extra_url_input.setPlaceholderText("可选，逗号分隔")
        input_layout3.addWidget(self.extra_url_input)
        config_layout.addLayout(input_layout3)
        
        # 文件路径提示
        file_info_layout = QHBoxLayout()
        self.accounts_label = QLabel("✅ accounts.txt")
        self.accounts_label.setStyleSheet("color: green;")
        self.proxies_label = QLabel("✅ proxies.txt")
        self.proxies_label.setStyleSheet("color: green;")
        file_info_layout.addWidget(self.accounts_label)
        file_info_layout.addWidget(self.proxies_label)
        file_info_layout.addStretch()
        config_layout.addLayout(file_info_layout)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        
        # 3. 创建控制按钮
        create_btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始根据模板创建窗口")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.start_btn.clicked.connect(self.start_creation)
        
        self.stop_btn = QPushButton("停止任务")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setEnabled(False)
        
        create_btn_layout.addWidget(self.start_btn)
        
        self.start_default_btn = QPushButton("使用默认模板创建")
        self.start_default_btn.setFixedHeight(40)
        self.start_default_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.start_default_btn.clicked.connect(self.start_creation_default)
        create_btn_layout.addWidget(self.start_default_btn)
        
        create_btn_layout.addWidget(self.stop_btn)
        left_layout.addLayout(create_btn_layout)
        
        # 4. 窗口列表部分
        list_group = QGroupBox("现存窗口列表")
        list_layout = QVBoxLayout()
        
        # 列表操作按钮
        list_action_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.clicked.connect(self.refresh_browser_list)
        
        self.btn_2fa = QPushButton("刷新并保存验证码")
        self.btn_2fa = QPushButton("刷新并保存验证码")
        self.btn_2fa.setStyleSheet("color: purple; font-weight: bold;")
        self.btn_2fa.clicked.connect(self.action_refresh_2fa)

        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        
        self.open_btn = QPushButton("打开选中窗口")
        self.open_btn.setStyleSheet("color: blue; font-weight: bold;")
        self.open_btn.clicked.connect(self.open_selected_browsers)

        self.delete_btn = QPushButton("删除选中窗口")
        self.delete_btn.setStyleSheet("color: red;")
        self.delete_btn.clicked.connect(self.delete_selected_browsers)
        
        list_action_layout.addWidget(self.refresh_btn)
        list_action_layout.addWidget(self.btn_2fa)
        list_action_layout.addWidget(self.select_all_checkbox)
        list_action_layout.addStretch()
        list_action_layout.addWidget(self.open_btn)
        list_action_layout.addWidget(self.delete_btn)
        list_layout.addLayout(list_action_layout)
        
        # 表格控件
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["选择", "名称", "窗口ID", "2FA验证码", "备注"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Checkbox
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)      # Name
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)      # ID
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)      # 2FA
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)          # Remark
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        list_layout.addWidget(self.table)
        
        list_group.setLayout(list_layout)
        left_layout.addWidget(list_group)
        
        # 添加左侧到主布局
        main_layout.addWidget(left_widget, 3)
        
        # ================== 右侧区域 (日志) ==================
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)
        
        log_label = QLabel("运行状态日志")
        log_label.setFont(title_font)
        right_layout.addWidget(log_label)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #f5f5f5;")
        right_layout.addWidget(self.status_text)
        
        # 添加清除日志按钮
        clear_log_btn = QPushButton("清除日志")
        clear_log_btn.clicked.connect(self.status_text.clear)
        right_layout.addWidget(clear_log_btn)
        
        # 添加右侧到主布局
        main_layout.addWidget(right_widget, 2)
        
        # 初始加载
        QTimer.singleShot(100, self.refresh_browser_list)
        self.check_files()

    def check_files(self):
        """检查文件是否存在并更新UI"""
        accounts_exists = os.path.exists('accounts.txt')
        proxies_exists = os.path.exists('proxies.txt')
        
        if not accounts_exists:
            self.accounts_label.setText("❌ accounts.txt 缺失")
            self.accounts_label.setStyleSheet("color: red;")
        if not proxies_exists:
            self.proxies_label.setText("⚠️ proxies.txt 未找到")
            self.proxies_label.setStyleSheet("color: orange;")

    def log(self, message):
        """添加日志"""
        self.status_text.append(message)
        cursor = self.status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.status_text.setTextCursor(cursor)

    def refresh_browser_list(self):
        """刷新窗口列表到表格"""
        self.table.setRowCount(0)
        self.select_all_checkbox.setChecked(False)
        self.log("正在刷新窗口列表...")
        QApplication.processEvents()
        
        try:
            browsers = get_browser_list()
            if not browsers:
                self.log("未获取到窗口列表")
                return
            
            self.table.setRowCount(len(browsers))
            for i, browser in enumerate(browsers):
                # Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(i, 0, chk_item)
                
                # Name
                name = str(browser.get('name', ''))
                self.table.setItem(i, 1, QTableWidgetItem(name))
                
                # ID
                bid = str(browser.get('id', ''))
                self.table.setItem(i, 2, QTableWidgetItem(bid))
                
                # 2FA (Initial empty)
                self.table.setItem(i, 3, QTableWidgetItem(""))
                
                # Remark
                remark = str(browser.get('remark', ''))
                self.table.setItem(i, 4, QTableWidgetItem(remark))
            
            self.log(f"列表刷新完成，共 {len(browsers)} 个窗口")
            
        except Exception as e:
            self.log(f"[错误] 刷新列表失败: {e}")

    def action_refresh_2fa(self):
        """刷新并保存2FA验证码"""
        self.log("正在获取所有窗口信息以生成验证码...")
        self.start_worker_thread('2fa')

    def action_get_sheerlink(self):
        """一键获取G-sheerlink"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先在列表中勾选要处理的窗口")
            return
        
        thread_count = self.thread_spinbox.value()
        msg = f"确定要对选中的 {len(ids)} 个窗口执行 SheerID 提取吗？\n"
        msg += f"当前并发模式: {thread_count} 线程\n"
        if thread_count > 1:
            msg += "⚠️ 注意: 将同时打开多个浏览器窗口，请确保电脑资源充足。"
        
        reply = QMessageBox.question(self, '确认操作', msg,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('sheerlink', ids=ids, thread_count=thread_count)

    def action_verify_sheerid(self):
        """打开 SheerID 批量验证窗口"""
        try:
            if not hasattr(self, 'verify_window') or self.verify_window is None:
                self.verify_window = SheerIDWindow(self)
            
            self.verify_window.show()
            self.verify_window.raise_()
            self.verify_window.activateWindow()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开验证窗口: {e}")

    def action_age_verification(self):
        """批量年龄验证"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先在列表中勾选要处理的窗口")
            return

        thread_count = self.thread_spinbox.value()

        reply = QMessageBox.question(self, "确认",
                                    f"确定要对选中的 {len(ids)} 个窗口进行年龄验证吗？\n"
                                    f"并发数: {thread_count}\n\n"
                                    f"此操作将自动访问 Google 年龄验证页面。",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('age_verification', ids=ids, thread_count=thread_count)

    def action_setup_2fa(self):
        """为没有 2FA 的账号设置新的 Authenticator"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先在列表中勾选要处理的窗口")
            return

        reply = QMessageBox.question(self, "确认设置 2FA",
                                    f"确定要为选中的 {len(ids)} 个窗口设置新的 2FA 吗？\n\n"
                                    f"⚠️ 注意:\n"
                                    f"• 此操作仅适用于【没有开启 2FA】的账号\n"
                                    f"• 如果账号已有 2FA，可能会导致问题\n"
                                    f"• 新密钥将自动保存到 new_2fa_secrets.txt\n"
                                    f"• 同时会更新比特浏览器的备注字段",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('setup_2fa', ids=ids)

    def action_bind_card(self):
        """执行绑卡订阅"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先在列表中勾选要处理的窗口")
            return

        # 弹出卡信息输入对话框
        from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("输入卡片信息")
        dialog.setMinimumWidth(350)

        layout = QFormLayout(dialog)

        card_number_input = QLineEdit()
        card_number_input.setPlaceholderText("卡号 (16位)")
        layout.addRow("卡号:", card_number_input)

        exp_input = QLineEdit()
        exp_input.setPlaceholderText("MM/YY 或 MMYY")
        layout.addRow("有效期:", exp_input)

        cvv_input = QLineEdit()
        cvv_input.setPlaceholderText("3位安全码")
        layout.addRow("CVV:", cvv_input)

        zip_input = QLineEdit()
        zip_input.setPlaceholderText("美国邮编 (可选)")
        layout.addRow("邮编:", zip_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # 解析卡信息
        card_number = card_number_input.text().strip().replace(" ", "")
        exp_raw = exp_input.text().strip().replace("/", "")
        cvv = cvv_input.text().strip()
        zip_code = zip_input.text().strip()

        if not card_number or len(card_number) < 13:
            QMessageBox.warning(self, "错误", "请输入有效的卡号")
            return

        if not exp_raw or len(exp_raw) < 4:
            QMessageBox.warning(self, "错误", "请输入有效的有效期 (MMYY)")
            return

        if not cvv or len(cvv) < 3:
            QMessageBox.warning(self, "错误", "请输入有效的CVV")
            return

        card_info = {
            'number': card_number,
            'exp_month': exp_raw[:2],
            'exp_year': exp_raw[2:],
            'cvv': cvv,
            'zip': zip_code or '10001'
        }

        reply = QMessageBox.question(self, "确认绑卡",
                                    f"确定要为选中的 {len(ids)} 个窗口绑卡订阅吗？\n\n"
                                    f"卡号: **** **** **** {card_number[-4:]}\n"
                                    f"有效期: {exp_raw[:2]}/{exp_raw[2:]}\n\n"
                                    f"⚠️ 注意: 此操作将自动完成绑卡和订阅流程",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('bind_card', ids=ids, card_info=card_info)
    
    def action_auto_all(self):
        """打开一键全自动处理窗口"""
        try:
            from auto_all_in_one_gui import AutoAllInOneWindow
            
            if not hasattr(self, 'auto_all_window') or self.auto_all_window is None:
                self.auto_all_window = AutoAllInOneWindow()
            
            self.auto_all_window.show()
            self.auto_all_window.raise_()
            self.auto_all_window.activateWindow()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开全自动处理窗口: {e}")
            import traceback
            traceback.print_exc()
        
    def open_selected_browsers(self):
        """打开选中的窗口"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先勾选要打开的窗口")
            return
        
        self.start_worker_thread('open', ids=ids)

    def toggle_select_all(self, state):
        """全选/取消全选"""
        is_checked = (state == Qt.CheckState.Checked.value)  # value of Qt.CheckState.Checked is 2
        # 注意：Qt6中 state 是 int
        # 实际上 stateChanged 发出的是 int
        # Qt.CheckState.Checked.value 是 2
        
        row_count = self.table.rowCount()
        for i in range(row_count):
            item = self.table.item(i, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if state == 2 else Qt.CheckState.Unchecked)

    def get_selected_browser_ids(self):
        """获取选中的窗口ID列表"""
        ids = []
        row_count = self.table.rowCount()
        for i in range(row_count):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                # ID is in column 2
                id_item = self.table.item(i, 2)
                if id_item:
                    ids.append(id_item.text())
        return ids

    def delete_selected_browsers(self):
        """删除选中的窗口"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先勾选要删除的窗口")
            return
        
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除选中的 {len(ids)} 个窗口吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('delete', ids=ids)

    def start_creation(self):
        """开始创建任务"""
        template_id = self.template_id_input.text().strip()
        if not template_id:
            QMessageBox.warning(self, "警告", "请输入模板窗口ID")
            return
            
        platform_url = self.platform_url_input.text().strip()
        extra_url = self.extra_url_input.text().strip()
        name_prefix = self.name_prefix_input.text().strip()
        
        self.update_ui_state(True)
        self.log(f"启动创建任务... 模板ID: {template_id}")
        
        self.worker_thread = WorkerThread(
            'create', 
            template_id=template_id,
            platform_url=platform_url, 
            extra_url=extra_url,
            name_prefix=name_prefix
        )
        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.finished_signal.connect(self.on_worker_finished)
        self.worker_thread.start()

    def start_worker_thread(self, task_type, **kwargs):
        """启动后台线程"""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "提示", "当前有任务正在运行，请稍候...")
            return
            
        self.worker_thread = WorkerThread(task_type, **kwargs)
        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.finished_signal.connect(self.on_worker_finished)
        self.worker_thread.start()
        
        self.update_ui_state(running=True)

    def update_ui_state(self, running):
        """更新UI按钮状态"""
        self.start_btn.setEnabled(not running)
        self.start_default_btn.setEnabled(not running)
        self.delete_btn.setEnabled(not running)
        self.open_btn.setEnabled(not running)
        self.btn_2fa.setEnabled(not running)
        self.btn_sheerlink.setEnabled(not running)
        self.btn_age_verify.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.refresh_btn.setEnabled(not running)
        self.template_id_input.setEnabled(not running)
        self.name_prefix_input.setEnabled(not running)

    def start_creation_default(self):
        """使用默认模板开始创建任务"""
        platform_url = self.platform_url_input.text().strip()
        extra_url = self.extra_url_input.text().strip()
        name_prefix = self.name_prefix_input.text().strip()
        
        self.update_ui_state(True)
        self.log(f"启动创建任务... 使用默认配置模板")
        
        self.start_worker_thread(
            'create', 
            template_config=DEFAULT_TEMPLATE_CONFIG,
            platform_url=platform_url, 
            extra_url=extra_url,
            name_prefix=name_prefix
        )

    def stop_task(self):
        """停止当前任务"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.log("[用户操作] 正在停止任务...")
            self.stop_btn.setEnabled(False) #防止重复点击

    def on_worker_finished(self, result):
        """任务结束回调"""
        self.update_ui_state(running=False)
        self.log(f"任务已结束")
        
        # 如果是删除操作，完成后刷新列表
        if result.get('type') == 'delete':
            self.refresh_browser_list()
        # 如果是创建操作，也刷新列表可以看到新窗口
        elif result.get('type') == 'create':
            self.refresh_browser_list()
        # 2FA刷新结果
        elif result.get('type') == '2fa':
            codes = result.get('codes', {})
            row_count = self.table.rowCount()
            for i in range(row_count):
                id_item = self.table.item(i, 2) # ID Column
                if id_item:
                    bid = id_item.text()
                    if bid in codes:
                        self.table.setItem(i, 3, QTableWidgetItem(str(codes[bid])))
            QMessageBox.information(self, "完成", "2FA验证码已更新并保存")
        # 打开操作
        elif result.get('type') == 'open':
            pass
            
        elif result.get('type') == 'sheerlink':
            count = result.get('count', 0)
            summary = result.get('summary')
            if summary:
                 QMessageBox.information(self, "任务完成", summary)
            else:
                 QMessageBox.information(self, "完成", f"SheerLink 提取任务结束\n成功提取: {count} 个\n结果保存在 sheerIDlink.txt")

        elif result.get('type') == 'verify_sheerid':
            count = result.get('count', 0)
            QMessageBox.information(self, "完成", f"SheerID 批量验证结束\n成功: {count} 个\n结果已保存至 sheerID_verified_success/failed.txt")

        elif result.get('type') == 'age_verification':
            count = result.get('count', 0)
            QMessageBox.information(self, "完成", f"年龄验证任务结束\n成功验证: {count} 个")

        elif result.get('type') == 'setup_2fa':
            count = result.get('count', 0)
            secrets = result.get('secrets', {})
            msg = f"2FA 设置任务结束\n成功设置: {count} 个\n\n"
            if secrets:
                msg += "新密钥已保存到:\n• new_2fa_secrets.txt\n• 比特浏览器备注字段"
            QMessageBox.information(self, "完成", msg)
            # 刷新列表以显示更新后的备注
            self.refresh_browser_list()

        elif result.get('type') == 'bind_card':
            count = result.get('count', 0)
            QMessageBox.information(self, "完成", f"绑卡订阅任务结束\n成功: {count} 个\n\n结果已保存到 已绑卡号.txt")

    def update_ui_state(self, running):
        """更新UI按钮状态"""
        self.start_btn.setEnabled(not running)
        self.delete_btn.setEnabled(not running)
        self.open_btn.setEnabled(not running)
        self.btn_2fa.setEnabled(not running)
        self.btn_sheerlink.setEnabled(not running)
        self.btn_age_verify.setEnabled(not running)
        self.btn_verify_sheerid.setEnabled(not running)
        self.btn_setup_2fa.setEnabled(not running)
        self.btn_bind_card.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.refresh_btn.setEnabled(not running)


def main():
    # Web Admin 已迁移到 web/backend，使用 FastAPI
    # 启动方式: cd web/backend && uvicorn main:app --reload --port 8000

    # 确保打包时包含 SVG 支持
    import PyQt6.QtSvg

    # Fix taskbar icon on Windows
    import ctypes
    try:
        myappid = 'leclee.bitbrowser.automanager.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass

    app = QApplication(sys.argv)
    
    # 设置全局字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)
    
    # 设置全局图标
    icon_path = resource_path("beta-1.svg")
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
        app.setWindowIcon(icon)
    else:
        # 如果打包环境下找不到图标，提示
        if hasattr(sys, '_MEIPASS'):
             QMessageBox.warning(None, "Icon Missing", f"Icon not found at: {icon_path}")
    
    window = BrowserWindowCreatorGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
