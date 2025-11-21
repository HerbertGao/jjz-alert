"""
车牌工具函数测试
"""

import pytest

from jjz_alert.base.plate_utils import (
    PlatePrefix,
    get_plate_pinyin,
    get_all_plate_mappings,
    convert_plate_to_pinyin,
    normalize_plate_for_ha_entity_id,
    get_plate_display_name_for_ha,
    extract_province_from_plate,
    validate_plate_number,
)


class TestPlatePrefix:
    """测试车牌前缀映射"""

    def test_common_provinces(self):
        """测试常见省份前缀"""
        assert get_plate_pinyin("京") == "beijing"
        assert get_plate_pinyin("沪") == "shanghai"
        assert get_plate_pinyin("粤") == "guangdong"
        assert get_plate_pinyin("川") == "sichuan"

    def test_special_prefixes(self):
        """测试特殊前缀"""
        assert get_plate_pinyin("军") == "jundui"
        assert get_plate_pinyin("警") == "jingcha"
        assert get_plate_pinyin("学") == "xue"

    def test_nonexistent_prefix(self):
        """测试不存在的前缀"""
        assert get_plate_pinyin("X") is None
        assert get_plate_pinyin("1") is None
        assert get_plate_pinyin("") is None

    def test_get_all_plate_mappings(self):
        """测试获取所有映射"""
        mappings = get_all_plate_mappings()
        assert isinstance(mappings, dict)
        assert "京" in mappings
        assert "沪" in mappings
        # 确保返回的是副本
        mappings["test"] = "test"
        assert "test" not in PlatePrefix


class TestConvertPlateToPinyin:
    """测试车牌转拼音"""

    def test_convert_with_chinese_prefix(self):
        """测试带汉字前缀的车牌"""
        assert convert_plate_to_pinyin("京A12345") == "beijingA12345"
        assert convert_plate_to_pinyin("沪B67890") == "shanghaiB67890"
        assert convert_plate_to_pinyin("粤C11111") == "guangdongC11111"

    def test_convert_without_chinese_prefix(self):
        """测试不带汉字前缀的车牌"""
        assert convert_plate_to_pinyin("ABC123") == "ABC123"
        assert convert_plate_to_pinyin("XYZ999") == "XYZ999"

    def test_convert_empty_string(self):
        """测试空字符串"""
        assert convert_plate_to_pinyin("") == ""

    def test_convert_single_char(self):
        """测试单字符"""
        assert convert_plate_to_pinyin("京") == "beijing"
        assert convert_plate_to_pinyin("A") == "A"


class TestNormalizePlateForHaEntityId:
    """测试车牌标准化为HA实体ID"""

    def test_normalize_with_chinese_prefix(self):
        """测试带汉字前缀的车牌标准化"""
        assert normalize_plate_for_ha_entity_id("京A12345") == "beijinga12345"
        assert normalize_plate_for_ha_entity_id("沪B15F93") == "shanghaib15f93"
        assert normalize_plate_for_ha_entity_id("粤C99999") == "guangdongc99999"

    def test_normalize_without_chinese_prefix(self):
        """测试不带汉字前缀的车牌标准化"""
        assert normalize_plate_for_ha_entity_id("ABC123") == "abc123"
        assert normalize_plate_for_ha_entity_id("XYZ999") == "xyz999"

    def test_normalize_starts_with_digit(self):
        """测试以数字开头的车牌（需要添加前缀）"""
        assert normalize_plate_for_ha_entity_id("12345") == "plate_12345"
        assert normalize_plate_for_ha_entity_id("999ABC") == "plate_999abc"

    def test_normalize_with_special_chars(self):
        """测试包含特殊字符的车牌"""
        assert normalize_plate_for_ha_entity_id("京A-12345") == "beijinga12345"
        assert normalize_plate_for_ha_entity_id("沪B_67890") == "shanghaib67890"
        assert normalize_plate_for_ha_entity_id("粤C.11111") == "guangdongc11111"

    def test_normalize_empty_string(self):
        """测试空字符串"""
        assert normalize_plate_for_ha_entity_id("") == ""

    def test_normalize_mixed_case(self):
        """测试混合大小写"""
        assert normalize_plate_for_ha_entity_id("京aBc123") == "beijingabc123"
        assert normalize_plate_for_ha_entity_id("AbC123") == "abc123"


class TestGetPlateDisplayNameForHa:
    """测试获取HA显示名称"""

    def test_with_custom_display_name(self):
        """测试使用自定义显示名称"""
        assert get_plate_display_name_for_ha("京A12345", "我的车") == "我的车"
        assert get_plate_display_name_for_ha("沪B67890", "测试车辆") == "测试车辆"

    def test_with_whitespace_display_name(self):
        """测试带空格的显示名称"""
        assert get_plate_display_name_for_ha("京A12345", "  我的车  ") == "我的车"
        assert get_plate_display_name_for_ha("京A12345", "  ") == "京A12345"

    def test_without_display_name(self):
        """测试没有显示名称时使用车牌号"""
        assert get_plate_display_name_for_ha("京A12345", None) == "京A12345"
        assert get_plate_display_name_for_ha("京A12345", "") == "京A12345"

    def test_with_empty_string_display_name(self):
        """测试空字符串显示名称"""
        assert get_plate_display_name_for_ha("京A12345", "") == "京A12345"


class TestExtractProvinceFromPlate:
    """测试提取省份信息"""

    def test_extract_valid_province(self):
        """测试提取有效省份"""
        assert extract_province_from_plate("京A12345") == ("京", "beijing")
        assert extract_province_from_plate("沪B67890") == ("沪", "shanghai")
        assert extract_province_from_plate("粤C11111") == ("粤", "guangdong")

    def test_extract_invalid_province(self):
        """测试提取无效省份"""
        assert extract_province_from_plate("ABC123") == ("", "")
        assert extract_province_from_plate("XYZ999") == ("", "")

    def test_extract_empty_string(self):
        """测试空字符串"""
        assert extract_province_from_plate("") == ("", "")

    def test_extract_single_char(self):
        """测试单字符"""
        assert extract_province_from_plate("京") == ("京", "beijing")
        assert extract_province_from_plate("X") == ("", "")


class TestValidatePlateNumber:
    """测试验证车牌号"""

    def test_validate_valid_plates(self):
        """测试有效车牌"""
        assert validate_plate_number("京A12345") is True
        assert validate_plate_number("沪B67890") is True
        assert validate_plate_number("粤C11111") is True
        assert validate_plate_number("川D22222") is True

    def test_validate_invalid_length(self):
        """测试长度无效的车牌"""
        assert validate_plate_number("京A123") is False  # 太短
        assert validate_plate_number("京A") is False  # 太短
        assert validate_plate_number("") is False  # 空字符串

    def test_validate_without_chinese_prefix(self):
        """测试不带汉字前缀的车牌（特殊车牌）"""
        assert validate_plate_number("ABC123") is True  # 字母开头
        assert validate_plate_number("XYZ999") is True  # 字母开头

    def test_validate_invalid_second_char(self):
        """测试第二个字符无效的车牌"""
        assert validate_plate_number("京112345") is False  # 第二个字符是数字
        assert validate_plate_number("京-12345") is False  # 第二个字符是特殊字符

    def test_validate_single_char(self):
        """测试单字符车牌"""
        assert validate_plate_number("京") is False  # 太短
        assert validate_plate_number("A") is False  # 太短

    def test_validate_with_special_chinese_prefix(self):
        """测试特殊汉字前缀"""
        assert validate_plate_number("军A12345") is True
        assert validate_plate_number("警B67890") is True
        assert validate_plate_number("学C11111") is True

    def test_validate_invalid_first_char(self):
        """测试第一个字符无效"""
        assert validate_plate_number("112345") is False  # 数字开头且不是汉字
        assert validate_plate_number("-12345") is False  # 特殊字符开头
