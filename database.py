import sqlite3
import os
import sys
import threading
from contextlib import contextmanager

# 数据库路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
DB_PATH = os.path.join(BASE_DIR, "accounts.db")

lock = threading.Lock()

class DBManager:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    @contextmanager
    def get_db():
        """Context manager for database connections, ensures proper cleanup."""
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def init_db():
        with lock:
            conn = DBManager.get_connection()
            cursor = conn.cursor()
            # 创建账号表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    email TEXT PRIMARY KEY,
                    password TEXT,
                    recovery_email TEXT,
                    secret_key TEXT,
                    verification_link TEXT,
                    status TEXT DEFAULT 'pending',
                    message TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    browser_id TEXT,
                    browser_config TEXT
                )
            ''')

            # 迁移：为旧表添加新字段
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN browser_id TEXT")
            except sqlite3.OperationalError:
                pass  # 字段已存在
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN browser_config TEXT")
            except sqlite3.OperationalError:
                pass  # 字段已存在
            
            # Check for existing data
            cursor.execute("SELECT count(*) FROM accounts")
            count = cursor.fetchone()[0]
            
            conn.commit()
            conn.close()
        
        # Release lock before importing to avoid deadlock if import calls methods that use lock
        if count == 0:
            DBManager.import_from_files()

    @staticmethod
    def _simple_parse(line):
        """
        解析账号信息行（使用固定分隔符）
        默认分隔符：----
        """
        import re
        
        # 移除注释
        if '#' in line:
            line = line.split('#')[0].strip()
        
        if not line:
            return None, None, None, None, None
        
        # 识别HTTP链接
        link = None
        link_match = re.search(r'https?://[^\s]+', line)
        if link_match:
            link = link_match.group()
            # 移除链接后继续解析
            line = line.replace(link, '').strip()
        
        # 使用固定分隔符分割（默认 ----）
        # 优先尝试 ----，如果没有则尝试其他常见分隔符
        separator = '----'
        if separator not in line:
            # 尝试其他分隔符
            found_sep = False
            for sep in ['---', '|', ',', ';', '\t']:
                if sep in line:
                    separator = sep
                    found_sep = True
                    break

            # 如果都没有找到，回退到空格分隔
            if not found_sep:
                parts = line.split()
                parts = [p.strip() for p in parts if p.strip()]
                # 提前返回，跳过下面的 separator 分割
                email = parts[0] if len(parts) >= 1 else None
                pwd = parts[1] if len(parts) >= 2 else None
                rec = parts[2] if len(parts) >= 3 else None
                sec = parts[3] if len(parts) >= 4 else None
                return email, pwd, rec, sec, link

        parts = line.split(separator)
        parts = [p.strip() for p in parts if p.strip()]
        
        email = None
        pwd = None
        rec = None
        sec = None
        
        # 按固定顺序分配
        if len(parts) >= 1:
            email = parts[0]
        if len(parts) >= 2:
            pwd = parts[1]
        if len(parts) >= 3:
            rec = parts[2]
        if len(parts) >= 4:
            sec = parts[3]
        
        return email, pwd, rec, sec, link

    @staticmethod
    def import_from_files():
        """从现有文本文件导入数据到数据库（初始化用）"""
        count_total = 0
        
        # 1. 优先从 accounts.txt 导入（使用新的解析方式）
        accounts_path = os.path.join(BASE_DIR, "accounts.txt")
        if os.path.exists(accounts_path):
            try:
                # 使用create_window中的read_accounts函数
                from create_window import read_accounts
                accounts = read_accounts(accounts_path)
                
                print(f"从 accounts.txt 读取到 {len(accounts)} 个账号")
                
                for account in accounts:
                    email = account.get('email', '')
                    pwd = account.get('password', '')
                    rec = account.get('backup_email', '')
                    sec = account.get('2fa_secret', '')
                    
                    if email:
                        # 新账号默认状态为pending（待处理）
                        DBManager.upsert_account(email, pwd, rec, sec, None, status='pending')
                        count_total += 1
                
                print(f"成功导入 {count_total} 个账号（状态: pending）")
            except Exception as e:
                print(f"从 accounts.txt 导入时出错: {e}")
        
        # 2. 从状态文件导入（覆盖accounts.txt中的状态）
        files_map = {
            "link_ready": "sheerIDlink.txt",
            "verified": "已验证未绑卡.txt",
            "subscribed": "已绑卡号.txt",
            "ineligible": "无资格号.txt",
            "error": "超时或其他错误.txt"
        }
        
        count_status = 0
        for status, filename in files_map.items():
            path = os.path.join(BASE_DIR, filename)
            if not os.path.exists(path): 
                continue
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]
                
                for line in lines:
                    email, pwd, rec, sec, link = DBManager._simple_parse(line)
                    if email:
                        DBManager.upsert_account(email, pwd, rec, sec, link, status=status)
                        count_status += 1
            except Exception as e:
                print(f"从 {filename} 导入时出错: {e}")
        
        if count_status > 0:
            print(f"从状态文件导入/更新了 {count_status} 个账号")
        
        total = count_total + count_status
        if total > 0:
            print(f"数据库初始化完成，共处理 {total} 条记录")

    @staticmethod
    def upsert_account(email, password=None, recovery_email=None, secret_key=None, 
                       link=None, status=None, message=None):
        """插入或更新账号信息"""
        if not email:
            print(f"[DB] upsert_account: email 为空，跳过")
            return
        # 注意：不再对密码进行小写化处理，保留原始大小写
            
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                
                # 先检查是否存在
                cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
                exists = cursor.fetchone()
                
                if exists:
                    # 构建更新语句 - 使用 is not None 而不是 truthiness 判断
                    fields = []
                    values = []
                    if password is not None: fields.append("password = ?"); values.append(password)
                    if recovery_email is not None: fields.append("recovery_email = ?"); values.append(recovery_email)
                    if secret_key is not None: fields.append("secret_key = ?"); values.append(secret_key)
                    if link is not None: fields.append("verification_link = ?"); values.append(link)
                    if status is not None: fields.append("status = ?"); values.append(status)
                    if message is not None: fields.append("message = ?"); values.append(message)
                    
                    if fields:
                        fields.append("updated_at = CURRENT_TIMESTAMP")
                        values.append(email)
                        sql = f"UPDATE accounts SET {', '.join(fields)} WHERE email = ?"
                        cursor.execute(sql, values)
                        print(f"[DB] 更新账号: {email}, 状态: {status}")
                else:
                    # 插入新记录
                    cursor.execute('''
                        INSERT INTO accounts (email, password, recovery_email, secret_key, verification_link, status, message)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (email, password, recovery_email, secret_key, link, status or 'pending', message))
                    print(f"[DB] 插入新账号: {email}, 状态: {status or 'pending'}")
                
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[DB ERROR] upsert_account 失败，email: {email}, 错误: {e}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def update_status(email, status, message=None):
        DBManager.upsert_account(email, status=status, message=message)

    @staticmethod
    def get_accounts_by_status(status):
        with lock:
            conn = DBManager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE status = ?", (status,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
            
    @staticmethod
    def get_all_accounts():
        with lock:
            conn = DBManager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts")
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]

    @staticmethod
    def export_to_files():
        """将数据库导出为传统文本文件，方便查看 (覆盖写入)"""
        print("[DB] 开始导出数据库到文本文件...")
        
        files_map = {
            "link_ready": "sheerIDlink.txt",
            "verified": "已验证未绑卡.txt",
            "subscribed": "已绑卡号.txt",
            "ineligible": "无资格号.txt",
            "error": "超时或其他错误.txt"
        }
        
        # link_ready 状态的账号同时也写入"有资格待验证号.txt"作为备份
        pending_file = "有资格待验证号.txt"
        
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM accounts")
                rows = cursor.fetchall()
                conn.close()
                
                print(f"[DB] 从数据库读取了 {len(rows)} 条记录")
                
                # Group by status
                data = {k: [] for k in files_map.keys()}
                pending_data = []  # 单独处理 pending 文件
                
                for row in rows:
                    st = row['status']
                    if st == 'running' or st == 'processing': continue 
                    
                    # Base line construction
                    email = row['email']
                    line_acc = email
                    if row['password']: line_acc += f"----{row['password']}"
                    if row['recovery_email']: line_acc += f"----{row['recovery_email']}"
                    if row['secret_key']: line_acc += f"----{row['secret_key']}"

                    if st == 'link_ready':
                        # Add to link file
                        if row['verification_link']:
                            line_link = f"{row['verification_link']}----{line_acc}"
                            data['link_ready'].append(line_link)
                        
                        # ALSO Add to pending file (有资格待验证号.txt)
                        pending_data.append(line_acc)
                    
                    elif st in data:
                         data[st].append(line_acc)
                
                # Write main files
                for status, filename in files_map.items():
                    target_path = os.path.join(BASE_DIR, filename)
                    lines = data[status]
                    with open(target_path, 'w', encoding='utf-8') as f:
                        for l in lines:
                            f.write(l + "\n")
                    print(f"[DB] 导出 {len(lines)} 条记录到 {filename}")
                
                # Write pending file separately
                pending_path = os.path.join(BASE_DIR, pending_file)
                with open(pending_path, 'w', encoding='utf-8') as f:
                    for l in pending_data:
                        f.write(l + "\n")
                print(f"[DB] 导出 {len(pending_data)} 条记录到 {pending_file}")
                
                print("[DB] 导出完成！")
        except Exception as e:
            print(f"[DB ERROR] export_to_files 失败: {e}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def save_browser_config(email: str, browser_id: str, config: dict) -> None:
        """保存浏览器配置到数据库"""
        import json
        if not email:
            return
        config_json = json.dumps(config, ensure_ascii=False) if config else None
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM accounts WHERE email = ?", (email,))
                exists = cursor.fetchone() is not None
                if exists:
                    cursor.execute('''
                        UPDATE accounts
                        SET browser_id = ?, browser_config = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE email = ?
                    ''', (browser_id, config_json, email))
                else:
                    cursor.execute('''
                        INSERT INTO accounts (email, browser_id, browser_config)
                        VALUES (?, ?, ?)
                    ''', (email, browser_id, config_json))
                conn.commit()
                conn.close()
                print(f"[DB] 保存浏览器配置: {email} -> {browser_id}")
        except Exception as e:
            print(f"[DB ERROR] save_browser_config 失败: {e}")

    @staticmethod
    def get_browser_config(email: str) -> dict | None:
        """获取浏览器配置"""
        import json
        if not email:
            return None
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT browser_config FROM accounts WHERE email = ?", (email,))
                row = cursor.fetchone()
                conn.close()
                if row and row['browser_config']:
                    return json.loads(row['browser_config'])
        except Exception as e:
            print(f"[DB ERROR] get_browser_config 失败: {e}")
        return None

    @staticmethod
    def get_browser_id(email: str) -> str | None:
        """获取当前浏览器窗口ID"""
        if not email:
            return None
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT browser_id FROM accounts WHERE email = ?", (email,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return row['browser_id']
        except Exception as e:
            print(f"[DB ERROR] get_browser_id 失败: {e}")
        return None

    @staticmethod
    def clear_browser_id(email: str) -> None:
        """清除浏览器ID（删除窗口后调用，保留配置）"""
        if not email:
            return
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE accounts
                    SET browser_id = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                ''', (email,))
                conn.commit()
                conn.close()
                print(f"[DB] 清除浏览器ID: {email}")
        except Exception as e:
            print(f"[DB ERROR] clear_browser_id 失败: {e}")

    @staticmethod
    def get_account_by_email(email: str) -> dict | None:
        """根据邮箱获取账号信息"""
        if not email:
            return None
        try:
            with lock:
                conn = DBManager.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return dict(row)
        except Exception as e:
            print(f"[DB ERROR] get_account_by_email 失败: {e}")
        return None
