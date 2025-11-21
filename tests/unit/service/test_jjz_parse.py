"""
JJZ Parse 单元测试
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from jjz_alert.service.jjz.jjz_parse import (
    _safe_int,
    parse_all_jjz_records,
    parse_jjz_response,
    parse_single_jjz_record,
    parse_status,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


@pytest.mark.unit
class TestParseStatus:
    """parse_status 函数测试类"""

    def test_parse_status_success(self):
        """测试解析状态 - 成功"""
        data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "sycs": "8",
                        "bzxx": [
                            {
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "blztmc": "审核通过(生效中)",
                                "jjzzlmc": "进京证(六环内)",
                            }
                        ],
                    }
                ]
            }
        }

        with patch("jjz_alert.service.jjz.jjz_parse.datetime") as mock_datetime:
            mock_now = datetime(2025, 8, 18, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime

            result = parse_status(data)

            assert result is not None
            assert len(result) == 1
            assert result[0]["plate"] == "京A12345"
            assert result[0]["end_date"] == "2025-08-20"
            assert result[0]["days_left"] == 2
            assert result[0]["sycs"] == "8"

    def test_parse_status_no_data(self):
        """测试解析状态 - 无data字段"""
        data = {"error": "网络错误"}

        result = parse_status(data)

        assert result is None

    def test_parse_status_no_bzclxx(self):
        """测试解析状态 - 无bzclxx字段"""
        data = {"data": {}}

        result = parse_status(data)

        assert result is None

    def test_parse_status_no_end_date(self):
        """测试解析状态 - 无结束日期"""
        data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "bzxx": [
                            {
                                "yxqs": "2025-08-15",
                                "blztmc": "审核中",
                                "jjzzlmc": "进京证(六环内)",
                            }
                        ],
                    }
                ]
            }
        }

        result = parse_status(data)

        assert result is not None
        assert result[0]["days_left"] == "无"

    def test_parse_status_invalid_date(self):
        """测试解析状态 - 无效日期格式"""
        data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "bzxx": [
                            {
                                "yxqs": "2025-08-15",
                                "yxqz": "invalid-date",
                                "blztmc": "审核通过(生效中)",
                                "jjzzlmc": "进京证(六环内)",
                            }
                        ],
                    }
                ]
            }
        }

        result = parse_status(data)

        assert result is not None
        assert result[0]["days_left"] == "日期格式错误"

    def test_parse_status_multiple_cars(self):
        """测试解析状态 - 多辆车"""
        data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "bzxx": [
                            {
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "blztmc": "审核通过(生效中)",
                                "jjzzlmc": "进京证(六环内)",
                            }
                        ],
                    },
                    {
                        "hphm": "京B67890",
                        "bzxx": [
                            {
                                "yxqs": "2025-08-16",
                                "yxqz": "2025-08-21",
                                "blztmc": "审核通过(生效中)",
                                "jjzzlmc": "进京证(六环外)",
                            }
                        ],
                    },
                ]
            }
        }

        with patch("jjz_alert.service.jjz.jjz_parse.datetime") as mock_datetime:
            mock_now = datetime(2025, 8, 18, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime

            result = parse_status(data)

            assert result is not None
            assert len(result) == 2
            assert result[0]["plate"] == "京A12345"
            assert result[1]["plate"] == "京B67890"

    def test_parse_status_no_hphm(self):
        """测试解析状态 - 无车牌号"""
        data = {
            "data": {
                "bzclxx": [
                    {
                        "bzxx": [
                            {
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "blztmc": "审核通过(生效中)",
                                "jjzzlmc": "进京证(六环内)",
                            }
                        ],
                    }
                ]
            }
        }

        with patch("jjz_alert.service.jjz.jjz_parse.datetime") as mock_datetime:
            mock_now = datetime(2025, 8, 18, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime

            result = parse_status(data)

            assert result is not None
            assert result[0]["plate"] == "未知车牌"


@pytest.mark.unit
class TestSafeInt:
    """_safe_int 函数测试类"""

    def test_safe_int_valid(self):
        """测试安全转换整数 - 有效值"""
        assert _safe_int("123") == 123
        assert _safe_int(456) == 456
        assert _safe_int("0") == 0

    def test_safe_int_none(self):
        """测试安全转换整数 - None值"""
        assert _safe_int(None) is None

    def test_safe_int_empty_string(self):
        """测试安全转换整数 - 空字符串"""
        assert _safe_int("") is None

    def test_safe_int_invalid(self):
        """测试安全转换整数 - 无效值"""
        assert _safe_int("abc") is None
        assert _safe_int("12.34") is None
        assert _safe_int([]) is None
        assert _safe_int({}) is None


@pytest.mark.unit
class TestParseSingleJJZRecord:
    """parse_single_jjz_record 函数测试类"""

    def test_parse_single_jjz_record_success(self):
        """测试解析单条记录 - 成功"""
        plate = "京A12345"
        record = {
            "blzt": "1",
            "blztmc": "审核通过(生效中)",
            "sqsj": "2025-08-15 10:00:00",
            "yxqs": "2025-08-15",
            "yxqz": "2025-08-20",
            "sxsyts": "5",
            "jjzzlmc": "进京证(六环内)",
        }
        vehicle = {"sycs": "8"}

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_single_jjz_record(
            plate, record, vehicle, "active", status_resolver, JJZStatus
        )

        assert result is not None
        assert result.plate == plate
        assert result.status == JJZStatusEnum.VALID.value
        assert result.apply_time == "2025-08-15 10:00:00"
        assert result.days_remaining == 5
        assert result.sycs == "8"

    def test_parse_single_jjz_record_exception(self):
        """测试解析单条记录 - 异常处理"""
        plate = "京A12345"
        record = {"invalid": "data"}
        vehicle = {}

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            raise Exception("测试异常")

        result = parse_single_jjz_record(
            plate, record, vehicle, "active", status_resolver, JJZStatus
        )

        assert result is None


@pytest.mark.unit
class TestParseAllJJZRecords:
    """parse_all_jjz_records 函数测试类"""

    def test_parse_all_jjz_records_error(self):
        """测试解析所有记录 - 响应包含错误"""
        response_data = {"error": "网络连接失败"}

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_all_jjz_records(response_data, status_resolver, JJZStatus)

        assert result == []

    def test_parse_all_jjz_records_no_bzclxx(self):
        """测试解析所有记录 - 无bzclxx"""
        response_data = {"data": {}}

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_all_jjz_records(response_data, status_resolver, JJZStatus)

        assert result == []

    def test_parse_all_jjz_records_empty_bzclxx(self):
        """测试解析所有记录 - 空bzclxx列表"""
        response_data = {"data": {"bzclxx": []}}

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_all_jjz_records(response_data, status_resolver, JJZStatus)

        assert result == []

    def test_parse_all_jjz_records_no_plate(self):
        """测试解析所有记录 - 无车牌号"""
        response_data = {
            "data": {
                "bzclxx": [
                    {
                        "bzxx": [
                            {
                                "blzt": "1",
                                "blztmc": "审核通过(生效中)",
                                "sqsj": "2025-08-15 10:00:00",
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "sxsyts": "5",
                            }
                        ],
                    }
                ]
            }
        }

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_all_jjz_records(response_data, status_resolver, JJZStatus)

        assert result == []


@pytest.mark.unit
class TestParseJJZResponse:
    """parse_jjz_response 函数测试类"""

    def test_parse_jjz_response_no_target_vehicle(self):
        """测试解析响应 - 未找到目标车辆"""
        plate = "京A12345"
        response_data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京B67890",
                        "bzxx": [
                            {
                                "blzt": "1",
                                "blztmc": "审核通过(生效中)",
                                "sqsj": "2025-08-15 10:00:00",
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "sxsyts": "5",
                            }
                        ],
                    }
                ]
            }
        }

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_jjz_response(plate, response_data, status_resolver, JJZStatus)

        assert result.plate == plate
        assert result.status == JJZStatusEnum.INVALID.value
        assert "未找到匹配车牌的记录" in result.error_message

    def test_parse_jjz_response_no_bzxx(self):
        """测试解析响应 - 无bzxx记录"""
        plate = "京A12345"
        response_data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "sycs": "8",
                    }
                ]
            }
        }

        def status_resolver(blzt, blztmc, yxqz, yxqs):
            return JJZStatusEnum.VALID.value

        result = parse_jjz_response(plate, response_data, status_resolver, JJZStatus)

        assert result.plate == plate
        assert result.status == JJZStatusEnum.INVALID.value
        assert "未找到进京证记录" in result.error_message

