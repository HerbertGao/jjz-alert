"""
Home Assistant同步服务

负责将进京证和限行数据同步到Home Assistant
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import get_homeassistant_config, get_plates_v2
from service.jjz.jjz_service import JJZStatus
from service.traffic.traffic_service import PlateTrafficStatus
from .ha_client import HomeAssistantClient, get_ha_client, HomeAssistantAPIError
from .ha_device import HAPlateDevice


class HomeAssistantSyncService:
    """Home Assistant同步服务"""

    def __init__(self):
        self.config = get_homeassistant_config()
        self._client: Optional[HomeAssistantClient] = None
        self._last_sync_time: Optional[datetime] = None

    async def _get_client(self) -> Optional[HomeAssistantClient]:
        """获取HA客户端"""
        if not self.config.enabled:
            return None
            
        if self._client is None:
            self._client = await get_ha_client()
            
        return self._client

    async def test_connection(self) -> Dict[str, Any]:
        """测试Home Assistant连接"""
        try:
            if not self.config.enabled:
                return {
                    'success': False,
                    'error': 'Home Assistant集成未启用'
                }

            client = await self._get_client()
            if not client:
                return {
                    'success': False,
                    'error': '无法创建HA客户端'
                }

            result = await client.test_connection()
            
            if result['success']:
                logging.info(f"Home Assistant连接测试成功: {result.get('version', 'unknown')}")
            else:
                logging.error(f"Home Assistant连接测试失败: {result.get('error', 'unknown')}")
                
            return result

        except Exception as e:
            error_msg = f"Home Assistant连接测试异常: {e}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    async def sync_plate_data(
        self,
        plate_number: str,
        display_name: str,
        jjz_status: JJZStatus,
        traffic_status: PlateTrafficStatus
    ) -> Dict[str, Any]:
        """同步单个车牌数据到Home Assistant"""
        
        sync_result = {
            'plate_number': plate_number,
            'display_name': display_name,
            'success': False,
            'error': None,
            'entity_count': 0,
            'sync_time': datetime.now().isoformat()
        }

        try:
            if not self.config.enabled:
                sync_result['error'] = 'Home Assistant集成未启用'
                return sync_result

            client = await self._get_client()
            if not client:
                sync_result['error'] = '无法获取HA客户端'
                return sync_result

            # 创建车牌设备数据
            plate_device = HAPlateDevice.from_jjz_and_traffic_data(
                plate_number=plate_number,
                display_name=display_name,
                jjz_status_data=jjz_status.to_dict(),
                traffic_status_data=traffic_status.to_dict()
            )

            # 执行同步（带重试机制）
            for attempt in range(self.config.retry_count):
                try:
                    result = await client.sync_plate_device(plate_device)
                    
                    # 更新同步结果
                    sync_result.update({
                        'success': result['success_count'] > 0,
                        'entity_count': result['total_count'],
                        'success_entities': result['success_count'],
                        'failed_entities': result['total_count'] - result['success_count'],
                        'entity_results': result['entity_results'],
                        'attempt': attempt + 1
                    })
                    
                    if result['errors']:
                        sync_result['error'] = '; '.join(result['errors'][:3])  # 只显示前3个错误
                    
                    # 如果成功或者是最后一次尝试，跳出重试循环
                    if result['success_count'] > 0 or attempt == self.config.retry_count - 1:
                        break
                        
                    # 重试前等待
                    if attempt < self.config.retry_count - 1:
                        await asyncio.sleep(2)
                        
                except HomeAssistantAPIError as e:
                    if "Authentication failed" in str(e) or "Access forbidden" in str(e):
                        # 认证错误不重试
                        sync_result['error'] = str(e)
                        break
                    elif attempt == self.config.retry_count - 1:
                        # 最后一次尝试
                        sync_result['error'] = str(e)
                    else:
                        # 继续重试
                        logging.warning(f"车牌 {plate_number} HA同步失败，尝试 {attempt + 1}/{self.config.retry_count}: {e}")
                        await asyncio.sleep(2)

            # 记录同步结果
            if sync_result['success']:
                logging.info(f"车牌 {plate_number} HA同步成功: {sync_result['success_entities']}/{sync_result['entity_count']} 实体")
            else:
                logging.error(f"车牌 {plate_number} HA同步失败: {sync_result.get('error', 'unknown')}")

        except Exception as e:
            error_msg = f"同步车牌数据异常 {plate_number}: {e}"
            logging.error(error_msg)
            sync_result['error'] = error_msg

        return sync_result

    async def sync_multiple_plates(
        self,
        plates_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量同步多个车牌数据"""
        
        batch_result = {
            'total_plates': len(plates_data),
            'success_plates': 0,
            'failed_plates': 0,
            'plate_results': [],
            'start_time': datetime.now().isoformat(),
            'errors': []
        }

        try:
            if not self.config.enabled:
                batch_result['errors'].append('Home Assistant集成未启用')
                return batch_result

            if not plates_data:
                batch_result['errors'].append('没有车牌数据需要同步')
                return batch_result

            # 并发同步所有车牌（限制并发数）
            semaphore = asyncio.Semaphore(3)  # 最多3个并发

            async def sync_single_plate(plate_data):
                async with semaphore:
                    return await self.sync_plate_data(
                        plate_data['plate_number'],
                        plate_data['display_name'],
                        plate_data['jjz_status'],
                        plate_data['traffic_status']
                    )

            # 执行并发同步
            sync_tasks = [sync_single_plate(plate_data) for plate_data in plates_data]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            # 统计结果
            for i, result in enumerate(results):
                plate_data = plates_data[i]
                
                if isinstance(result, Exception):
                    error_msg = f"车牌 {plate_data['plate_number']} 同步异常: {result}"
                    batch_result['errors'].append(error_msg)
                    batch_result['failed_plates'] += 1
                    batch_result['plate_results'].append({
                        'plate_number': plate_data['plate_number'],
                        'success': False,
                        'error': str(result)
                    })
                else:
                    batch_result['plate_results'].append(result)
                    if result['success']:
                        batch_result['success_plates'] += 1
                    else:
                        batch_result['failed_plates'] += 1

            # 记录批量同步结果
            success_rate = (batch_result['success_plates'] / batch_result['total_plates'] * 100) if batch_result['total_plates'] > 0 else 0
            
            batch_result['end_time'] = datetime.now().isoformat()
            batch_result['success_rate'] = round(success_rate, 1)

            logging.info(f"HA批量同步完成: {batch_result['success_plates']}/{batch_result['total_plates']} 车牌成功 ({success_rate:.1f}%)")

        except Exception as e:
            error_msg = f"批量同步异常: {e}"
            logging.error(error_msg)
            batch_result['errors'].append(error_msg)

        return batch_result

    async def sync_from_query_results(
        self,
        jjz_results: Dict[str, JJZStatus],
        traffic_results: Dict[str, PlateTrafficStatus]
    ) -> Dict[str, Any]:
        """从查询结果同步数据"""
        
        # 获取配置的车牌信息
        plates_config = get_plates_v2()
        plate_info_map = {plate.plate: plate for plate in plates_config}

        # 准备同步数据
        plates_data = []
        for plate_number in jjz_results.keys():
            if plate_number not in traffic_results:
                continue
                
            plate_config = plate_info_map.get(plate_number)
            display_name = plate_config.display_name if plate_config else plate_number

            plates_data.append({
                'plate_number': plate_number,
                'display_name': display_name,
                'jjz_status': jjz_results[plate_number],
                'traffic_status': traffic_results[plate_number]
            })

        if not plates_data:
            return {
                'total_plates': 0,
                'success_plates': 0,
                'failed_plates': 0,
                'errors': ['没有有效的查询结果需要同步']
            }

        # 执行批量同步
        result = await self.sync_multiple_plates(plates_data)
        
        # 更新最后同步时间
        if result['success_plates'] > 0:
            self._last_sync_time = datetime.now()
            
        return result

    async def cleanup_stale_entities(self) -> Dict[str, Any]:
        """清理过期的实体"""
        try:
            if not self.config.enabled:
                return {
                    'success': False,
                    'error': 'Home Assistant集成未启用'
                }

            client = await self._get_client()
            if not client:
                return {
                    'success': False,
                    'error': '无法获取HA客户端'
                }

            # 获取当前配置的车牌列表
            plates_config = get_plates_v2()
            current_plates = [plate.plate for plate in plates_config]

            # 执行清理
            result = await client.cleanup_stale_entities(current_plates)
            
            logging.info(f"HA实体清理完成: 删除 {result['deleted_count']} 个过期实体")
            
            return {
                'success': True,
                'deleted_count': result['deleted_count'],
                'total_found': result['total_found'],
                'errors': result['errors']
            }

        except Exception as e:
            error_msg = f"清理过期实体异常: {e}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    async def get_sync_status(self) -> Dict[str, Any]:
        """获取同步服务状态"""
        try:
            status = {
                'enabled': self.config.enabled,
                'last_sync_time': self._last_sync_time.isoformat() if self._last_sync_time else None,
                'config': {
                    'url': self.config.url,
                    'entity_prefix': self.config.entity_prefix,
                    'sync_after_query': self.config.sync_after_query,
                    'create_device_per_plate': self.config.create_device_per_plate,
                    'retry_count': self.config.retry_count,
                    'timeout': self.config.timeout,
                },
                'connection_status': None
            }

            # 测试连接状态
            if self.config.enabled:
                connection_result = await self.test_connection()
                status['connection_status'] = connection_result

            return status

        except Exception as e:
            logging.error(f"获取HA同步状态失败: {e}")
            return {
                'enabled': False,
                'error': str(e)
            }

    async def close(self):
        """关闭同步服务"""
        if self._client:
            await self._client.close()
            self._client = None


# 全局HA同步服务实例
ha_sync_service = HomeAssistantSyncService()


async def sync_to_homeassistant(
    jjz_results: Dict[str, JJZStatus],
    traffic_results: Dict[str, PlateTrafficStatus]
) -> Optional[Dict[str, Any]]:
    """便捷函数：同步查询结果到Home Assistant"""
    try:
        config = get_homeassistant_config()
        if not config.enabled or not config.sync_after_query:
            return None
            
        return await ha_sync_service.sync_from_query_results(jjz_results, traffic_results)
        
    except Exception as e:
        logging.error(f"同步到Home Assistant失败: {e}")
        return None


async def get_ha_service_status() -> Dict[str, Any]:
    """获取Home Assistant服务状态（供健康检查使用）"""
    try:
        config = get_homeassistant_config()
        
        if not config.enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "Home Assistant集成未启用"
            }
        
        # 获取详细状态
        sync_status = await ha_sync_service.get_sync_status()
        
        # 判断总体状态
        if sync_status.get('connection_status', {}).get('success', False):
            status = "healthy"
        elif sync_status.get('enabled', False):
            status = "error"
        else:
            status = "disabled"
        
        return {
            "status": status,
            "enabled": sync_status.get('enabled', False),
            "url": config.url,
            "last_sync": sync_status.get('last_sync_time'),
            "connection": sync_status.get('connection_status', {}).get('success', False),
            "sync_after_query": config.sync_after_query,
            "entity_prefix": config.entity_prefix
        }
        
    except Exception as e:
        logging.error(f"获取HA服务状态失败: {e}")
        return {
            "status": "error",
            "enabled": False,
            "error": str(e)
        }