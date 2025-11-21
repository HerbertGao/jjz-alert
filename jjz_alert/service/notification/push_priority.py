"""
推送优先级相关枚举和映射器
"""

from enum import Enum
from typing import Dict


class PushPriority(Enum):
    """推送优先级"""

    NORMAL = "normal"
    HIGH = "high"


class PlatformPriority(Enum):
    """不同平台的优先级映射"""

    # Apprise通用优先级
    APPRISE_LOW = "low"
    APPRISE_NORMAL = "normal"
    APPRISE_HIGH = "high"
    APPRISE_URGENT = "urgent"
    APPRISE_CRITICAL = "critical"

    # Bark特定优先级
    BARK_ACTIVE = "active"
    BARK_CRITICAL = "critical"

    # 其他平台可以在这里添加
    # TELEGRAM_NORMAL = "normal"
    # TELEGRAM_HIGH = "high"
    # EMAIL_LOW = "low"
    # EMAIL_HIGH = "high"


class PriorityMapper:
    """优先级映射器"""

    # 从PushPriority到各平台的映射
    PRIORITY_MAPPINGS = {
        PushPriority.NORMAL: {
            "apprise": PlatformPriority.APPRISE_NORMAL,
            "bark": PlatformPriority.BARK_ACTIVE,
        },
        PushPriority.HIGH: {
            "apprise": PlatformPriority.APPRISE_HIGH,
            "bark": PlatformPriority.BARK_CRITICAL,
        },
    }

    @classmethod
    def get_platform_priority(cls, priority: PushPriority, platform: str) -> str:
        """
        获取指定平台的优先级值

        Args:
            priority: 统一优先级
            platform: 平台名称 ('apprise', 'bark', etc.)

        Returns:
            平台特定的优先级值
        """
        if priority not in cls.PRIORITY_MAPPINGS:
            # 默认使用normal
            priority = PushPriority.NORMAL

        platform_mapping = cls.PRIORITY_MAPPINGS[priority]
        if platform not in platform_mapping:
            # 如果平台不存在，使用apprise作为默认
            platform = "apprise"

        return platform_mapping[platform].value

    @classmethod
    def get_all_platform_priorities(cls, priority: PushPriority) -> Dict[str, str]:
        """
        获取所有平台的优先级映射

        Args:
            priority: 统一优先级

        Returns:
            所有平台的优先级映射字典
        """
        if priority not in cls.PRIORITY_MAPPINGS:
            priority = PushPriority.NORMAL

        return {
            platform: mapping.value
            for platform, mapping in cls.PRIORITY_MAPPINGS[priority].items()
        }

