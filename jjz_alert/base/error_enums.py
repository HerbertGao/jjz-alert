"""
错误处理相关枚举定义
"""

from enum import Enum


class ErrorSeverity(Enum):
    """错误严重级别"""

    LOW = "low"  # 轻微错误，记录但不影响系统运行
    MEDIUM = "medium"  # 中等错误，可能影响部分功能，需要关注
    HIGH = "high"  # 高级错误，影响主要功能，需要立即处理
    CRITICAL = "critical"  # 严重错误，系统无法正常运行，需要紧急修复


class RecoveryStrategy(Enum):
    """恢复策略"""

    NONE = "none"  # 无恢复策略
    RETRY = "retry"  # 重试
    FALLBACK = "fallback"  # 使用备用方案
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断
    GRACEFUL_DEGRADATION = "graceful_degradation"  # 优雅降级

