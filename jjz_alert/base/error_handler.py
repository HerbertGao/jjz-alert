"""
错误处理工具模块

提供统一的错误分类、重试机制和监控
"""

from jjz_alert.base.admin_notifier import AdminNotifier
from jjz_alert.base.admin_notifier import admin_notifier
from jjz_alert.base.circuit_breaker import CircuitBreaker

# 导入工具类
from jjz_alert.base.error_category import ErrorCategory
from jjz_alert.base.error_collector import ErrorCollector

# 导入全局实例
from jjz_alert.base.error_collector import error_collector

# 导入装饰器
from jjz_alert.base.error_decorators import with_error_handling, with_retry

# 导入枚举类
from jjz_alert.base.error_enums import ErrorSeverity, RecoveryStrategy

# 导入所有异常类
from jjz_alert.base.error_exceptions import (
    JJZError,
    ConfigurationError,
    NetworkError,
    APIError,
    CacheError,
    RetryableError,
    RedisError,
    PushError,
    TrafficServiceError,
)

# 导入工具函数
from jjz_alert.base.error_utils import (
    handle_critical_error,
    is_token_error,
    get_error_handling_status,
)
from jjz_alert.base.recovery_manager import AutoRecoveryManager
from jjz_alert.base.recovery_manager import recovery_manager

# 导出所有内容，保持向后兼容
__all__ = [
    # 异常类
    "JJZError",
    "ConfigurationError",
    "NetworkError",
    "APIError",
    "CacheError",
    "RetryableError",
    "RedisError",
    "PushError",
    "TrafficServiceError",
    # 枚举类
    "ErrorSeverity",
    "RecoveryStrategy",
    # 工具类
    "ErrorCategory",
    "CircuitBreaker",
    "AutoRecoveryManager",
    "ErrorCollector",
    "AdminNotifier",
    # 装饰器
    "with_error_handling",
    "with_retry",
    # 工具函数
    "handle_critical_error",
    "is_token_error",
    "get_error_handling_status",
    # 全局实例
    "error_collector",
    "admin_notifier",
    "recovery_manager",
]
