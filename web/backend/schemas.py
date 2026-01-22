"""
Pydantic 数据模型
"""
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum


class AccountStatus(str, Enum):
    pending = "pending"
    link_ready = "link_ready"
    verified = "verified"
    subscribed = "subscribed"
    ineligible = "ineligible"
    error = "error"
    running = "running"


class AccountBase(BaseModel):
    email: str
    password: Optional[str] = None
    recovery_email: Optional[str] = None
    secret_key: Optional[str] = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    password: Optional[str] = None
    recovery_email: Optional[str] = None
    secret_key: Optional[str] = None
    status: Optional[AccountStatus] = None
    message: Optional[str] = None


class Account(AccountBase):
    verification_link: Optional[str] = None
    status: AccountStatus = AccountStatus.pending
    message: Optional[str] = None
    updated_at: Optional[str] = None
    browser_id: Optional[str] = None
    browser_config: Optional[str] = None

    class Config:
        from_attributes = True


class AccountListResponse(BaseModel):
    total: int
    items: List[Account]


class BrowserInfo(BaseModel):
    id: str
    name: Optional[str] = None
    userName: Optional[str] = None  # 关联的邮箱
    seq: Optional[int] = None
    groupName: Optional[str] = None
    proxyMethod: Optional[int] = None
    proxyType: Optional[str] = None


class BrowserCreateRequest(BaseModel):
    email: str
    device_type: str = "pc"  # pc 或 android
    template_browser_id: Optional[str] = None  # 模板浏览器 ID


class TaskType(str, Enum):
    setup_2fa = "setup_2fa"  # 设置 2FA
    reset_2fa = "reset_2fa"  # 修改 2FA
    age_verification = "age_verification"  # 年龄验证
    get_sheerlink = "get_sheerlink"  # 获取 SheerLink
    bind_card = "bind_card"  # 绑卡订阅


class TaskCreateRequest(BaseModel):
    task_types: List[TaskType]  # 支持多选任务类型
    emails: List[str]  # 要执行任务的账号列表
    close_after: bool = False  # 执行完成后是否关闭浏览器
    concurrency: int = 1  # 并发数（1-5）


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AccountProgressStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AccountProgress(BaseModel):
    """单个账号的执行进度"""
    email: str
    status: AccountProgressStatus = AccountProgressStatus.pending
    current_task: Optional[str] = None
    message: Optional[str] = None


class TaskProgress(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus
    total: int
    completed: int
    current_email: Optional[str] = None
    message: Optional[str] = None


class ImportRequest(BaseModel):
    content: str  # 导入的文本内容，每行一个账号
    separator: str = "----"  # 分隔符


class ExportResponse(BaseModel):
    content: str
    count: int


class ConfigUpdate(BaseModel):
    """配置更新请求"""
    sheerid_api_key: Optional[str] = None
    card_number: Optional[str] = None
    card_exp_month: Optional[str] = None
    card_exp_year: Optional[str] = None
    card_cvv: Optional[str] = None
    card_zip: Optional[str] = None


class ConfigResponse(BaseModel):
    """配置响应"""
    sheerid_api_key: str = ""
    card_number: str = ""
    card_exp_month: str = ""
    card_exp_year: str = ""
    card_cvv: str = ""
    card_zip: str = ""
