"""把 JJZService 已经算出的进京证状态映射成对外查询字段。"""

import asyncio
import logging
from typing import Any, Dict, Optional

from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.jjz.jjz_utils import extract_jjz_type_from_jjzzlmc
from jjz_alert.service.traffic.traffic_models import PlateTrafficStatus

# 限行是补充字段。上游单次请求的套接字超时是 10 秒；这里只多留一点余量，
# 让一次能返回的查询完成。不跟随限行服务自己的多重重试（那会到大约 100 秒
# 才开始备用源）。超时后该字段为 null，进京证结果仍返回。其他调用方继续用
# 限行服务原有的重试。
PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS = 12

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


def _remaining_count(value: Any) -> Optional[int]:
    """六环内剩余次数。空白或不能按整数解析时对外为 null。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def traffic_limited_today_value(
    status: Optional[PlateTrafficStatus],
) -> Optional[bool]:
    """限行服务给出确定结论时返回布尔值，否则返回 None。

    查询失败时 ``PlateTrafficStatus.is_limited`` 仍是 False，同时带有
    ``error_message`` 且没有规则。这个占位 False 不能当成“今日不限行”。
    """
    if status is None:
        return None
    if (status.error_message or "").strip():
        return None
    if status.rule is None:
        return None
    return bool(status.is_limited)


async def lookup_traffic_limited_today(plate: str) -> Optional[bool]:
    """复用限行服务判断该车牌当日是否限行。查不准或超过等待时限时返回 None。

    等待只包住这一次补充查询，不修改限行服务的重试次数。
    """
    from jjz_alert.service.traffic.traffic_service import traffic_service

    try:
        status = await asyncio.wait_for(
            traffic_service.check_plate_limited(plate),
            timeout=PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logging.warning("限行查询超过等待时限")
        return None
    except Exception as exc:
        logging.warning("限行查询失败: %s", type(exc).__name__)
        return None
    return traffic_limited_today_value(status)


def to_permit_payload(
    status: JJZStatus,
    plate: str,
    *,
    traffic_limited_today: Optional[bool] = None,
) -> Dict[str, Any]:
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
        "remaining_count": _remaining_count(status.sycs),
        "reject_reason": _blank_to_none(status.reject_reason),
        "traffic_limited_today": traffic_limited_today,
    }
