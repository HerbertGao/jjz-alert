"""
日志分类枚举定义
"""

from enum import Enum


class LogCategory(Enum):
    """日志分类"""

    SYSTEM = "system"  # 系统级日志
    BUSINESS = "business"  # 业务逻辑日志
    PERFORMANCE = "performance"  # 性能相关日志
    SECURITY = "security"  # 安全相关日志
    API = "api"  # API调用日志
    ERROR = "error"  # 错误日志

