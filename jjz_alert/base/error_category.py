"""
错误分类管理
"""

from typing import Type, Optional

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
from jjz_alert.base.error_enums import ErrorSeverity, RecoveryStrategy


class ErrorCategory:
    """错误分类管理"""

    # 默认错误严重级别映射
    DEFAULT_SEVERITY_MAPPING = {
        ConfigurationError: ErrorSeverity.HIGH,
        NetworkError: ErrorSeverity.MEDIUM,
        APIError: ErrorSeverity.HIGH,
        CacheError: ErrorSeverity.MEDIUM,
        RetryableError: ErrorSeverity.LOW,
        RedisError: ErrorSeverity.HIGH,
        PushError: ErrorSeverity.MEDIUM,
        TrafficServiceError: ErrorSeverity.MEDIUM,
    }

    # 默认错误恢复策略映射
    DEFAULT_RECOVERY_MAPPING = {
        ConfigurationError: RecoveryStrategy.FALLBACK,
        NetworkError: RecoveryStrategy.RETRY,
        APIError: RecoveryStrategy.RETRY,
        CacheError: RecoveryStrategy.GRACEFUL_DEGRADATION,
        RetryableError: RecoveryStrategy.RETRY,
        RedisError: RecoveryStrategy.RETRY,
        PushError: RecoveryStrategy.GRACEFUL_DEGRADATION,
        TrafficServiceError: RecoveryStrategy.RETRY,
    }

    SEVERITY_MAPPING = DEFAULT_SEVERITY_MAPPING.copy()
    RECOVERY_MAPPING = DEFAULT_RECOVERY_MAPPING.copy()

    @classmethod
    def get_severity(cls, error: Exception) -> ErrorSeverity:
        """获取错误严重级别"""
        error_type = type(error)
        return cls.SEVERITY_MAPPING.get(error_type, ErrorSeverity.MEDIUM)

    @classmethod
    def get_recovery_strategy(cls, error: Exception) -> RecoveryStrategy:
        """获取错误恢复策略"""
        error_type = type(error)
        return cls.RECOVERY_MAPPING.get(error_type, RecoveryStrategy.NONE)

    @classmethod
    def should_notify_admin(cls, error: Exception) -> bool:
        """判断是否需要通知管理员"""
        severity = cls.get_severity(error)
        return severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]

    @classmethod
    def should_auto_recover(cls, error: Exception) -> bool:
        """判断是否应该自动恢复"""
        strategy = cls.get_recovery_strategy(error)
        return strategy != RecoveryStrategy.NONE

    @classmethod
    def register_error(
        cls,
        error_type: Type[Exception],
        severity: Optional[ErrorSeverity] = None,
        recovery_strategy: Optional[RecoveryStrategy] = None,
    ) -> None:
        """动态注册新的错误类型配置"""
        if severity:
            cls.SEVERITY_MAPPING[error_type] = severity
        if recovery_strategy:
            cls.RECOVERY_MAPPING[error_type] = recovery_strategy

    @classmethod
    def reset(cls) -> None:
        """恢复到默认映射（主要用于测试）"""
        cls.SEVERITY_MAPPING = cls.DEFAULT_SEVERITY_MAPPING.copy()
        cls.RECOVERY_MAPPING = cls.DEFAULT_RECOVERY_MAPPING.copy()
