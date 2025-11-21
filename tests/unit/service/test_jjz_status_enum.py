"""
JJZStatusEnum 单元测试
"""

import pytest

from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


@pytest.mark.unit
class TestJJZStatusEnum:
    """JJZStatusEnum测试类"""

    def test_str_method(self):
        """测试 __str__ 方法"""
        assert str(JJZStatusEnum.VALID) == "valid"
        assert str(JJZStatusEnum.EXPIRED) == "expired"
        assert str(JJZStatusEnum.PENDING) == "pending"
        assert str(JJZStatusEnum.INVALID) == "invalid"
        assert str(JJZStatusEnum.ERROR) == "error"
        assert str(JJZStatusEnum.UNKNOWN) == "unknown"

    def test_from_string_empty(self):
        """测试 from_string - 空字符串"""
        assert JJZStatusEnum.from_string("") == JJZStatusEnum.UNKNOWN
        assert JJZStatusEnum.from_string(None) == JJZStatusEnum.UNKNOWN

    def test_from_string_direct_match(self):
        """测试 from_string - 直接匹配枚举值"""
        assert JJZStatusEnum.from_string("valid") == JJZStatusEnum.VALID
        assert JJZStatusEnum.from_string("VALID") == JJZStatusEnum.VALID
        assert JJZStatusEnum.from_string("  valid  ") == JJZStatusEnum.VALID
        assert JJZStatusEnum.from_string("expired") == JJZStatusEnum.EXPIRED
        assert JJZStatusEnum.from_string("pending") == JJZStatusEnum.PENDING
        assert JJZStatusEnum.from_string("invalid") == JJZStatusEnum.INVALID
        assert JJZStatusEnum.from_string("error") == JJZStatusEnum.ERROR
        assert JJZStatusEnum.from_string("unknown") == JJZStatusEnum.UNKNOWN

    def test_from_string_status_mapping(self):
        """测试 from_string - 状态映射"""
        # approved -> VALID
        assert JJZStatusEnum.from_string("approved") == JJZStatusEnum.VALID
        assert JJZStatusEnum.from_string("APPROVED") == JJZStatusEnum.VALID
        
        # active -> VALID
        assert JJZStatusEnum.from_string("active") == JJZStatusEnum.VALID
        
        # effective -> VALID
        assert JJZStatusEnum.from_string("effective") == JJZStatusEnum.VALID
        
        # reviewing -> PENDING
        assert JJZStatusEnum.from_string("reviewing") == JJZStatusEnum.PENDING
        
        # auditing -> PENDING
        assert JJZStatusEnum.from_string("auditing") == JJZStatusEnum.PENDING
        
        # rejected -> INVALID
        assert JJZStatusEnum.from_string("rejected") == JJZStatusEnum.INVALID
        
        # denied -> INVALID
        assert JJZStatusEnum.from_string("denied") == JJZStatusEnum.INVALID
        
        # failed -> ERROR
        assert JJZStatusEnum.from_string("failed") == JJZStatusEnum.ERROR
        
        # exception -> ERROR
        assert JJZStatusEnum.from_string("exception") == JJZStatusEnum.ERROR

    def test_from_string_unknown(self):
        """测试 from_string - 未知状态"""
        assert JJZStatusEnum.from_string("unknown_status") == JJZStatusEnum.UNKNOWN
        assert JJZStatusEnum.from_string("xyz") == JJZStatusEnum.UNKNOWN

    def test_is_valid_property(self):
        """测试 is_valid 属性"""
        assert JJZStatusEnum.VALID.is_valid is True
        assert JJZStatusEnum.EXPIRED.is_valid is False
        assert JJZStatusEnum.PENDING.is_valid is False
        assert JJZStatusEnum.INVALID.is_valid is False
        assert JJZStatusEnum.ERROR.is_valid is False
        assert JJZStatusEnum.UNKNOWN.is_valid is False

    def test_is_expired_property(self):
        """测试 is_expired 属性"""
        assert JJZStatusEnum.EXPIRED.is_expired is True
        assert JJZStatusEnum.VALID.is_expired is False
        assert JJZStatusEnum.PENDING.is_expired is False
        assert JJZStatusEnum.INVALID.is_expired is False
        assert JJZStatusEnum.ERROR.is_expired is False
        assert JJZStatusEnum.UNKNOWN.is_expired is False

    def test_is_pending_property(self):
        """测试 is_pending 属性"""
        assert JJZStatusEnum.PENDING.is_pending is True
        assert JJZStatusEnum.VALID.is_pending is False
        assert JJZStatusEnum.EXPIRED.is_pending is False
        assert JJZStatusEnum.INVALID.is_pending is False
        assert JJZStatusEnum.ERROR.is_pending is False
        assert JJZStatusEnum.UNKNOWN.is_pending is False

    def test_is_invalid_property(self):
        """测试 is_invalid 属性"""
        assert JJZStatusEnum.INVALID.is_invalid is True
        assert JJZStatusEnum.VALID.is_invalid is False
        assert JJZStatusEnum.EXPIRED.is_invalid is False
        assert JJZStatusEnum.PENDING.is_invalid is False
        assert JJZStatusEnum.ERROR.is_invalid is False
        assert JJZStatusEnum.UNKNOWN.is_invalid is False

    def test_is_error_property(self):
        """测试 is_error 属性"""
        assert JJZStatusEnum.ERROR.is_error is True
        assert JJZStatusEnum.VALID.is_error is False
        assert JJZStatusEnum.EXPIRED.is_error is False
        assert JJZStatusEnum.PENDING.is_error is False
        assert JJZStatusEnum.INVALID.is_error is False
        assert JJZStatusEnum.UNKNOWN.is_error is False

    def test_is_actionable_property(self):
        """测试 is_actionable 属性"""
        assert JJZStatusEnum.VALID.is_actionable is True
        assert JJZStatusEnum.EXPIRED.is_actionable is True
        assert JJZStatusEnum.PENDING.is_actionable is False
        assert JJZStatusEnum.INVALID.is_actionable is False
        assert JJZStatusEnum.ERROR.is_actionable is False
        assert JJZStatusEnum.UNKNOWN.is_actionable is False

    def test_needs_attention_property(self):
        """测试 needs_attention 属性"""
        assert JJZStatusEnum.EXPIRED.needs_attention is True
        assert JJZStatusEnum.ERROR.needs_attention is True
        assert JJZStatusEnum.INVALID.needs_attention is True
        assert JJZStatusEnum.VALID.needs_attention is False
        assert JJZStatusEnum.PENDING.needs_attention is False
        assert JJZStatusEnum.UNKNOWN.needs_attention is False

    def test_description_property(self):
        """测试 description 属性"""
        assert JJZStatusEnum.VALID.description == "有效"
        assert JJZStatusEnum.EXPIRED.description == "已过期"
        assert JJZStatusEnum.PENDING.description == "审核中"
        assert JJZStatusEnum.INVALID.description == "无效"
        assert JJZStatusEnum.ERROR.description == "错误"
        assert JJZStatusEnum.UNKNOWN.description == "未知"

