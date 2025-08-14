"""
统一推送入口服务

提供包括紧急程度、分类、分组、自定义图标等多种额外参数的推送服务
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Union

from config import PlateConfig, NotificationConfig
from service.cache.cache_service import cache_service
from service.notification.apprise_pusher import apprise_pusher


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


class UnifiedPusher:
    """统一推送入口服务"""

    def __init__(self):

        self.apprise_enabled = True

    async def push(
            self,
            plate_config: PlateConfig,
            title: str,
            body: str,
            priority: Union[PushPriority, str] = PushPriority.NORMAL,
            group: Optional[str] = None,
            icon: Optional[str] = None,
            sound: Optional[str] = None,
            badge: Optional[int] = None,
            url: Optional[str] = None,
            actions: Optional[List[str]] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        """
        统一推送入口方法

        Args:
            plate_config: 车牌配置
            title: 推送标题
            body: 推送内容
            priority: 推送优先级 (low, normal, high, urgent, critical)
            group: 推送分组
            icon: 自定义图标URL
            sound: 自定义声音
            badge: 角标数字
            url: 点击跳转URL
            actions: 操作按钮列表
            **kwargs: 其他参数

        Returns:
            推送结果汇总
        """
        try:
            # 标准化参数
            priority = self._normalize_priority(priority)

            # 设置默认group为车牌号
            if group is None:
                group = plate_config.plate

            # 构建推送参数
            push_params = {
                "priority": priority,
                "group": group,
                "icon": icon,
                "sound": sound,
                "badge": badge,
                "url": url,
                "actions": actions,
                **kwargs,
            }

            # 根据优先级调整推送参数
            push_params = self._adjust_params_by_priority(push_params, priority)

            # 发送推送
            return await self._send_notifications(
                plate_config, title, body, push_params
            )

        except Exception as e:
            error_msg = f"统一推送异常: {e}"
            logging.error(error_msg)
            return {
                "plate": getattr(plate_config, "plate", "unknown"),
                "success_count": 0,
                "total_count": 0,
                "errors": [error_msg],
                "timestamp": datetime.now().isoformat(),
            }

    def _normalize_priority(self, priority: Union[PushPriority, str]) -> PushPriority:
        """标准化优先级"""
        if isinstance(priority, PushPriority):
            return priority

        priority_str = str(priority).lower()
        try:
            return PushPriority(priority_str)
        except ValueError:
            logging.warning(f"未知的优先级: {priority}, 使用默认值 NORMAL")
            return PushPriority.NORMAL

    def _adjust_params_by_priority(
            self, params: Dict[str, Any], priority: PushPriority
    ) -> Dict[str, Any]:
        """根据优先级调整推送参数"""
        adjusted_params = params.copy()

        # 根据优先级设置声音
        if not adjusted_params.get("sound"):
            priority_sounds = {
                PushPriority.NORMAL: "default",
                PushPriority.HIGH: "alarm",
            }
            adjusted_params["sound"] = priority_sounds.get(priority, "default")

        return adjusted_params

    def _process_url_placeholders(
            self, url: str, plate: str, display_name: str, push_params: Dict[str, Any]
    ) -> str:
        """处理URL中的变量占位符"""
        try:
            # 替换图标占位符（先处理，避免影响其他参数）
            icon = push_params.get("icon")
            if icon:
                url = url.replace("{icon}", icon)
            else:
                # 如果没有指定图标，移除icon参数
                url = (
                    url.replace("&icon={icon}", "")
                    .replace("?icon={icon}&", "?")
                    .replace("?icon={icon}", "")
                )

            # 替换基本占位符
            url = url.replace("{plate}", plate)
            url = url.replace("{display_name}", display_name)

            # 替换优先级占位符
            priority = push_params.get("priority", PushPriority.NORMAL)
            if hasattr(priority, "value"):
                priority_str = priority.value
            else:
                priority_str = str(priority)

            # 使用PriorityMapper获取各平台的优先级
            priority_enum = (
                PushPriority(priority_str)
                if priority_str in ["normal", "high"]
                else PushPriority.NORMAL
            )
            platform_priorities = PriorityMapper.get_all_platform_priorities(
                priority_enum
            )

            # 替换URL中的占位符
            url = url.replace(
                "{level}", platform_priorities.get("bark", "active")
            )  # 对于Bark URL，使用bark级别
            url = url.replace(
                "{priority}", platform_priorities.get("apprise", "normal")
            )  # 对于其他Apprise服务，使用apprise优先级

            return url

        except Exception as e:
            logging.error(f"处理URL占位符失败: {e}")
            return url

    async def _send_notifications(
            self,
            plate_config: PlateConfig,
            title: str,
            body: str,
            push_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送推送通知"""
        try:
            plate = plate_config.plate
            display_name = plate_config.display_name or plate

            # 准备推送结果汇总
            results = {
                "plate": plate,
                "display_name": display_name,
                "title": title,
                "body": body,
                "priority": push_params["priority"].value,
                "group": push_params.get("group"),
                "timestamp": datetime.now().isoformat(),
                "notifications": [],
                "success_count": 0,
                "total_count": 0,
                "errors": [],
            }

            # 串行执行所有推送任务
            for i, notification in enumerate(plate_config.notifications):
                try:
                    # 发送单个推送通知
                    result = await self._send_single_notification(
                        notification=notification,
                        title=title,
                        body=body,
                        plate=plate,
                        display_name=display_name,
                        notification_index=i,
                        push_params=push_params,
                    )
                    
                    results["notifications"].append(result)
                    # 累加URL级别的统计
                    results["total_count"] += result.get("total_count", 0)
                    results["success_count"] += result.get("success_count", 0)
                    
                except Exception as e:
                    error_msg = f"推送任务异常: {e}"
                    logging.error(error_msg)
                    results["errors"].append(error_msg)
                    results["notifications"].append(
                        {"success": False, "error": str(e), "total_count": 0, "success_count": 0}
                    )

            # 记录推送历史
            await self._record_push_history(plate, results)

            # 记录推送统计
            success_rate = (
                (results["success_count"] / results["total_count"] * 100)
                if results["total_count"] > 0
                else 0
            )
            logging.info(
                f"车牌{plate}推送完成: {results['success_count']}/{results['total_count']} "
                f"成功率{success_rate:.1f}% (优先级:{push_params['priority'].value})"
            )

            return results

        except Exception as e:
            error_msg = f"推送服务异常: {e}"
            logging.error(error_msg)
            return {
                "plate": getattr(plate_config, "plate", "unknown"),
                "success_count": 0,
                "total_count": 0,
                "errors": [error_msg],
                "timestamp": datetime.now().isoformat(),
            }

    async def _send_single_notification(
            self,
            notification: NotificationConfig,
            title: str,
            body: str,
            plate: str,
            display_name: str,
            notification_index: int,
            push_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送单个推送通知"""
        try:
            notification_result = {
                "type": notification.type,
                "index": notification_index,
                "success": False,
                "total_count": 0,
                "success_count": 0,
                "timestamp": datetime.now().isoformat(),
            }

            if notification.type == "apprise":
                # Apprise推送
                result = await self._send_apprise_notification(
                    notification, title, body, plate, display_name, push_params
                )
                notification_result.update(result)

            else:
                error_msg = f"未知的推送类型: {notification.type}"
                logging.error(error_msg)
                notification_result["error"] = error_msg

            return notification_result

        except Exception as e:
            logging.error(f"单个推送通知失败: {e}")
            return {
                "type": notification.type,
                "index": notification_index,
                "success": False,
                "total_count": 0,
                "success_count": 0,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _send_apprise_notification(
            self,
            notification: NotificationConfig,
            title: str,
            body: str,
            plate: str,
            display_name: str,
            push_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送Apprise推送通知"""
        try:
            if not self.apprise_enabled:
                return {
                    "success": False, 
                    "error": "Apprise推送已禁用",
                    "total_count": 0,
                    "success_count": 0
                }

            # 处理URL中的变量占位符
            processed_urls = []
            for url in notification.urls:
                processed_url = self._process_url_placeholders(
                    url, plate, display_name, push_params
                )
                processed_urls.append(processed_url)

            # 构建推送内容
            apprise_body = body

            # 使用PriorityMapper获取Apprise优先级
            priority = push_params.get("priority", PushPriority.NORMAL)
            apprise_priority = PriorityMapper.get_platform_priority(priority, "apprise")

            # 执行Apprise推送
            result = await apprise_pusher.send_notification(
                urls=processed_urls,  # 使用处理后的URLs
                title=title,
                body=apprise_body,
                priority=apprise_priority,
                body_format="text",
            )

            # 从Apprise结果中提取URL级别的统计
            total_count = result.get("valid_urls", 0) + result.get("invalid_urls", 0)
            
            # 计算实际成功的URL数量
            success_count = 0
            if result.get("url_results"):
                for url_result in result["url_results"]:
                    if url_result.get("success", False):
                        success_count += 1

            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "error": result.get("error"),
                "total_count": total_count,
                "success_count": success_count,
                "valid_urls": result.get("valid_urls", 0),
                "invalid_urls": result.get("invalid_urls", 0),
                "url_results": result.get("url_results", []),
            }

        except Exception as e:
            logging.error(f"Apprise推送失败: {e}")
            return {
                "success": False, 
                "error": str(e),
                "total_count": 0,
                "success_count": 0
            }

    async def _record_push_history(self, plate: str, results: Dict[str, Any]) -> None:
        """记录推送历史"""
        try:
            history_data = {
                "plate": plate,
                "timestamp": results["timestamp"],
                "title": results["title"],
                "priority": results["priority"],
                "success_count": results["success_count"],
                "total_count": results["total_count"],
                "errors": results["errors"],
            }

            await cache_service.record_push_history(plate, history_data)

        except Exception as e:
            logging.error(f"记录推送历史失败: {e}")

    async def test_notifications(self, plate_config: PlateConfig) -> Dict[str, Any]:
        """
        测试车牌推送配置

        Args:
            plate_config: 车牌配置

        Returns:
            测试结果
        """
        try:
            test_title = "推送测试"
            test_body = f"这是车牌 {plate_config.plate} 的推送测试消息"

            result = await self.push(
                plate_config=plate_config,
                title=test_title,
                body=test_body,
                priority=PushPriority.NORMAL,
            )

            return result

        except Exception as e:
            error_msg = f"推送测试失败: {e}"
            logging.error(error_msg)
            return {
                "plate": plate_config.plate,
                "success_count": 0,
                "total_count": 0,
                "errors": [error_msg],
                "timestamp": datetime.now().isoformat(),
            }

    async def validate_plate_config(self, plate_config: PlateConfig) -> Dict[str, Any]:
        """
        验证车牌推送配置

        Args:
            plate_config: 车牌配置

        Returns:
            验证结果
        """
        try:
            # 检查配置完整性
            errors = []

            if not plate_config.notifications:
                errors.append("未配置任何推送通道")

            for i, notification in enumerate(plate_config.notifications):
                if notification.type == "apprise":
                    if not notification.urls:
                        errors.append(f"Apprise配置 {i + 1}: 缺少URL配置")
                else:
                    errors.append(f"未知的推送类型: {notification.type}")

            # 执行测试推送
            test_result = await self.test_notifications(plate_config)

            return {
                "plate": plate_config.plate,
                "valid": len(errors) == 0 and test_result.get("success_count", 0) > 0,
                "errors": errors + test_result.get("errors", []),
                "test_result": test_result,
            }

        except Exception as e:
            error_msg = f"配置验证失败: {e}"
            logging.error(error_msg)
            return {"plate": plate_config.plate, "valid": False, "errors": [error_msg]}

    def get_status(self) -> Dict[str, Any]:
        """
        获取推送服务状态

        Returns:
            服务状态信息
        """
        try:
            # 获取Apprise支持的服务列表
            supported_services = []
            try:
                import apprise

                apobj = apprise.Apprise()
                supported_services = list(apobj.schemas())
            except Exception:
                pass

            return {
                "service_status": {
                    "apprise_enabled": self.apprise_enabled,
                    "supported_apprise_services": supported_services,
                },
                "configuration": {
                    "total_plates": 0,  # 需要从配置中获取
                    "apprise_channels": 0,  # 需要从配置中获取
                    "total_channels": 0,  # 需要从配置中获取
                },
            }

        except Exception as e:
            logging.error(f"获取服务状态失败: {e}")
            return {
                "service_status": {
                    "apprise_enabled": self.apprise_enabled,
                    "supported_apprise_services": [],
                },
                "configuration": {
                    "total_plates": 0,
                    "apprise_channels": 0,
                    "total_channels": 0,
                },
            }

    async def get_service_status(self) -> Dict[str, Any]:
        """
        获取推送服务状态（异步版本，供健康检查使用）

        Returns:
            服务状态信息
        """
        try:
            # 获取配置信息
            from config.config_v2 import config_manager
            app_config = config_manager.load_config()
            
            # 统计配置
            total_plates = len(app_config.plates)
            total_channels = 0
            apprise_channels = 0
            
            for plate in app_config.plates:
                for notification in plate.notifications:
                    if notification.type == "apprise":
                        apprise_channels += len(notification.urls)
                        total_channels += len(notification.urls)
                    else:
                        total_channels += 1
            
            # 获取Apprise支持的服务列表
            supported_services = []
            apprise_available = False
            try:
                import apprise
                apobj = apprise.Apprise()
                supported_services = list(apobj.schemas())
                apprise_available = True
            except Exception as e:
                logging.warning(f"Apprise不可用: {e}")
            
            # 测试Apprise推送器状态
            apprise_status = "unknown"
            try:
                if self.apprise_enabled and apprise_available:
                    apprise_status = "healthy"
                elif self.apprise_enabled and not apprise_available:
                    apprise_status = "error"
                else:
                    apprise_status = "disabled"
            except Exception:
                apprise_status = "error"
            
            return {
                "status": "healthy" if apprise_status == "healthy" else apprise_status,
                "channels_available": len(supported_services),
                "service_details": {
                    "apprise_enabled": self.apprise_enabled,
                    "apprise_available": apprise_available,
                    "apprise_status": apprise_status,
                    "supported_services_count": len(supported_services),
                },
                "configuration": {
                    "total_plates": total_plates,
                    "total_channels": total_channels,
                    "apprise_channels": apprise_channels,
                },
                "capabilities": {
                    "priorities": [p.value for p in PushPriority],
                    "notification_types": ["apprise"],
                }
            }

        except Exception as e:
            logging.error(f"获取推送服务状态失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "channels_available": 0,
                "service_details": {
                    "apprise_enabled": self.apprise_enabled,
                    "apprise_available": False,
                    "apprise_status": "error",
                },
                "configuration": {
                    "total_plates": 0,
                    "total_channels": 0,
                    "apprise_channels": 0,
                },
            }


# 全局统一推送实例
unified_pusher = UnifiedPusher()
