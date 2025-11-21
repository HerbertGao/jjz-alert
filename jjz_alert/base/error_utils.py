"""
错误处理工具函数
"""

import asyncio
from typing import Any, Dict

from jjz_alert.base.error_exceptions import (
    ConfigurationError,
    APIError,
    NetworkError,
)
from jjz_alert.base.error_collector import error_collector
from jjz_alert.base.admin_notifier import admin_notifier


def _run_async_safe(coro: asyncio.Future) -> None:
    """
    在同步上下文中安全运行异步任务。

    - 如果当前已有事件循环，则创建后台任务
    - 否则使用 asyncio.run 创建新的事件循环
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    loop.create_task(coro)


async def handle_critical_error(error: Exception, context: str = ""):
    """处理关键错误，记录并通知管理员"""
    error_collector.record_error(error, context)

    # 对于关键错误类型，通知管理员
    critical_errors = (ConfigurationError, APIError, NetworkError)
    if isinstance(error, critical_errors) or "Token" in str(error):
        await admin_notifier.notify_admin(error, context)


def is_token_error(error: Exception) -> bool:
    """检查是否为Token相关错误"""
    error_msg = str(error).lower()
    token_keywords = ["token", "unauthorized", "403", "401", "认证失败", "令牌"]
    return any(keyword in error_msg for keyword in token_keywords)


def get_error_handling_status() -> Dict[str, Any]:
    """获取错误处理系统状态"""
    try:
        from jjz_alert.base.recovery_manager import recovery_manager

        error_summary = error_collector.get_error_summary()
        recovery_status = recovery_manager.get_status()

        return {
            "status": "healthy",
            "error_collector": {
                "total_errors": error_summary.get("total_errors", 0),
                "error_types": error_summary.get("error_counts", {}),
                "recent_errors": len(error_summary.get("recent_errors", [])),
            },
            "recovery_manager": {
                "circuit_breakers_count": len(
                    recovery_status.get("circuit_breakers", {})
                ),
                "open_circuit_breakers": [
                    name
                    for name, status in recovery_status.get(
                        "circuit_breakers", {}
                    ).items()
                    if status.get("state") == "open"
                ],
                "recovery_attempts": len(recovery_status.get("recovery_attempts", {})),
            },
            "admin_notifier": {
                "notification_interval": admin_notifier.notification_interval,
                "last_notifications": len(admin_notifier.last_notification_time),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

