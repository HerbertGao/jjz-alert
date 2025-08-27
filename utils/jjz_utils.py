#!/usr/bin/env python3
"""
进京证相关工具函数
"""

from datetime import datetime


def format_valid_dates(start_str: str | None, end_str: str | None) -> tuple[str, str]:
    """
    将有效期起止日期格式化：同年仅显示 mm-dd，跨年显示 YYYY-mm-dd。

    Args:
        start_str: 开始日期，格式 YYYY-mm-dd
        end_str: 结束日期，格式 YYYY-mm-dd

    Returns:
        (formatted_start, formatted_end)
    """
    try:
        if not start_str or not end_str:
            return start_str or "", end_str or ""
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
        if start_dt.year == end_dt.year:
            return start_dt.strftime("%m-%d"), end_dt.strftime("%m-%d")
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    except Exception:
        return start_str or "", end_str or ""


def extract_jjz_type_from_jjzzlmc(jjzzlmc: str) -> str:
    """
    从进京证类型名称中提取括号内的内容

    Args:
        jjzzlmc: 进京证类型名称，如 "进京证（六环外）"

    Returns:
        提取的类型，如 "六环外"
    """
    if not jjzzlmc:
        return "未知"

    if "（" in jjzzlmc and "）" in jjzzlmc:
        start = jjzzlmc.find("（") + 1
        end = jjzzlmc.find("）")
        return jjzzlmc[start:end]
    elif "(" in jjzzlmc and ")" in jjzzlmc:
        start = jjzzlmc.find("(") + 1
        end = jjzzlmc.find(")")
        return jjzzlmc[start:end]
    else:
        return jjzzlmc


def extract_status_from_blztmc(blztmc: str, status: str) -> str:
    """
    从办理状态描述中提取状态文本

    Args:
        blztmc: 办理状态描述，如 "审核通过(生效中)"
        status: 状态码，如 "valid"

    Returns:
        提取的状态文本，如 "生效中"
    """
    if not blztmc:
        return "未知"

    # 如果是审核通过状态，尝试提取括号内的内容
    if "审核通过" in blztmc:
        if "（" in blztmc and "）" in blztmc:
            start = blztmc.find("（") + 1
            end = blztmc.find("）")
            return blztmc[start:end]
        elif "(" in blztmc and ")" in blztmc:
            start = blztmc.find("(") + 1
            end = blztmc.find(")")
            return blztmc[start:end]

    # 如果没有括号或不是审核通过状态，返回原始描述
    return blztmc


def format_jjz_push_content(
        display_name: str,
        jjzzlmc: str,
        blztmc: str,
        status: str,
        valid_start: str,
        valid_end: str,
        days_remaining: int,
        sycs: str,
) -> str:
    """
    格式化进京证推送内容（有效状态）

    Args:
        display_name: 显示名称
        jjzzlmc: 进京证类型名称
        blztmc: 办理状态描述
        status: 状态码
        valid_start: 有效期开始
        valid_end: 有效期结束
        days_remaining: 剩余天数
        sycs: 六环内剩余次数

    Returns:
        格式化的推送内容
    """
    # 导入模板管理器
    from utils.message_templates import template_manager
    
    # 提取进京证类型
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)

    # 提取状态文本
    status_text = extract_status_from_blztmc(blztmc, status)

    # 根据是否跨年决定日期显示格式
    disp_start, disp_end = format_valid_dates(valid_start, valid_end)

    # 使用模板管理器格式化内容
    return template_manager.format_valid_status(
        display_name=display_name,
        jjz_type=jjz_type,
        status_text=status_text,
        valid_start=disp_start,
        valid_end=disp_end,
        days_remaining=days_remaining,
        sycs=sycs,
    )


def format_jjz_expired_content(display_name: str, sycs: str) -> str:
    """
    格式化进京证过期推送内容

    Args:
        display_name: 显示名称
        sycs: 六环内剩余次数

    Returns:
        格式化的推送内容
    """
    # 导入模板管理器
    from utils.message_templates import template_manager
    
    # 使用模板管理器格式化内容
    return template_manager.format_expired_status(display_name, sycs)


def format_jjz_pending_content(display_name: str, jjzzlmc: str, apply_time: str) -> str:
    """
    格式化进京证审核中推送内容

    Args:
        display_name: 显示名称
        jjzzlmc: 进京证类型名称
        apply_time: 申请时间

    Returns:
        格式化的推送内容
    """
    # 导入模板管理器
    from utils.message_templates import template_manager
    
    # 提取进京证类型
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)
    
    # 使用模板管理器格式化内容
    return template_manager.format_pending_status(display_name, jjz_type, apply_time)


def format_jjz_error_content(
        display_name: str, jjzzlmc: str, status: str, error_msg: str
) -> str:
    """
    格式化进京证错误推送内容

    Args:
        display_name: 显示名称
        jjzzlmc: 进京证类型名称
        status: 状态码
        error_msg: 错误信息

    Returns:
        格式化的推送内容
    """
    # 导入模板管理器
    from utils.message_templates import template_manager
    
    # 提取进京证类型
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)
    
    # 使用模板管理器格式化内容
    return template_manager.format_error_status(display_name, jjz_type, status, error_msg)
