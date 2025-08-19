"""
Home Assistant API客户端

提供与Home Assistant的REST API交互功能
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

import aiohttp

from config import HomeAssistantConfig
from .ha_device import HAPlateDevice, HAEntityState, HADeviceInfo


class HomeAssistantAPIError(Exception):
    """Home Assistant API错误"""
    pass


class HomeAssistantClient:
    """Home Assistant API客户端"""

    def __init__(self, config: HomeAssistantConfig):
        self.config = config
        self.base_url = config.url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {config.token}',
            'Content-Type': 'application/json',
        }
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            # 不在会话级别设置超时，而是在每个请求中单独设置
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                raise_for_status=False
            )
        return self._session

    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送HTTP请求"""
        # 正确处理endpoint路径 - 避免重复/api/前缀
        clean_endpoint = endpoint.lstrip('/')
        if clean_endpoint.startswith('api/'):
            clean_endpoint = clean_endpoint[4:]  # 移除api/前缀
        url = f"{self.base_url}/api/{clean_endpoint}"
        session = await self._get_session()

        timeout_value = timeout or self.config.timeout
        request_timeout = aiohttp.ClientTimeout(total=timeout_value)

        try:
            async with session.request(method, url, json=data, timeout=request_timeout) as response:
                response_text = await response.text()

                if response.status == 200 or response.status == 201:
                    try:
                        return await response.json()
                    except Exception:
                        return {"status": "success", "response": response_text}
                elif response.status == 404:
                    raise HomeAssistantAPIError(f"API endpoint not found: {endpoint}")
                elif response.status == 401:
                    raise HomeAssistantAPIError("Authentication failed. Check your token.")
                elif response.status == 403:
                    raise HomeAssistantAPIError("Access forbidden. Check your permissions.")
                else:
                    error_msg = f"API request failed: {response.status} - {response_text}"
                    raise HomeAssistantAPIError(error_msg)

        except asyncio.TimeoutError:
            raise HomeAssistantAPIError(f"Request timeout after {timeout_value}s")
        except aiohttp.ClientError as e:
            raise HomeAssistantAPIError(f"Network error: {e}")

    async def test_connection(self) -> Dict[str, Any]:
        """测试与Home Assistant的连接"""
        try:
            response = await self._make_request('GET', '/api/')
            return {
                'success': True,
                'message': response.get('message', 'API connected'),
                'version': response.get('version', 'unknown')
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    async def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取实体状态"""
        try:
            return await self._make_request('GET', f'/api/states/{entity_id}')
        except HomeAssistantAPIError as e:
            if "not found" in str(e).lower():
                return None
            raise

    async def set_entity_state(
            self,
            entity_id: str,
            state: str,
            attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """设置实体状态"""
        data = {
            'state': str(state),
            'attributes': attributes or {}
        }

        try:
            await self._make_request('POST', f'/api/states/{entity_id}', data)
            return True
        except Exception as e:
            logging.error(f"设置实体状态失败 {entity_id}: {e}")
            return False

    async def register_device(self, device_info: HADeviceInfo) -> bool:
        """注册设备到Home Assistant"""
        # Home Assistant会在首次接收到实体状态时自动创建设备
        # 这里我们通过设置一个临时实体来触发设备创建
        # entity_id 必须小写且只包含 a-z0-9_
        import re
        safe_identifiers = re.sub(r'[^a-z0-9_]', '_', str(device_info.identifiers).lower())
        temp_entity_id = f"sensor.{safe_identifiers}_device_info"

        device_data = device_info.to_dict()
        attributes = {
            'device_info': device_data,
            'friendly_name': f"{device_info.name} 设备信息",
            'icon': 'mdi:car',
        }

        try:
            success = await self.set_entity_state(
                temp_entity_id,
                'registered',
                attributes
            )

            if success:
                logging.info(f"设备注册成功: {device_info.name}")
            return success

        except Exception as e:
            logging.error(f"设备注册失败 {device_info.name}: {e}")
            return False

    async def sync_entity_state(self, entity_state: HAEntityState) -> bool:
        """同步实体状态到Home Assistant"""
        try:
            # 准备实体属性，包含设备信息
            attributes = entity_state.attributes.copy()

            # 添加设备信息到属性中，HA会根据这个信息自动创建或更新设备
            if entity_state.device_info:
                attributes['device'] = entity_state.device_info.to_dict()

            success = await self.set_entity_state(
                entity_state.entity_id,
                entity_state.state,
                attributes
            )

            if success:
                logging.debug(f"实体状态同步成功: {entity_state.entity_id} = {entity_state.state}")
            else:
                logging.warning(f"实体状态同步失败: {entity_state.entity_id}")

            return success

        except Exception as e:
            logging.error(f"同步实体状态异常 {entity_state.entity_id}: {e}")
            return False

    async def sync_plate_device(self, plate_device: HAPlateDevice) -> Dict[str, Any]:
        """同步整个车牌设备到Home Assistant"""
        sync_results = {
            'device_name': plate_device.display_name,
            'plate_number': plate_device.plate_number,
            'success_count': 0,
            'total_count': 0,
            'entity_results': [],
            'errors': []
        }

        try:
            # 首先注册设备
            device_info = plate_device.get_device_info(
                manufacturer=self.config.device_manufacturer,
                model=self.config.device_model
            )

            device_registered = await self.register_device(device_info)
            if not device_registered:
                sync_results['errors'].append('设备注册失败')

            # 获取所有实体状态
            entity_states = plate_device.get_all_entity_states(self.config.entity_prefix)
            sync_results['total_count'] = len(entity_states)

            # 并发同步所有实体
            sync_tasks = []
            for entity_state in entity_states:
                task = self.sync_entity_state(entity_state)
                sync_tasks.append(task)

            # 等待所有同步完成
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            # 统计结果
            for i, result in enumerate(results):
                entity_state = entity_states[i]
                entity_result = {
                    'entity_id': entity_state.entity_id,
                    'entity_type': entity_state.entity_type.value,
                    'success': False,
                    'error': None
                }

                if isinstance(result, Exception):
                    entity_result['error'] = str(result)
                    sync_results['errors'].append(f"{entity_state.entity_id}: {result}")
                elif result:
                    entity_result['success'] = True
                    sync_results['success_count'] += 1
                else:
                    entity_result['error'] = '同步失败'
                    sync_results['errors'].append(f"{entity_state.entity_id}: 同步失败")

                sync_results['entity_results'].append(entity_result)

            # 记录同步结果
            success_rate = (sync_results['success_count'] / sync_results['total_count'] * 100) if sync_results[
                                                                                                      'total_count'] > 0 else 0

            if sync_results['success_count'] == sync_results['total_count']:
                logging.info(
                    f"车牌设备 {plate_device.plate_number} 同步成功: {sync_results['success_count']}/{sync_results['total_count']} 实体")
            else:
                logging.warning(
                    f"车牌设备 {plate_device.plate_number} 部分同步失败: {sync_results['success_count']}/{sync_results['total_count']} 实体成功 ({success_rate:.1f}%)")

        except Exception as e:
            error_msg = f"同步车牌设备异常 {plate_device.plate_number}: {e}"
            logging.error(error_msg)
            sync_results['errors'].append(error_msg)

        return sync_results

    async def get_all_jjz_entities(self) -> List[Dict[str, Any]]:
        """获取所有JJZ相关的实体"""
        try:
            # 获取所有实体状态
            states = await self._make_request('GET', '/api/states')

            # 过滤JJZ相关实体
            jjz_entities = []
            prefix = self.config.entity_prefix

            for state in states:
                entity_id = state.get('entity_id', '')
                if entity_id.startswith(f'sensor.{prefix}_'):
                    jjz_entities.append(state)

            return jjz_entities

        except Exception as e:
            logging.error(f"获取JJZ实体列表失败: {e}")
            return []

    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体（通过删除其状态）"""
        try:
            await self._make_request('DELETE', f'/api/states/{entity_id}')
            logging.info(f"实体删除成功: {entity_id}")
            return True
        except Exception as e:
            logging.error(f"删除实体失败 {entity_id}: {e}")
            return False

    async def cleanup_stale_entities(self, current_plates: List[str]) -> Dict[str, Any]:
        """清理过期的实体（不在当前车牌列表中的）"""
        cleanup_results = {
            'deleted_count': 0,
            'total_found': 0,
            'errors': []
        }

        try:
            # 获取所有JJZ实体
            all_entities = await self.get_all_jjz_entities()
            cleanup_results['total_found'] = len(all_entities)

            # 提取当前车牌的实体前缀
            current_prefixes = set()
            prefix = self.config.entity_prefix
            for plate in current_plates:
                # 提取省份信息和车牌剩余部分
                from utils.plate_utils import extract_province_from_plate
                province_chinese, province_pinyin = extract_province_from_plate(plate)
                plate_remainder = plate[1:] if len(plate) > 1 else ""
                # 全部小写并清洗非法字符
                import re
                safe_prefix = re.sub(r'[^a-z0-9_]', '_', prefix.lower())
                safe_remainder = re.sub(r'[^a-z0-9_]', '_', plate_remainder.lower())
                current_prefixes.add(f'sensor.{safe_prefix}_{province_pinyin}_{safe_remainder}')

            # 找出需要删除的实体
            entities_to_delete = []
            for entity in all_entities:
                entity_id = entity.get('entity_id', '')

                # 检查是否属于当前车牌
                is_current = any(entity_id.startswith(prefix) for prefix in current_prefixes)
                if not is_current:
                    entities_to_delete.append(entity_id)

            # 删除过期实体
            if entities_to_delete:
                logging.info(f"发现 {len(entities_to_delete)} 个过期实体，开始清理...")

                delete_tasks = [self.delete_entity(entity_id) for entity_id in entities_to_delete]
                results = await asyncio.gather(*delete_tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    entity_id = entities_to_delete[i]
                    if isinstance(result, Exception):
                        cleanup_results['errors'].append(f"{entity_id}: {result}")
                    elif result:
                        cleanup_results['deleted_count'] += 1
                    else:
                        cleanup_results['errors'].append(f"{entity_id}: 删除失败")

            logging.info(f"实体清理完成: 删除 {cleanup_results['deleted_count']} 个过期实体")

        except Exception as e:
            error_msg = f"清理过期实体异常: {e}"
            logging.error(error_msg)
            cleanup_results['errors'].append(error_msg)

        return cleanup_results


# 全局HA客户端实例（延迟初始化）
_ha_client: Optional[HomeAssistantClient] = None


async def get_ha_client() -> Optional[HomeAssistantClient]:
    """获取HA客户端实例"""
    global _ha_client

    try:
        from config import get_homeassistant_config
        ha_config = get_homeassistant_config()

        if not ha_config.enabled:
            return None

        if _ha_client is None:
            _ha_client = HomeAssistantClient(ha_config)

        return _ha_client

    except Exception as e:
        logging.error(f"获取HA客户端失败: {e}")
        return None


async def close_ha_client():
    """关闭HA客户端"""
    global _ha_client
    if _ha_client:
        await _ha_client.close()
        _ha_client = None
