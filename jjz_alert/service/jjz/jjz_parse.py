import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar

from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum

logger = logging.getLogger(__name__)

TRecord = TypeVar("TRecord")
RecordBuilder = Callable[..., TRecord]
StatusResolver = Callable[[str, str, str, Optional[str]], str]


def parse_status(data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    解析进京证状态数据
    """
    if "data" not in data or "bzclxx" not in data["data"]:
        logger.warning("未找到 data.bzclxx 字段，原始返回: %s", data)
        return None

    all_status = []
    for car in data["data"]["bzclxx"]:
        plate = car.get("hphm", "未知车牌")
        bzxx_list = car.get("bzxx", [])
        for bz in bzxx_list:
            end_date = bz.get("yxqz")
            start_date = bz.get("yxqs")
            status = bz.get("blztmc", "未知状态")
            jjz_type = bz.get("jjzzlmc", "未知类型")
            try:
                if end_date:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    now_date = datetime.now().replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    days_left = (end_dt - now_date).days
                else:
                    days_left = "无"
            except Exception as e:
                logger.warning("日期解析错误 %s，异常：%s", end_date, e)
                days_left = "日期格式错误"

            all_status.append(
                {
                    "plate": plate,
                    "start_date": start_date,
                    "end_date": end_date,
                    "status": status,
                    "days_left": days_left,
                    "jjz_type": jjz_type,
                    "sycs": car.get("sycs", ""),
                }
            )
    return all_status


def _safe_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_single_jjz_record(
    plate: str,
    record: Dict[str, Any],
    vehicle: Dict[str, Any],
    record_type: str,
    status_resolver: StatusResolver,
    record_builder: RecordBuilder[TRecord],
) -> Optional[TRecord]:
    """
    解析单条进京证记录为业务对象
    """
    try:
        blzt = record.get("blzt", "")
        blztmc = record.get("blztmc", "")
        sqsj = record.get("sqsj", "")
        yxqs = record.get("yxqs", "")
        yxqz = record.get("yxqz", "")
        sxsyts = record.get("sxsyts", "")
        sycs = vehicle.get("sycs", "")
        jjzzlmc = record.get("jjzzlmc", "")

        status = status_resolver(blzt, blztmc, yxqz, yxqs)
        days_remaining = _safe_int(sxsyts)

        return record_builder(
            plate=plate,
            status=status,
            apply_time=sqsj,
            valid_start=yxqs,
            valid_end=yxqz,
            days_remaining=days_remaining,
            sycs=sycs,
            jjzzlmc=jjzzlmc,
            blztmc=blztmc,
            data_source="api",
        )
    except Exception as exc:
        logger.error(
            "解析单个进京证记录失败 plate=%s record_type=%s error=%s",
            plate,
            record_type,
            exc,
        )
        return None


def parse_all_jjz_records(
    response_data: Dict[str, Any],
    status_resolver: StatusResolver,
    record_builder: RecordBuilder[TRecord],
) -> List[TRecord]:
    """
    解析 API 响应中所有车辆的进京证记录
    """
    records: List[TRecord] = []

    if "error" in response_data:
        logger.warning("API响应包含错误: %s", response_data["error"])
        return records

    data = response_data.get("data", {})
    bzclxx = data.get("bzclxx", [])
    if not bzclxx:
        return records

    for vehicle in bzclxx:
        plate = vehicle.get("hphm", "")
        if not plate:
            continue

        for record in vehicle.get("bzxx", []):
            parsed = parse_single_jjz_record(
                plate, record, vehicle, "active", status_resolver, record_builder
            )
            if parsed:
                records.append(parsed)

        for record in vehicle.get("ecbzxx", []):
            parsed = parse_single_jjz_record(
                plate, record, vehicle, "pending", status_resolver, record_builder
            )
            if parsed:
                records.append(parsed)

    return records


def parse_jjz_response(
    plate: str,
    response_data: Dict[str, Any],
    status_resolver: StatusResolver,
    record_builder: RecordBuilder[TRecord],
) -> TRecord:
    """
    解析指定车牌的进京证响应
    """
    if "error" in response_data:
        return record_builder(
            plate=plate,
            status=JJZStatusEnum.ERROR.value,
            error_message=response_data["error"],
            data_source="api",
        )

    data = response_data.get("data", {})
    bzclxx = data.get("bzclxx", [])
    if not bzclxx:
        return record_builder(
            plate=plate,
            status=JJZStatusEnum.INVALID.value,
            error_message="未找到车辆信息",
            data_source="api",
        )

    target_vehicle = next(
        (vehicle for vehicle in bzclxx if vehicle.get("hphm") == plate), None
    )
    if not target_vehicle:
        return record_builder(
            plate=plate,
            status=JJZStatusEnum.INVALID.value,
            error_message="未找到匹配车牌的记录",
            data_source="api",
        )

    bzxx = target_vehicle.get("bzxx", [])
    if not bzxx:
        return record_builder(
            plate=plate,
            status=JJZStatusEnum.INVALID.value,
            error_message="未找到进京证记录",
            data_source="api",
        )

    latest_record = bzxx[0]
    blzt = latest_record.get("blzt", "")
    blztmc = latest_record.get("blztmc", "")
    sqsj = latest_record.get("sqsj", "")
    yxqs = latest_record.get("yxqs", "")
    yxqz = latest_record.get("yxqz", "")
    sxsyts = latest_record.get("sxsyts", "")
    sycs = target_vehicle.get("sycs", "")
    jjzzlmc = latest_record.get("jjzzlmc", "")

    status = status_resolver(blzt, blztmc, yxqz, yxqs)
    days_remaining = _safe_int(sxsyts)

    return record_builder(
        plate=plate,
        status=status,
        apply_time=sqsj,
        valid_start=yxqs,
        valid_end=yxqz,
        days_remaining=days_remaining,
        sycs=sycs,
        jjzzlmc=jjzzlmc,
        blztmc=blztmc,
        data_source="api",
    )


__all__ = [
    "parse_status",
    "parse_single_jjz_record",
    "parse_all_jjz_records",
    "parse_jjz_response",
]
