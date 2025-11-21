"""
限行服务数据模型
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, Optional


@dataclass
class TrafficRule:
    """限行规则数据模型"""

    date: date
    limited_numbers: str  # 如 "1和6", "不限行"
    limited_time: str  # 原始时间字符串
    is_limited: bool
    description: Optional[str] = None
    data_source: str = "api"  # api, cache
    cached_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "date": self.date.isoformat(),
            "limited_numbers": self.limited_numbers,
            "limited_time": self.limited_time,
            "is_limited": self.is_limited,
            "description": self.description,
            "data_source": self.data_source,
            "cached_at": self.cached_at,
        }


@dataclass
class PlateTrafficStatus:
    """车牌限行状态数据模型"""

    plate: str
    date: date
    is_limited: bool
    tail_number: str
    rule: Optional[TrafficRule] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "plate": self.plate,
            "date": self.date.isoformat(),
            "is_limited": self.is_limited,
            "tail_number": self.tail_number,
            "rule": self.rule.to_dict() if self.rule else None,
            "error_message": self.error_message,
        }
