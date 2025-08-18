#!/usr/bin/env python3
"""
进京证相关工具函数
"""


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
    # 提取进京证类型
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)

    # 提取状态文本
    status_text = extract_status_from_blztmc(blztmc, status)

    # 构建内容
    content_parts = [
        f"车牌{display_name}的进京证({jjz_type})状态：{status_text}，有效期 {valid_start} 至 {valid_end}"
    ]

    if days_remaining is not None:
        content_parts.append(f"，剩余 {days_remaining} 天。")
    else:
        content_parts.append("。")

    # 添加六环内剩余次数信息
    if sycs:
        content_parts.append(f"六环内进京证剩余 {sycs} 次。")

    return "".join(content_parts)


def format_jjz_expired_content(display_name: str, sycs: str) -> str:
    """
    格式化进京证过期推送内容

    Args:
        display_name: 显示名称
        sycs: 六环内剩余次数

    Returns:
        格式化的推送内容
    """
    content_parts = [f"车牌 {display_name} 的进京证 已过期，请及时续办。"]

    # 添加六环内剩余次数信息
    if sycs:
        content_parts.append(f"六环内进京证剩余 {sycs} 次。")

    return "".join(content_parts)


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
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)
    return f"车牌{display_name}的进京证({jjz_type})状态：审核中，申请时间 {apply_time}。请关注审核进度。"


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
    jjz_type = extract_jjz_type_from_jjzzlmc(jjzzlmc)
    return f"车牌{display_name}的进京证({jjz_type})状态：{status}。{error_msg}"
