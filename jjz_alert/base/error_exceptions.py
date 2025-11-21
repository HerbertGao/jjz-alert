"""
JJZ系统异常定义
"""

from datetime import datetime
from typing import Any, Dict, Optional


class JJZError(Exception):
    """JJZ系统基础异常"""

    def __init__(
        self, message: str, error_code: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now()


class ConfigurationError(JJZError):
    """配置错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "CONFIG_ERROR", details)


class NetworkError(JJZError):
    """网络连接错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "NETWORK_ERROR", details)


class APIError(JJZError):
    """API调用错误"""

    def __init__(
        self, message: str, status_code: int = None, details: Dict[str, Any] = None
    ):
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, "API_ERROR", details)


class CacheError(JJZError):
    """缓存操作错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "CACHE_ERROR", details)


class RetryableError(JJZError):
    """可重试的错误"""

    def __init__(
        self, message: str, retry_after: int = 5, details: Dict[str, Any] = None
    ):
        details = details or {}
        details["retry_after"] = retry_after
        super().__init__(message, "RETRYABLE_ERROR", details)


class RedisError(JJZError):
    """Redis操作错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "REDIS_ERROR", details)


class PushError(JJZError):
    """推送服务错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "PUSH_ERROR", details)


class TrafficServiceError(JJZError):
    """限行服务错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "TRAFFIC_SERVICE_ERROR", details)
