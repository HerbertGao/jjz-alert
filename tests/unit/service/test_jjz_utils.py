"""
JJZ Utils 单元测试
"""

from unittest.mock import Mock, patch

import pytest

from jjz_alert.service.jjz import jjz_utils


@pytest.mark.unit
class TestFormatValidDates:
    """format_valid_dates 函数测试类"""

    def test_format_same_year(self):
        """测试同年日期格式化"""
        start, end = jjz_utils.format_valid_dates("2025-08-15", "2025-08-20")
        assert start == "08-15"
        assert end == "08-20"

    def test_format_cross_year(self):
        """测试跨年日期格式化"""
        start, end = jjz_utils.format_valid_dates("2024-12-25", "2025-01-05")
        assert start == "2024-12-25"
        assert end == "2025-01-05"

    def test_format_none_start(self):
        """测试开始日期为None"""
        start, end = jjz_utils.format_valid_dates(None, "2025-08-20")
        assert start == ""
        assert end == "2025-08-20"

    def test_format_none_end(self):
        """测试结束日期为None"""
        start, end = jjz_utils.format_valid_dates("2025-08-15", None)
        assert start == "2025-08-15"
        assert end == ""

    def test_format_both_none(self):
        """测试两个日期都为None"""
        start, end = jjz_utils.format_valid_dates(None, None)
        assert start == ""
        assert end == ""

    def test_format_empty_string(self):
        """测试空字符串"""
        start, end = jjz_utils.format_valid_dates("", "")
        assert start == ""
        assert end == ""

    def test_format_invalid_date(self):
        """测试无效日期格式"""
        start, end = jjz_utils.format_valid_dates("invalid", "2025-08-20")
        assert start == "invalid"
        assert end == "2025-08-20"

    def test_format_invalid_both(self):
        """测试两个日期都无效"""
        start, end = jjz_utils.format_valid_dates("invalid1", "invalid2")
        assert start == "invalid1"
        assert end == "invalid2"


@pytest.mark.unit
class TestExtractJJZTypeFromJJZZLMC:
    """extract_jjz_type_from_jjzzlmc 函数测试类"""

    def test_extract_chinese_brackets(self):
        """测试中文括号提取"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("进京证（六环外）")
        assert result == "六环外"

    def test_extract_english_brackets(self):
        """测试英文括号提取"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("进京证(六环内)")
        assert result == "六环内"

    def test_extract_no_brackets(self):
        """测试无括号情况"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("进京证")
        assert result == "进京证"

    def test_extract_empty_string(self):
        """测试空字符串"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("")
        assert result == "未知"

    def test_extract_none(self):
        """测试None值"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc(None)
        assert result == "未知"

    def test_extract_only_left_bracket(self):
        """测试只有左括号"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("进京证（六环外")
        assert result == "进京证（六环外"

    def test_extract_only_right_bracket(self):
        """测试只有右括号"""
        result = jjz_utils.extract_jjz_type_from_jjzzlmc("进京证六环外）")
        assert result == "进京证六环外）"


@pytest.mark.unit
class TestExtractStatusFromBLZTMC:
    """extract_status_from_blztmc 函数测试类"""

    def test_extract_chinese_brackets_approved(self):
        """测试审核通过状态 - 中文括号"""
        result = jjz_utils.extract_status_from_blztmc("审核通过（生效中）", "valid")
        assert result == "生效中"

    def test_extract_english_brackets_approved(self):
        """测试审核通过状态 - 英文括号"""
        result = jjz_utils.extract_status_from_blztmc("审核通过(待生效)", "pending")
        assert result == "待生效"

    def test_extract_no_brackets_approved(self):
        """测试审核通过状态 - 无括号"""
        result = jjz_utils.extract_status_from_blztmc("审核通过", "valid")
        assert result == "审核通过"

    def test_extract_not_approved(self):
        """测试非审核通过状态"""
        result = jjz_utils.extract_status_from_blztmc("审核中", "pending")
        assert result == "审核中"

    def test_extract_empty_string(self):
        """测试空字符串"""
        result = jjz_utils.extract_status_from_blztmc("", "valid")
        assert result == "未知"

    def test_extract_none(self):
        """测试None值"""
        result = jjz_utils.extract_status_from_blztmc(None, "valid")
        assert result == "未知"


@pytest.mark.unit
class TestFormatJJZPushContent:
    """format_jjz_push_content 函数测试类"""

    @patch("jjz_alert.base.message_templates.template_manager")
    def test_format_jjz_push_content(self, mock_template_manager):
        """测试格式化进京证推送内容"""
        mock_template_manager.format_valid_status.return_value = "测试内容"

        result = jjz_utils.format_jjz_push_content(
            display_name="京A12345",
            jjzzlmc="进京证(六环内)",
            blztmc="审核通过(生效中)",
            status="valid",
            valid_start="2025-08-15",
            valid_end="2025-08-20",
            days_remaining=5,
            sycs="8",
        )

        assert result == "测试内容"
        mock_template_manager.format_valid_status.assert_called_once()
        call_args = mock_template_manager.format_valid_status.call_args[1]
        assert call_args["display_name"] == "京A12345"
        assert call_args["jjz_type"] == "六环内"
        assert call_args["status_text"] == "生效中"
        assert call_args["valid_start"] == "08-15"
        assert call_args["valid_end"] == "08-20"
        assert call_args["days_remaining"] == 5
        assert call_args["sycs"] == "8"

    @patch("jjz_alert.base.message_templates.template_manager")
    def test_format_jjz_push_content_cross_year(self, mock_template_manager):
        """测试跨年日期格式化"""
        mock_template_manager.format_valid_status.return_value = "测试内容"

        jjz_utils.format_jjz_push_content(
            display_name="京A12345",
            jjzzlmc="进京证(六环内)",
            blztmc="审核通过(生效中)",
            status="valid",
            valid_start="2024-12-25",
            valid_end="2025-01-05",
            days_remaining=10,
            sycs="8",
        )

        call_args = mock_template_manager.format_valid_status.call_args[1]
        assert call_args["valid_start"] == "2024-12-25"
        assert call_args["valid_end"] == "2025-01-05"


@pytest.mark.unit
class TestFormatJJZExpiredContent:
    """format_jjz_expired_content 函数测试类"""

    @patch("jjz_alert.base.message_templates.template_manager")
    def test_format_jjz_expired_content(self, mock_template_manager):
        """测试格式化过期推送内容"""
        mock_template_manager.format_expired_status.return_value = "过期内容"

        result = jjz_utils.format_jjz_expired_content(
            display_name="京A12345",
            sycs="8",
        )

        assert result == "过期内容"
        mock_template_manager.format_expired_status.assert_called_once_with(
            "京A12345", "8"
        )


@pytest.mark.unit
class TestFormatJJZPendingContent:
    """format_jjz_pending_content 函数测试类"""

    @patch("jjz_alert.base.message_templates.template_manager")
    def test_format_jjz_pending_content(self, mock_template_manager):
        """测试格式化审核中推送内容"""
        mock_template_manager.format_pending_status.return_value = "审核中内容"

        result = jjz_utils.format_jjz_pending_content(
            display_name="京A12345",
            jjzzlmc="进京证(六环内)",
            apply_time="2025-08-15 10:00:00",
        )

        assert result == "审核中内容"
        mock_template_manager.format_pending_status.assert_called_once()
        call_args = mock_template_manager.format_pending_status.call_args[0]
        assert call_args[0] == "京A12345"
        assert call_args[1] == "六环内"
        assert call_args[2] == "2025-08-15 10:00:00"


@pytest.mark.unit
class TestFormatJJZErrorContent:
    """format_jjz_error_content 函数测试类"""

    @patch("jjz_alert.base.message_templates.template_manager")
    def test_format_jjz_error_content(self, mock_template_manager):
        """测试格式化错误推送内容"""
        mock_template_manager.format_error_status.return_value = "错误内容"

        result = jjz_utils.format_jjz_error_content(
            display_name="京A12345",
            jjzzlmc="进京证(六环内)",
            status="error",
            error_msg="网络连接失败",
        )

        assert result == "错误内容"
        mock_template_manager.format_error_status.assert_called_once()
        call_args = mock_template_manager.format_error_status.call_args[0]
        assert call_args[0] == "京A12345"
        assert call_args[1] == "六环内"
        assert call_args[2] == "error"
        assert call_args[3] == "网络连接失败"
