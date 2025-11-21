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

class PriorityMapper:
    """优先级映射器"""

    # 从PushPriority到各平台的映射
    PRIORITY_MAPPINGS = {
        PushPriority.NORMAL: {
            "apprise": PlatformPriority.APPRISE_NORMAL,
        },
        PushPriority.HIGH: {
            "apprise": PlatformPriority.APPRISE_HIGH,
        },
    }

    # Bark URL 占位符映射（基于 Apprise Bark 插件支持）
    # Apprise Bark 支持的 level: active, timeSensitive, passive, critical
    # 参考：https://github.com/caronc/apprise/blob/master/apprise/plugins/bark.py
    BARK_LEVEL_MAPPINGS = {
        PushPriority.NORMAL: "active",
        PushPriority.HIGH: "critical",
    }

    @classmethod
    def get_platform_priority(cls, priority: PushPriority, platform: str) -> str:
        """
        获取指定平台的优先级值

        Args:
            priority: 统一优先级
            platform: 平台名称 ('apprise' 等)

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
    def get_bark_level(cls, priority: PushPriority) -> str:
        """
        获取 Bark URL 占位符的 level 值

        Args:
            priority: 统一优先级

        Returns:
            Bark 特定的 level 值 (active/critical)
        """
        return cls.BARK_LEVEL_MAPPINGS.get(priority, "active")

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
