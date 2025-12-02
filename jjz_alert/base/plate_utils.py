#!/usr/bin/env python3
"""
车牌工具函数

提供车牌前缀汉字转拼音功能，确保 Home Assistant 设备名称兼容性
"""

import re
from typing import Dict, Optional

PlatePrefix = {
    "京": "beijing",
    "津": "tianjin",
    "沪": "shanghai",
    "渝": "chongqing",
    "冀": "hebei",
    "豫": "henan",
    "云": "yunnan",
    "辽": "liaoning",
    "黑": "heilongjiang",
    "湘": "hunan",
    "皖": "anhui",
    "鲁": "shandong",
    "新": "xinjiang",
    "苏": "jiangsu",
    "浙": "zhejiang",
    "赣": "jiangxi",
    "鄂": "hubei",
    "桂": "guangxi",
    "甘": "gansu",
    "晋": "shanxi",
    "蒙": "neimenggu",
    "陕": "shaanxi",
    "吉": "jilin",
    "闽": "fujian",
    "贵": "guizhou",
    "粤": "guangdong",
    "青": "qinghai",
    "藏": "xizang",
    "川": "sichuan",
    "宁": "ningxia",
    "琼": "hainan",
    "港": "xianggang",
    "澳": "aomen",
    "台": "taiwan",
    "军": "jundui",
    "警": "jingcha",
    "学": "xue",
}


def get_plate_pinyin(chinese_char: str) -> Optional[str]:
    return PlatePrefix.get(chinese_char)


def get_all_plate_mappings() -> Dict[str, str]:
    return PlatePrefix.copy()


def convert_plate_to_pinyin(plate_number: str) -> str:
    """将车牌号中的汉字前缀转换为拼音

    Args:
        plate_number: 车牌号，如 "京A12345"

    Returns:
        转换后的车牌号，如 "jingA12345"
    """
    if not plate_number:
        return plate_number

    # 提取第一个字符（车牌前缀）
    first_char = plate_number[0]

    # 获取对应的拼音
    pinyin = get_plate_pinyin(first_char)

    if pinyin:
        # 替换汉字前缀为拼音
        return pinyin + plate_number[1:]
    else:
        # 如果不是汉字前缀（如测试车牌或特殊情况），直接返回
        return plate_number


def normalize_plate_for_ha_entity_id(plate_number: str) -> str:
    """将车牌号标准化为适合 Home Assistant 实体ID的格式

    Home Assistant 实体ID要求：
    - 只能包含小写字母、数字和下划线
    - 不能以数字开头
    - 长度限制

    Args:
        plate_number: 原始车牌号

    Returns:
        标准化后的实体ID部分

    Examples:
        >>> normalize_plate_for_ha_entity_id("京A12345")
        'jinga12345'
        >>> normalize_plate_for_ha_entity_id("津B15F93")
        'jinb15f93'
    """
    # 转换汉字为拼音
    pinyin_plate = convert_plate_to_pinyin(plate_number)

    # 转换为小写
    normalized = pinyin_plate.lower()

    # 移除或替换不合法字符（保留字母数字）
    normalized = re.sub(r"[^a-z0-9]", "", normalized)

    # 确保不以数字开头（如果以数字开头，添加前缀）
    if normalized and normalized[0].isdigit():
        normalized = f"plate_{normalized}"

    return normalized


def get_plate_display_name_for_ha(
    plate_number: str, display_name: Optional[str] = None
) -> str:
    """获取适合 Home Assistant 显示的设备名称

    Args:
        plate_number: 车牌号
        display_name: 可选的显示名称

    Returns:
        适合 HA 显示的设备名称
    """
    # 如果有自定义显示名称，优先使用
    if display_name and display_name.strip():
        return display_name.strip()

    # 否则使用原始车牌号（保留汉字用于显示）
    return plate_number


def extract_province_from_plate(plate_number: str) -> tuple[str, str]:
    """从车牌号提取省份信息

    Args:
        plate_number: 车牌号

    Returns:
        (省份汉字, 省份拼音) 的元组

    Examples:
        >>> extract_province_from_plate("京A12345")
        ('京', 'jing')
        >>> extract_province_from_plate("ABC123")
        ('', '')
    """
    if not plate_number:
        return ("", "")

    first_char = plate_number[0]
    pinyin = get_plate_pinyin(first_char)

    if pinyin:
        return (first_char, pinyin)
    else:
        return ("", "")


def validate_plate_number(plate_number: str) -> bool:
    """验证车牌号格式是否正确

    Args:
        plate_number: 车牌号

    Returns:
        是否为有效的车牌号格式
    """
    if not plate_number or len(plate_number) < 6:
        return False

    # 检查是否以已知的车牌前缀开头
    first_char = plate_number[0]
    if get_plate_pinyin(first_char) is None:
        # 如果不是汉字前缀，检查是否为字母（可能是特殊车牌）
        if not first_char.isalpha():
            return False

    # 基本格式检查：第二个字符应该是字母
    if len(plate_number) > 1 and not plate_number[1].isalpha():
        return False

    return True
