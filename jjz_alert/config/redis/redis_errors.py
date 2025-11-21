"""
Redis 异常定义
"""

from jjz_alert.base.error_handler import RedisError


class RedisConnectionError(RedisError):
    """Redis连接错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)


class RedisTimeoutError(RedisError):
    """Redis超时错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)
