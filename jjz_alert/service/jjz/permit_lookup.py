"""把 JJZService 已经算出的进京证状态映射成对外查询字段。"""

from typing import Any, Dict, Optional

from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.jjz.jjz_utils import extract_jjz_type_from_jjzzlmc

# 这些文案来自现有查询：车牌在账户返回里没有任何进京证记录。
MISSING_PERMIT_MESSAGES = frozenset(
    {
        "未找到匹配车牌的记录",
        "未找到车辆信息",
        "未找到进京证记录",
    }
)


def is_permit_missing(status: Optional[JJZStatus]) -> bool:
    """范围内的车牌没有进京证记录。查询失败不算缺失。

    必须同时是 invalid。上游失败时状态是 error，即使文案碰巧相同也不能当成 404。
    """
    if status is None:
        return False
    if (status.status or "").strip() != JJZStatusEnum.INVALID.value:
        return False
    message = (status.error_message or "").strip()
    return message in MISSING_PERMIT_MESSAGES


def is_permit_lookup_error(status: Optional[JJZStatus]) -> bool:
    """上游查询失败，或服务没有返回状态对象。"""
    if status is None:
        return True
    return (status.status or "").strip() == JJZStatusEnum.ERROR.value


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _permit_type_fields(jjzzlmc: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """进京证类型用现有的括号内简称，中文名称用 jjzzlmc。"""
    type_name = _blank_to_none(jjzzlmc)
    if not type_name:
        return None, None
    extracted = extract_jjz_type_from_jjzzlmc(type_name).strip()
    return (extracted or None), type_name


def _status_name(status: JJZStatus, status_code: str) -> str:
    name = (status.blztmc or "").strip()
    if name:
        return name
    return JJZStatusEnum.from_string(status_code).description


def _days_remaining(value: Any) -> Optional[int]:
    # bool 是 int 的子类，不能当成剩余天数。
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def to_permit_payload(status: JJZStatus, plate: str) -> Dict[str, Any]:
    """映射为查询接口的响应字段。只保留该车牌的进京证状态，不带账户或其它车牌。"""
    permit_type, type_name = _permit_type_fields(status.jjzzlmc)
    status_code = (status.status or "").strip() or JJZStatusEnum.UNKNOWN.value
    return {
        "plate": plate,
        "type": permit_type,
        "type_name": type_name,
        "status": status_code,
        "status_name": _status_name(status, status_code),
        "valid_from": _blank_to_none(status.valid_start),
        "valid_until": _blank_to_none(status.valid_end),
        "days_remaining": _days_remaining(status.days_remaining),
    }
