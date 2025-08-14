"""
推送辅助函数

为main函数提供便捷的推送接口
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional

from config import PlateConfig
from service.notification.unified_pusher import unified_pusher, PushPriority
from service.jjz.jjz_status import JJZStatusEnum


async def push_jjz_status(
    plate_config: PlateConfig,
    jjz_data: Dict[str, Any],
    target_date: Optional[date] = None,
    is_next_day: bool = False,
    traffic_reminder: str = None,
) -> Dict[str, Any]:
    """
    推送进京证状态

    Args:
        plate_config: 车牌配置
        jjz_data: 进京证数据
        target_date: 目标日期
        is_next_day: 是否为次日推送
        traffic_reminder: 限行提醒信息（如"今日限行"、"明日限行"）

    Returns:
        推送结果
    """
    try:
        plate = plate_config.plate
        display_name = plate_config.display_name or plate

        # 构建推送内容
        status = jjz_data.get("status", "unknown")
        days_remaining = jjz_data.get("days_remaining")
        valid_end = jjz_data.get("valid_end")
        sycs = jjz_data.get("sycs")  # 六环内剩余办理次数

        # 根据状态确定推送参数
        from utils.jjz_utils import (
            format_jjz_push_content,
            format_jjz_expired_content,
            format_jjz_pending_content,
            format_jjz_error_content,
        )

        if status == JJZStatusEnum.VALID.value:
            priority = PushPriority.NORMAL
            body = format_jjz_push_content(
                display_name=display_name,
                jjzzlmc=jjz_data.get("jjzzlmc", ""),
                blztmc=jjz_data.get("blztmc", ""),
                status=status,
                valid_start=jjz_data.get("valid_start", "未知"),
                valid_end=valid_end,
                days_remaining=days_remaining,
                sycs=sycs,
            )

        elif status == JJZStatusEnum.EXPIRED.value:
            priority = PushPriority.HIGH
            body = format_jjz_expired_content(display_name, sycs)

        elif status == JJZStatusEnum.PENDING.value:
            priority = PushPriority.HIGH
            apply_time = jjz_data.get("apply_time", "未知")
            body = format_jjz_pending_content(
                display_name=display_name,
                jjzzlmc=jjz_data.get("jjzzlmc", ""),
                apply_time=apply_time,
            )

        else:
            priority = PushPriority.NORMAL
            error_msg = jjz_data.get("error_message", "")
            body = format_jjz_error_content(
                display_name=display_name,
                jjzzlmc=jjz_data.get("jjzzlmc", ""),
                status=status,
                error_msg=error_msg,
            )

        # 使用显示名称作为标题
        title = display_name

        # 发送推送
        result = await unified_pusher.push(
            plate_config=plate_config,
            title=title,
            body=body,
            priority=priority,
            icon=plate_config.icon,  # 传递图标
        )

        return result

    except Exception as e:
        error_msg = f"推送进京证状态失败: {e}"
        logging.error(error_msg)
        return {
            "plate": getattr(plate_config, "plate", "unknown"),
            "success_count": 0,
            "total_count": 0,
            "errors": [error_msg],
            "timestamp": datetime.now().isoformat(),
        }


async def push_jjz_reminder(
    plate_config: PlateConfig, message: str, priority: PushPriority = PushPriority.HIGH
) -> Dict[str, Any]:
    """
    推送进京证提醒

    Args:
        plate_config: 车牌配置
        message: 提醒消息
        priority: 优先级
        category: 分类

    Returns:
        推送结果
    """
    try:
        plate = plate_config.plate
        display_name = plate_config.display_name or plate

        title = display_name

        body = message

        # 发送推送
        result = await unified_pusher.push(
            plate_config=plate_config,
            title=title,
            body=body,
            priority=priority,
            icon=plate_config.icon,  # 传递图标
        )

        return result

    except Exception as e:
        error_msg = f"推送进京证提醒失败: {e}"
        logging.error(error_msg)
        return {
            "plate": getattr(plate_config, "plate", "unknown"),
            "success_count": 0,
            "total_count": 0,
            "errors": [error_msg],
            "timestamp": datetime.now().isoformat(),
        }


async def push_admin_notification(
    plate_configs: list,
    title: str,
    message: str,
    priority: PushPriority = PushPriority.NORMAL,
) -> Dict[str, Any]:
    """
    推送管理员通知

    Args:
        plate_configs: 车牌配置列表
        title: 标题
        message: 消息内容
        priority: 优先级
        category: 分类

    Returns:
        推送结果
    """
    try:
        # 使用第一个车牌配置的管理员通知
        if not plate_configs:
            return {
                "success_count": 0,
                "total_count": 0,
                "errors": ["没有可用的车牌配置"],
                "timestamp": datetime.now().isoformat(),
            }

        # 创建临时配置用于管理员推送
        admin_config = PlateConfig(
            plate="ADMIN",
            display_name="管理员",
            notifications=plate_configs[0].notifications,  # 使用第一个配置的通知设置
            icon=plate_configs[0].icon,
        )

        # 发送推送
        result = await unified_pusher.push(
            plate_config=admin_config, title=title, body=message, priority=priority
        )

        return result

    except Exception as e:
        error_msg = f"推送管理员通知失败: {e}"
        logging.error(error_msg)
        return {
            "success_count": 0,
            "total_count": 0,
            "errors": [error_msg],
            "timestamp": datetime.now().isoformat(),
        }
