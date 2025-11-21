"""
推送辅助函数

为main函数提供便捷的推送接口
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional

from jjz_alert.config import PlateConfig
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.notification.unified_pusher import unified_pusher
from jjz_alert.service.notification.push_priority import PushPriority


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
        from jjz_alert.service.jjz.jjz_utils import (
            format_jjz_push_content,
            format_jjz_expired_content,
            format_jjz_pending_content,
            format_jjz_error_content,
        )

        # 添加状态和优先级判断的调试日志
        logging.debug(
            f"[STATUS_DEBUG] 车牌 {plate} - JJZ状态: {status}, 有效期: {valid_end}, 剩余天数: {days_remaining}"
        )

        if status == JJZStatusEnum.VALID.value:
            priority = PushPriority.NORMAL
            logging.debug(
                f"[STATUS_DEBUG] 车牌 {plate} - 状态为VALID，设置优先级为NORMAL"
            )
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
            logging.debug(
                f"[STATUS_DEBUG] 车牌 {plate} - 状态为EXPIRED，设置优先级为HIGH"
            )
            body = format_jjz_expired_content(display_name, sycs)

        elif status == JJZStatusEnum.PENDING.value:
            priority = PushPriority.HIGH
            logging.debug(
                f"[STATUS_DEBUG] 车牌 {plate} - 状态为PENDING，设置优先级为HIGH"
            )
            apply_time = jjz_data.get("apply_time", "未知")
            body = format_jjz_pending_content(
                display_name=display_name,
                jjzzlmc=jjz_data.get("jjzzlmc", ""),
                apply_time=apply_time,
            )

        else:
            # 检查是否为系统级错误，如果是则跳过用户推送并通知管理员
            error_msg = jjz_data.get("error_message", "")
            if _is_system_error(error_msg):
                logging.warning(f"车牌 {plate} 因系统级错误跳过用户推送: {error_msg}")

                # 通知管理员系统错误
                await _notify_admin_system_error(plate, display_name, error_msg)

                return {
                    "plate": plate,
                    "success_count": 0,
                    "total_count": 0,
                    "skipped": True,
                    "skip_reason": "系统级错误",
                    "error": error_msg,
                }

            priority = PushPriority.NORMAL
            logging.debug(
                f"[STATUS_DEBUG] 车牌 {plate} - 状态为{status}，设置优先级为NORMAL"
            )
            body = format_jjz_error_content(
                display_name=display_name,
                jjzzlmc=jjz_data.get("jjzzlmc", ""),
                status=status,
                error_msg=error_msg,
            )

        # 根据限行提醒在正文最前拼接提示
        try:
            if traffic_reminder:
                reminder_text = str(traffic_reminder).strip()
                if reminder_text in ("今日限行", "明日限行"):
                    # 使用模板管理器格式化限行提醒
                    from jjz_alert.base.message_templates import template_manager

                    reminder_prefix = template_manager.format_traffic_reminder(
                        reminder_text
                    )
                    body = reminder_prefix + body
        except Exception:
            pass

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
    plate_configs: list = None,
    title: str = "",
    message: str = "",
    priority: PushPriority = PushPriority.NORMAL,
    category: str = "admin",
) -> Dict[str, Any]:
    """
    推送管理员通知

    Args:
        plate_configs: 车牌配置列表（可选，为空时使用全局管理员配置）
        title: 标题
        message: 消息内容
        priority: 优先级
        category: 分类

    Returns:
        推送结果
    """
    try:
        from jjz_alert.config.config import config_manager

        # 获取全局管理员通知配置
        app_config = config_manager.load_config()
        admin_notifications = app_config.global_config.admin.notifications

        if not admin_notifications:
            return {
                "success_count": 0,
                "total_count": 0,
                "errors": ["未配置管理员通知"],
                "timestamp": datetime.now().isoformat(),
            }

        # 创建管理员配置
        admin_config = PlateConfig(
            plate="ADMIN",
            display_name="管理员",
            notifications=admin_notifications,
            icon="https://cdn-icons-png.flaticon.com/512/1077/1077114.png",  # 管理员图标
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


def _is_system_error(error_msg: str) -> bool:
    """
    检测是否为系统级错误

    Args:
        error_msg: 错误信息

    Returns:
        是否为系统级错误
    """
    if not error_msg:
        return False

    # 系统级错误关键词
    system_error_keywords = [
        # 网络相关错误
        "TLS connect error",
        "OPENSSL_internal",
        "curl: (35)",
        "网络连接失败",
        "网络TLS错误",
        "TLS连接失败",
        "Connection",
        "timeout",
        "网络错误",
        "连接超时",
        "SSL",
        "TLS",
        "certificate",
        "handshake",
        # API相关错误
        "Session.request() got an unexpected keyword argument",
        "HTTP POST请求失败",
        "HTTP GET请求失败",
        "进京证查询失败",
        # 系统级错误
        "系统错误",
        "服务不可用",
        "服务器错误",
        "API错误",
        "配置错误",
        "未配置",
        "初始化失败",
    ]

    error_msg_lower = error_msg.lower()
    return any(keyword.lower() in error_msg_lower for keyword in system_error_keywords)


async def _notify_admin_system_error(plate: str, display_name: str, error_msg: str):
    """
    通知管理员系统级错误

    Args:
        plate: 车牌号
        display_name: 显示名称
        error_msg: 错误信息
    """
    try:
        # 构建通知消息
        title = "🚨 进京证查询系统错误"
        message = f"""
🚗 车牌: {display_name} ({plate})
❌ 错误类型: 系统级错误
📝 错误详情: {error_msg}
⏰ 发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
💡 建议: 请检查系统配置和服务器状态
🔄 处理: 已跳过用户推送，仅通知管理员
        """.strip()

        # 直接使用全局管理员配置发送通知
        await push_admin_notification(
            title=title,
            message=message,
            priority=PushPriority.HIGH,
            category="system_error",
        )

        logging.info(f"已向管理员发送系统错误通知: {plate}")

    except Exception as e:
        logging.error(f"发送管理员系统错误通知失败: {e}")


async def _notify_admin_network_error(plate: str, display_name: str, error_msg: str):
    """
    通知管理员网络错误（保留向后兼容）

    Args:
        plate: 车牌号
        display_name: 显示名称
        error_msg: 错误信息
    """
    # 调用系统错误通知函数
    await _notify_admin_system_error(plate, display_name, error_msg)
