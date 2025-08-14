#!/usr/bin/env python3
"""
车牌工具函数

提供车牌前缀汉字转拼音功能，确保 Home Assistant 设备名称兼容性
"""

import re
from enum import Enum
from typing import Dict, Optional


class PlatePrefix(Enum):
    """车牌前缀汉字与拼音对照枚举
    
    包含全国各省市自治区的车牌前缀汉字及其拼音对应关系
    """
    
    # 直辖市
    京 = "beijing"  # 北京市
    津 = "tianjin"  # 天津市
    沪 = "shanghai" # 上海市
    渝 = "chongqing" # 重庆市
    
    # 省份
    冀 = "hebei"    # 河北省
    豫 = "henan"    # 河南省
    云 = "yunnan"   # 云南省
    辽 = "liaoning" # 辽宁省
    黑 = "heilongjiang" # 黑龙江省
    湘 = "hunan"    # 湖南省
    皖 = "anhui"    # 安徽省
    鲁 = "shandong" # 山东省
    新 = "xinjiang" # 新疆维吾尔自治区
    苏 = "jiangsu"  # 江苏省
    浙 = "zhejiang" # 浙江省
    赣 = "jiangxi"  # 江西省
    鄂 = "hubei"    # 湖北省
    桂 = "guangxi"  # 广西壮族自治区
    甘 = "gansu"    # 甘肃省
    晋 = "shanxi"   # 山西省
    蒙 = "neimenggu" # 内蒙古自治区
    陕 = "shaanxi"  # 陕西省
    吉 = "jilin"    # 吉林省
    闽 = "fujian"   # 福建省
    贵 = "guizhou"  # 贵州省
    粤 = "guangdong" # 广东省
    青 = "qinghai"  # 青海省
    藏 = "xizang"   # 西藏自治区
    川 = "sichuan"  # 四川省
    宁 = "ningxia"  # 宁夏回族自治区
    琼 = "hainan"   # 海南省
    
    # 特殊车牌
    港 = "gang"     # 香港特别行政区
    澳 = "ao"       # 澳门特别行政区
    台 = "tai"      # 台湾（特殊情况）
    
    # 军用车牌
    军 = "jun"      # 军用车牌
    警 = "jing"     # 警用车牌
    学 = "xue"      # 教练车牌
    
    def __str__(self) -> str:
        """返回拼音值"""
        return self.value
    
    @classmethod
    def get_pinyin(cls, chinese_char: str) -> Optional[str]:
        """获取汉字对应的拼音
        
        Args:
            chinese_char: 车牌前缀汉字
            
        Returns:
            对应的拼音，如果不存在则返回None
        """
        for prefix in cls:
            if prefix.name == chinese_char:
                return prefix.value
        return None
    
    @classmethod
    def get_all_mappings(cls) -> Dict[str, str]:
        """获取所有汉字到拼音的映射"""
        return {prefix.name: prefix.value for prefix in cls}


def convert_plate_to_pinyin(plate_number: str) -> str:
    """将车牌号中的汉字前缀转换为拼音
    
    Args:
        plate_number: 车牌号，如 "京A12345"
        
    Returns:
        转换后的车牌号，如 "jingA12345"
        
    Examples:
        >>> convert_plate_to_pinyin("京A12345")
        'jingA12345'
        >>> convert_plate_to_pinyin("津B15F93")
        'jinB15F93'
        >>> convert_plate_to_pinyin("ABC123")
        'ABC123'
    """
    if not plate_number:
        return plate_number
    
    # 提取第一个字符（车牌前缀）
    first_char = plate_number[0]
    
    # 获取对应的拼音
    pinyin = PlatePrefix.get_pinyin(first_char)
    
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
    normalized = re.sub(r'[^a-z0-9]', '', normalized)
    
    # 确保不以数字开头（如果以数字开头，添加前缀）
    if normalized and normalized[0].isdigit():
        normalized = f"plate_{normalized}"
    
    return normalized


def get_plate_display_name_for_ha(plate_number: str, display_name: Optional[str] = None) -> str:
    """获取适合 Home Assistant 显示的设备名称
    
    Args:
        plate_number: 车牌号
        display_name: 可选的显示名称
        
    Returns:
        适合 HA 显示的设备名称
        
    Examples:
        >>> get_plate_display_name_for_ha("京A12345")
        '京A12345'
        >>> get_plate_display_name_for_ha("津B15F93", "我的车")
        '我的车'
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
        return ('', '')
    
    first_char = plate_number[0]
    pinyin = PlatePrefix.get_pinyin(first_char)
    
    if pinyin:
        return (first_char, pinyin)
    else:
        return ('', '')


def validate_plate_number(plate_number: str) -> bool:
    """验证车牌号格式是否正确
    
    Args:
        plate_number: 车牌号
        
    Returns:
        是否为有效的车牌号格式
        
    Examples:
        >>> validate_plate_number("京A12345")
        True
        >>> validate_plate_number("津B15F93")
        True
        >>> validate_plate_number("ABC")
        False
    """
    if not plate_number or len(plate_number) < 6:
        return False
    
    # 检查是否以已知的车牌前缀开头
    first_char = plate_number[0]
    if PlatePrefix.get_pinyin(first_char) is None:
        # 如果不是汉字前缀，检查是否为字母（可能是特殊车牌）
        if not first_char.isalpha():
            return False
    
    # 基本格式检查：第二个字符应该是字母
    if len(plate_number) > 1 and not plate_number[1].isalpha():
        return False
    
    return True


# 常用的车牌前缀映射（用于快速查询）
COMMON_PLATE_PREFIXES = {
    "京": "beijing",  # 北京
    "津": "tianjin", # 天津  
    "沪": "shanghai", # 上海
    "渝": "chongqing", # 重庆
    "冀": "hebei",   # 河北
    "豫": "henan",   # 河南
    "云": "yunnan",  # 云南
    "辽": "liaoning", # 辽宁
    "黑": "heilongjiang", # 黑龙江
    "湘": "hunan",   # 湖南
    "皖": "anhui",   # 安徽
    "鲁": "shandong", # 山东
    "苏": "jiangsu", # 江苏
    "浙": "zhejiang", # 浙江
    "赣": "jiangxi",  # 江西
    "鄂": "hubei",   # 湖北
    "桂": "guangxi", # 广西
    "甘": "gansu",   # 甘肃
    "晋": "shanxi",  # 山西
    "蒙": "neimenggu", # 内蒙古
    "陕": "shaanxi", # 陕西
    "吉": "jilin",   # 吉林
    "闽": "fujian",  # 福建
    "贵": "guizhou", # 贵州
    "粤": "guangdong", # 广东
    "青": "qinghai", # 青海
    "藏": "xizang",  # 西藏
    "川": "sichuan", # 四川
    "宁": "ningxia", # 宁夏
    "琼": "hainan",  # 海南
}


if __name__ == "__main__":
    # 测试代码
    test_plates = ["京A12345", "津B15F93", "沪C99999", "粤B88888", "川A12345"]
    
    print("=== 车牌前缀转换测试 ===")
    for plate in test_plates:
        pinyin_plate = convert_plate_to_pinyin(plate)
        entity_id_part = normalize_plate_for_ha_entity_id(plate)
        province_info = extract_province_from_plate(plate)
        
        print(f"原始车牌: {plate}")
        print(f"拼音转换: {pinyin_plate}")
        print(f"HA实体ID: {entity_id_part}")
        print(f"省份信息: {province_info[0]} -> {province_info[1]}")
        print("-" * 40)