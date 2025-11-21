"""
管理员通知器
"""

import logging
from datetime import datetime

from jjz_alert.base.error_exceptions import (
    JJZError,
    ConfigurationError,
    NetworkError,
    APIError,
)


class AdminNotifier:
    """管理员通知器，用于发送系统错误通知"""

    def __init__(self):
        self.last_notification_time = {}
        self.notification_interval = 3600  # 1小时内相同类型错误只通知一次

    async def notify_admin(self, error: Exception, context: str = ""):
        """向管理员发送错误通知"""
        try:
            from jjz_alert.config.config import config_manager
            from jjz_alert.service.notification.unified_pusher import unified_pusher
            from jjz_alert.service.notification.push_priority import PushPriority

            # 获取配置
            config = config_manager.load_config()
            admin_config = config.global_config.admin

            if not admin_config or not admin_config.notifications:
                return

            error_type = type(error).__name__
            current_time = datetime.now().timestamp()

            # 检查是否需要限制通知频率
            last_time = self.last_notification_time.get(error_type, 0)
            if current_time - last_time < self.notification_interval:
                return

            # 构造通知消息
            message = self._build_error_message(error, context)

            # 创建临时配置用于管理员推送
            from jjz_alert.config.config import PlateConfig

            admin_plate_config = PlateConfig(
                plate="ADMIN",
                display_name="管理员",
                notifications=admin_config.notifications,
                icon=None,  # 管理员通知不需要图标
            )

            # 发送通知
            await unified_pusher.push(
                plate_config=admin_plate_config,
                title="🚨 JJZ系统错误告警",
                body=message,
                priority=PushPriority.HIGH,
            )

            # 更新最后通知时间
            self.last_notification_time[error_type] = current_time
            logging.info(f"已向管理员发送错误通知: {error_type}")

        except Exception as e:
            logging.error(f"发送管理员通知失败: {e}")

    def _build_error_message(self, error: Exception, context: str) -> str:
        """构建错误通知消息"""
        lines = []
        lines.append(f"⚠️ 系统错误类型: {type(error).__name__}")
        lines.append(f"📝 错误描述: {str(error)}")

        if context:
            lines.append(f"🔍 错误上下文: {context}")

        if isinstance(error, JJZError):
            lines.append(f"🔢 错误代码: {error.error_code}")
            if error.details:
                lines.append(f"📋 详细信息: {error.details}")

        lines.append(f"⏰ 发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 添加可能的解决方案
        if isinstance(error, ConfigurationError):
            lines.append("💡 建议: 请检查配置文件是否正确")
        elif isinstance(error, NetworkError):
            lines.append("💡 建议: 请检查网络连接和API地址")
        elif isinstance(error, APIError):
            lines.append("💡 建议: 请检查API Token是否有效")
        elif "Token" in str(error) or "token" in str(error):
            lines.append("💡 建议: 进京证Token可能已失效，请更新")

        return "\n".join(lines)


# 全局管理员通知器实例
admin_notifier = AdminNotifier()
