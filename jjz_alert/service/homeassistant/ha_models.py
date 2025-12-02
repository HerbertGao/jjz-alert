"""
Home Assistant 数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any


class HAEntityType(Enum):
    """HA实体类型"""

    SENSOR = "sensor"


@dataclass
class HADeviceInfo:
    """Home Assistant设备信息"""

    # 设备标识
    identifiers: str  # 设备唯一标识符
    name: str  # 设备名称
    model: str  # 设备型号
    manufacturer: str  # 制造商
    sw_version: str  # 软件版本

    # 设备属性（车牌相关）
    plate_number: str  # 车牌号
    display_name: str  # 显示名称

    def to_dict(self) -> Dict[str, Any]:
        """转换为HA设备注册格式"""
        return {
            "identifiers": [self.identifiers],
            "name": self.name,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "sw_version": self.sw_version,
            "configuration_url": None,  # 可以后续添加配置页面
        }


@dataclass
class HAEntityState:
    """Home Assistant实体状态"""

    # 实体基本信息
    entity_id: str  # 实体ID
    entity_type: HAEntityType  # 实体类型
    state: Any  # 实体状态值
    attributes: Dict[str, Any]  # 实体属性

    # 元数据
    last_updated: datetime
    device_info: HADeviceInfo

    def to_dict(self) -> Dict[str, Any]:
        """转换为HA状态格式"""
        return {
            "state": str(self.state),
            "attributes": self.attributes,
            "last_updated": self.last_updated.isoformat(),
        }
