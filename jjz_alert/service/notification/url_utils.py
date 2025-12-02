"""
URL 处理工具函数

提供 URL 占位符处理和解析的共享逻辑
"""

import logging
from typing import Optional, Tuple, Union

from jjz_alert.config.config_models import AppriseUrlConfig
from jjz_alert.service.notification.push_priority import PushPriority, PriorityMapper


def process_url_placeholders(
    url: str,
    plate: str,
    display_name: str,
    priority: PushPriority,
    icon: Optional[str] = None,
) -> str:
    """
    处理 URL 中的变量占位符

    Args:
        url: 原始 URL
        plate: 车牌号
        display_name: 显示名称
        priority: 优先级
        icon: 图标 URL

    Returns:
        处理后的 URL
    """
    try:
        # 替换图标占位符
        if icon:
            url = url.replace("{icon}", icon)
        else:
            # 如果没有指定图标，移除 icon 参数
            url = (
                url.replace("&icon={icon}", "")
                .replace("?icon={icon}&", "?")
                .replace("?icon={icon}", "")
            )

        # 替换基本占位符
        url = url.replace("{plate}", plate)
        url = url.replace("{display_name}", display_name)

        # 替换优先级占位符
        # {level} 用于 Bark URL，{priority} 用于其他 Apprise 服务
        url = url.replace("{level}", PriorityMapper.get_bark_level(priority))
        url = url.replace(
            "{priority}",
            PriorityMapper.get_platform_priority(priority, "apprise"),
        )

        return url

    except Exception as e:
        logging.error(f"处理 URL 占位符失败: {e}")
        return url


def parse_apprise_url_item(
    url_item: Union[str, AppriseUrlConfig, dict],
) -> Tuple[str, Optional[str]]:
    """
    解析 Apprise URL 配置项

    Args:
        url_item: URL 配置（字符串、AppriseUrlConfig 或字典）

    Returns:
        (url, batch_key) - URL 字符串和批量推送键（如果有）
    """
    if isinstance(url_item, str):
        return url_item, None
    elif isinstance(url_item, AppriseUrlConfig):
        return url_item.url, url_item.batch_key
    elif isinstance(url_item, dict):
        return url_item.get("url", ""), url_item.get("batch_key")
    else:
        return "", None
