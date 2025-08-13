from __future__ import annotations

"""公共推送工具，供计划任务（main.py）和 REST API 复用。

主要功能：
1. 根据车牌分组进京证记录并选择需要推送的那一条；
2. 生成推送消息文本及级别；
3. 调用 bark 接口完成推送。
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

from config.config import get_admin_bark_configs, get_default_icon
from service.bark_pusher import BarkLevel, push_bark
from service.traffic_limiter import traffic_limiter
from utils.crypto import generate_md5

# ----------------------------- 通用工具 ----------------------------- #


def extract_device_key_from_server(server_url: str) -> str:
    """从Bark服务器URL中提取device_key
    
    Args:
        server_url
        
    Returns:
        device_key
    """
    # 移除末尾的斜杠
    url = server_url.rstrip('/')
    # 获取最后一个斜杠后的部分
    return url.split('/')[-1]


def generate_push_id(plate: str, device_key: str) -> str:
    """生成推送ID，为车牌号拼接device_key的MD5值
    
    Args:
        plate: 车牌号
        device_key: 设备密钥
        
    Returns:
        MD5哈希值
    """
    combined = f"{plate}{device_key}"
    return generate_md5(combined)


def format_status_display(status: str) -> str:
    """格式化状态显示

    如果状态包含 "审核通过"，只返回括号内内容；否则返回完整状态。
    """
    if "审核通过" in status and "(" in status and ")" in status:
        start = status.find("(") + 1
        end = status.find(")")
        if start > 0 and end > start:
            return status[start:end]
    return status


def group_by_plate(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按车牌号将记录分组"""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        grouped.setdefault(rec["plate"], []).append(rec)
    return grouped


def select_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从同一车牌的多条记录中选出最合适的一条

    1. 优先选择 "审核通过(生效中)"，若有多条则取 end_date 最大（剩余天数最长）；
    2. 若无生效中的，则取 end_date 最大的记录。
    """
    if not records:
        raise ValueError("records 不能为空")

    active = [r for r in records if r["status"] == "审核通过(生效中)"]
    target_list = active or records
    # 按 end_date 字符串倒序；若 end_date 为空字符串则排在后面
    return sorted(target_list, key=lambda x: (x.get("end_date") or ""), reverse=True)[0]


# ----------------------------- 推送核心 ----------------------------- #


def build_message(
    record: Dict[str, Any], target_date: date | None = None
) -> Tuple[str, BarkLevel]:
    """生成推送消息文本及级别"""
    plate: str = record["plate"]
    jjz_type_short = record["jjz_type"]
    if "（" in jjz_type_short and "）" in jjz_type_short:
        jjz_type_short = jjz_type_short.split("（")[1].split("）")[0]

        # 根据目标日期判断限行
    if target_date is None or target_date == date.today():
        # 今日
        is_limited = traffic_limiter.check_plate_limited(plate)
        limited_tag = "今日限行"
    elif target_date == date.today() + timedelta(days=1):
        # 明日
        is_limited = traffic_limiter.check_plate_limited_on(plate, target_date)
        limited_tag = "明日限行"
    else:
        is_limited = traffic_limiter.check_plate_limited_on(plate, target_date)
        limited_tag = target_date.strftime("%m-%d限行")

    plate_display = f"{plate} （{limited_tag}）" if is_limited else plate

    status_display = format_status_display(record["status"])

    if record["status"] == "审核通过(生效中)":
        msg = (
            f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}，"
            f"有效期 {record['start_date']} 至 {record['end_date']}，剩余 {record['days_left']} 天。"
        )
        level = BarkLevel.ACTIVE
    else:
        msg = (
            f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}。"
        )
        level = BarkLevel.CRITICAL
    return msg, level


def push_admin(title: str, body: str, level: BarkLevel = BarkLevel.CRITICAL):
    """向管理员 Bark 发送通知。若未配置管理员，则记录 warning。"""
    admin_configs = get_admin_bark_configs()
    if not admin_configs:
        logging.warning("未配置管理员 Bark，无法发送管理员通知: %s - %s", title, body)
        return []
    results = []
    for cfg in admin_configs:
        # 生成管理员推送ID（使用特殊标识）
        device_key = extract_device_key_from_server(cfg["bark_server"])
        admin_push_id = generate_push_id("ADMIN", device_key)
        
        res = push_bark(
            title,
            None,
            body,
            cfg["bark_server"],
            encrypt=cfg.get("bark_encrypt", False),
            encrypt_key=cfg.get("bark_encrypt_key"),
            encrypt_iv=cfg.get("bark_encrypt_iv"),
            encrypt_algorithm=cfg.get("bark_encrypt_algorithm"),
            encrypt_mode=cfg.get("bark_encrypt_mode"),
            encrypt_padding=cfg.get("bark_encrypt_padding"),
            level=level,
            push_id=admin_push_id,
        )
        results.append(res)
    return results


def push_plate(
    record: Dict[str, Any], plate_cfg: Dict[str, Any], target_date: date | None = None
) -> List[Any]:
    """向该车牌配置的所有 bark 服务推送消息，返回结果列表"""
    msg, level = build_message(record, target_date)
    results: List[Any] = []
    plate = record["plate"]
    
    for bark_cfg in plate_cfg["bark_configs"]:
        # 生成推送ID
        device_key = extract_device_key_from_server(bark_cfg["bark_server"])
        push_id = generate_push_id(plate, device_key)
        
        result = push_bark(
            "进京证状态",
            None,
            msg,
            bark_cfg["bark_server"],
            encrypt=bark_cfg.get("bark_encrypt", False),
            encrypt_key=bark_cfg.get("bark_encrypt_key"),
            encrypt_iv=bark_cfg.get("bark_encrypt_iv"),
            encrypt_algorithm=bark_cfg.get("bark_encrypt_algorithm"),
            encrypt_mode=bark_cfg.get("bark_encrypt_mode"),
            encrypt_padding=bark_cfg.get("bark_encrypt_padding"),
            level=level,
            icon=plate_cfg.get("plate_icon", get_default_icon()),
            push_id=push_id,
        )
        results.append(result)
    return results
