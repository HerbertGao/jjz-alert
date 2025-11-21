"""
JJZStatus 数据模型
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JJZStatus:
    """进京证状态数据模型"""

    plate: str
    status: str
    apply_time: Optional[str] = None
    valid_start: Optional[str] = None
    valid_end: Optional[str] = None
    days_remaining: Optional[int] = None
    sycs: Optional[str] = None
    jjzzlmc: Optional[str] = None
    blztmc: Optional[str] = None
    error_message: Optional[str] = None
    data_source: str = "api"
    cached_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        from jjz_alert.service.jjz.jjz_utils import (
            extract_jjz_type_from_jjzzlmc,
            extract_status_from_blztmc,
        )

        formatted_jjz_type = extract_jjz_type_from_jjzzlmc(self.jjzzlmc or "")
        formatted_status_desc = extract_status_from_blztmc(
            self.blztmc or "未知", self.status
        )

        return {
            "plate": self.plate,
            "status": self.status,
            "apply_time": self.apply_time,
            "valid_start": self.valid_start,
            "valid_end": self.valid_end,
            "days_remaining": self.days_remaining,
            "sycs": self.sycs,
            "jjzzlmc": self.jjzzlmc,
            "jjz_type_formatted": formatted_jjz_type,
            "blztmc": self.blztmc,
            "status_desc_formatted": formatted_status_desc,
            "error_message": self.error_message,
            "data_source": self.data_source,
            "cached_at": self.cached_at,
        }


__all__ = ["JJZStatus"]
