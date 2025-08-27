"""
推送系统适配器

提供v1.x和v2.0推送系统的兼容性接口
"""

import logging
from typing import Dict, Any

from config import get_plates_v2
from service.notification.unified_pusher import unified_pusher


class NotificationAdapter:
    """推送通知适配器"""

    @staticmethod
    async def send_plate_notifications(
            plate: str,
            title: str,
            body: str,
            **kwargs
    ) -> Dict[str, Any]:
        """
        为指定车牌发送推送通知（v2.0接口）
        
        Args:
            plate: 车牌号
            title: 推送标题  
            body: 推送内容
            **kwargs: 额外参数
        
        Returns:
            推送结果
        """
        try:
            # 获取车牌配置
            plates = get_plates_v2()
            plate_config = None

            for p in plates:
                if p.plate == plate:
                    plate_config = p
                    break

            if not plate_config:
                error_msg = f"未找到车牌{plate}的推送配置"
                logging.warning(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'plate': plate
                }

            # 发送推送
            result = await unified_pusher.push(
                plate_config=plate_config,
                title=title,
                body=body,
                **kwargs
            )

            return result

        except Exception as e:
            error_msg = f"车牌{plate}推送失败: {e}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'plate': plate
            }

    @staticmethod
    async def send_all_notifications(
            title: str,
            body: str,
            **kwargs
    ) -> Dict[str, Any]:
        """
        向所有配置的车牌发送推送通知
        
        Args:
            title: 推送标题
            body: 推送内容
            **kwargs: 额外参数
        
        Returns:
            推送结果汇总
        """
        try:
            plates = get_plates_v2()

            if not plates:
                return {
                    'success': False,
                    'error': '未配置任何车牌',
                    'total_plates': 0,
                    'results': []
                }

            results = []
            success_count = 0

            # 为每个车牌发送推送
            for plate_config in plates:
                result = await unified_pusher.push(
                    plate_config=plate_config,
                    title=title,
                    body=body,
                    **kwargs
                )

                results.append(result)

                if result.get('success_count', 0) > 0:
                    success_count += 1

            return {
                'success': success_count > 0,
                'total_plates': len(plates),
                'success_plates': success_count,
                'results': results,
                'timestamp': results[0]['timestamp'] if results else None
            }

        except Exception as e:
            error_msg = f"批量推送失败: {e}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'total_plates': 0,
                'results': []
            }

    @staticmethod
    async def test_plate_notifications(plate: str) -> Dict[str, Any]:
        """
        测试指定车牌的推送配置
        
        Args:
            plate: 车牌号
        
        Returns:
            测试结果
        """
        try:
            plates = get_plates_v2()
            plate_config = None

            for p in plates:
                if p.plate == plate:
                    plate_config = p
                    break

            if not plate_config:
                return {
                    'success': False,
                    'error': f'未找到车牌{plate}的配置',
                    'plate': plate
                }

            # 执行测试
            result = await unified_pusher.test_notifications(plate_config)
            return result

        except Exception as e:
            error_msg = f"测试车牌{plate}推送配置失败: {e}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'plate': plate
            }

    @staticmethod
    async def validate_all_plate_configs() -> Dict[str, Any]:
        """
        验证所有车牌的推送配置
        
        Returns:
            验证结果汇总
        """
        try:
            plates = get_plates_v2()

            if not plates:
                return {
                    'valid': False,
                    'error': '未配置任何车牌',
                    'total_plates': 0,
                    'valid_plates': 0,
                    'results': []
                }

            results = []
            valid_count = 0

            for plate_config in plates:
                result = await unified_pusher.validate_plate_config(plate_config)
                results.append(result)

                if result.get('valid', False):
                    valid_count += 1

            return {
                'valid': valid_count == len(plates),
                'total_plates': len(plates),
                'valid_plates': valid_count,
                'invalid_plates': len(plates) - valid_count,
                'results': results
            }

        except Exception as e:
            error_msg = f"验证车牌配置失败: {e}"
            logging.error(error_msg)
            return {
                'valid': False,
                'error': error_msg,
                'total_plates': 0,
                'results': []
            }

    @staticmethod
    def get_notification_status() -> Dict[str, Any]:
        """
        获取推送服务状态
        
        Returns:
            服务状态信息
        """
        try:
            # 获取推送服务状态
            service_status = unified_pusher.get_status()

            # 获取配置的车牌数量
            plates = get_plates_v2()
            plate_count = len(plates)

            # 统计推送通道数量
            apprise_count = 0

            for plate in plates:
                for notification in plate.notifications:
                    if notification.type == 'apprise':
                        apprise_count += len(notification.urls)

            return {
                'service_status': service_status,
                'configuration': {
                    'total_plates': plate_count,
                    'apprise_channels': apprise_count,
                    'total_channels': apprise_count
                }
            }

        except Exception as e:
            logging.error(f"获取推送服务状态失败: {e}")
            return {
                'service_status': {'error': str(e)},
                'configuration': {
                    'total_plates': 0,
                    'apprise_channels': 0,
                    'total_channels': 0
                }
            }


# 全局适配器实例
notification_adapter = NotificationAdapter()
