"""
Home Assistant设备模型

定义车牌设备的数据结构和属性
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

from service.jjz.jjz_status import JJZStatusEnum
from utils.plate_utils import (
    normalize_plate_for_ha_entity_id,
    get_plate_display_name_for_ha,
    extract_province_from_plate
)


class HAEntityType(Enum):
    """HA实体类型"""
    SENSOR = "sensor"


@dataclass
class HADeviceInfo:
    """Home Assistant设备信息"""
    
    # 设备标识
    identifiers: str         # 设备唯一标识符
    name: str               # 设备名称
    model: str              # 设备型号
    manufacturer: str       # 制造商
    sw_version: str         # 软件版本
    
    # 设备属性（车牌相关）
    plate_number: str       # 车牌号
    display_name: str       # 显示名称
    
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
    entity_id: str          # 实体ID
    entity_type: HAEntityType  # 实体类型
    state: Any              # 实体状态值
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


@dataclass 
class HAPlateDevice:
    """车牌设备模型 - 包含完整的车牌相关信息"""
    
    # 基础信息
    plate_number: str       # 车牌号
    display_name: str       # 显示名称
    
    # 进京证信息
    jjz_status: str = "unknown"           # 进京证状态 (valid/invalid/expired/pending/error)
    jjz_status_desc: str = "未知"        # 进京证状态描述（中文，如审核通过(生效中)）
    jjz_type: Optional[str] = None        # 进京证类型名称
    jjz_apply_time: Optional[str] = None  # 申请时间
    jjz_valid_start: Optional[str] = None # 有效期开始
    jjz_valid_end: Optional[str] = None   # 有效期结束
    jjz_days_remaining: Optional[int] = None  # 剩余天数
    jjz_remaining_count: Optional[str] = None  # 六环内进京证剩余次数
    
    # 限行信息
    traffic_limited_today: bool = False   # 当日是否限行
    traffic_rule_desc: str = "未知"       # 限行规则描述
    traffic_limited_tail_numbers: str = "0"  # 当日限行尾号
    
    # 数据元信息
    last_updated: datetime = None
    data_source: str = "api"             # 数据来源
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    def get_device_info(self, manufacturer: str = "JJZ Alert", model: str = "Beijing Vehicle") -> HADeviceInfo:
        """获取设备信息"""
        # 使用拼音转换后的车牌号作为设备标识符
        normalized_plate = normalize_plate_for_ha_entity_id(self.plate_number)
        return HADeviceInfo(
            identifiers=f"jjz_alert_{normalized_plate}",
            name=f"进京证监控 {self.display_name}",
            model=model,
            manufacturer=manufacturer,
            sw_version="2.0",
            plate_number=self.plate_number,
            display_name=self.display_name,
        )
    
    def get_combined_sensor_state(self, entity_prefix: str = "jjz_alert") -> HAEntityState:
        """获取合并的进京证和限行传感器状态"""
        # 提取省份信息和车牌剩余部分
        province_chinese, province_pinyin = extract_province_from_plate(self.plate_number)
        
        # 获取车牌号剩余部分（去掉省份前缀）
        plate_remainder = self.plate_number[1:] if len(self.plate_number) > 1 else ""
        
        # 构建实体ID：前缀_省份_车牌号剩余部分
        entity_id = f"sensor.{entity_prefix}_{province_pinyin}_{plate_remainder}"
        
        # 状态值：优先显示进京证状态，如果进京证有效则显示限行状态
        if self.jjz_status == JJZStatusEnum.VALID.value:
            # 进京证有效时，显示限行状态
            if self.traffic_limited_today:
                state = f"限行 ({self.traffic_limited_tail_numbers})"
            else:
                state = "正常通行"
        else:
            # 进京证无效时，显示进京证状态
            state = self.jjz_status_desc
        
        # 详细属性
        attributes = {
            "friendly_name": f"{self.display_name} 进京证与限行状态",
            "plate_number": self.plate_number,
            "display_name": self.display_name,
            "province": province_chinese,
            "province_pinyin": province_pinyin,
            
            # 进京证相关属性
            "jjz_status": self.jjz_status,
            "jjz_status_desc": self.jjz_status_desc,
            "jjz_type": self.jjz_type,
            "jjz_apply_time": self.jjz_apply_time,
            "jjz_valid_start": self.jjz_valid_start,
            "jjz_valid_end": self.jjz_valid_end,
            "jjz_days_remaining": self.jjz_days_remaining,
            "jjz_remaining_count": self.jjz_remaining_count,
            
            # 限行相关属性
            "traffic_limited_today": self.traffic_limited_today,
            "traffic_rule_desc": self.traffic_rule_desc,
            "traffic_limited_tail_numbers": self.traffic_limited_tail_numbers,
            
            # 元信息
            "data_source": self.data_source,
            "icon": self._get_icon(),
            "device_class": None,
        }
        
        return HAEntityState(
            entity_id=entity_id,
            entity_type=HAEntityType.SENSOR,
            state=state,
            attributes=attributes,
            last_updated=self.last_updated,
            device_info=self.get_device_info(),
        )
    
    def _get_icon(self) -> str:
        """根据状态获取图标"""
        if self.jjz_status != JJZStatusEnum.VALID.value:
            # 进京证无效
            return "mdi:alert-circle"
        elif self.traffic_limited_today:
            # 进京证有效但限行
            return "mdi:car-brake-alert"
        else:
            # 进京证有效且不限行
            return "mdi:car"
    
    def get_all_entity_states(self, entity_prefix: str = "jjz_alert") -> list[HAEntityState]:
        """获取该车牌的所有实体状态"""
        entities = []
        
        # 合并的进京证和限行传感器
        entities.append(self.get_combined_sensor_state(entity_prefix))
        
        return entities
    
    @classmethod
    def from_jjz_and_traffic_data(
        cls,
        plate_number: str,
        display_name: str,
        jjz_status_data: Dict[str, Any],
        traffic_status_data: Dict[str, Any],
    ) -> "HAPlateDevice":
        """从进京证和限行数据创建车牌设备"""
        
        # 使用 jjz_utils 格式化进京证类型和状态描述
        from utils.jjz_utils import extract_jjz_type_from_jjzzlmc, extract_status_from_blztmc
        
        jjzzlmc = jjz_status_data.get("jjzzlmc", "")
        blztmc = jjz_status_data.get("blztmc", "未知")
        status = jjz_status_data.get("status", "unknown")
        
        # 格式化进京证类型
        formatted_jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)
        
        # 格式化状态描述
        formatted_status_desc = extract_status_from_blztmc(blztmc, status)
        
        return cls(
            plate_number=plate_number,
            display_name=display_name or plate_number,
            
            # 进京证信息 - 使用格式化后的数据
            jjz_status=status,
            jjz_status_desc=formatted_status_desc,
            jjz_type=formatted_jjz_type,
            jjz_apply_time=jjz_status_data.get("apply_time"),
            jjz_valid_start=jjz_status_data.get("valid_start"),
            jjz_valid_end=jjz_status_data.get("valid_end"),
            jjz_days_remaining=jjz_status_data.get("days_remaining"),
            jjz_remaining_count=jjz_status_data.get("sycs"),
            
            # 限行信息
            traffic_limited_today=traffic_status_data.get("is_limited", False),
            traffic_rule_desc=traffic_status_data.get("rule", {}).get("limited_numbers", "未知"),
            traffic_limited_tail_numbers=traffic_status_data.get("rule", {}).get("limited_numbers", "0"),
            
            # 元信息
            last_updated=datetime.now(),
            data_source=jjz_status_data.get("data_source", "api"),
        )