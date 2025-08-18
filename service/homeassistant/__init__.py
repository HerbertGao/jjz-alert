"""
Home Assistant集成服务模块

提供与Home Assistant的数据同步功能
每个车牌创建一个独立设备，包含完整的车辆状态信息
"""

from .ha_client import HomeAssistantClient, HomeAssistantAPIError, get_ha_client, close_ha_client
# 导入主要类和函数，方便外部使用
from .ha_device import HAPlateDevice, HADeviceInfo, HAEntityState, HAEntityType
from .ha_sync import HomeAssistantSyncService, ha_sync_service, sync_to_homeassistant

__all__ = [
    # 设备和实体模型
    'HAPlateDevice',
    'HADeviceInfo',
    'HAEntityState',
    'HAEntityType',

    # API客户端
    'HomeAssistantClient',
    'HomeAssistantAPIError',
    'get_ha_client',
    'close_ha_client',

    # 同步服务
    'HomeAssistantSyncService',
    'ha_sync_service',
    'sync_to_homeassistant',
]
