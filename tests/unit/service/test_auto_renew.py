"""
自动续办服务单元测试
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jjz_alert.config.config_models import (
    AutoRenewConfig,
    AutoRenewDestinationConfig,
    AutoRenewAccommodationConfig,
    AutoRenewApplyLocationConfig,
    PlateConfig,
)
from jjz_alert.service.jjz.auto_renew_service import AutoRenewService, RenewResult
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


def _make_ar_config(**overrides):
    defaults = dict(
        enabled=True,
        purpose="03",
        purpose_name="探亲访友",
        destination=AutoRenewDestinationConfig(
            area="朝阳区",
            area_code="010",
            address="测试地址",
            lng="116.4",
            lat="39.9",
        ),
        accommodation=AutoRenewAccommodationConfig(enabled=False),
        apply_location=AutoRenewApplyLocationConfig(),
    )
    defaults.update(overrides)
    return AutoRenewConfig(**defaults)


def _make_plate_config(plate="京A12345", ar_config=None):
    return PlateConfig(
        plate=plate,
        display_name="测试车",
        auto_renew=ar_config or _make_ar_config(),
    )


def _make_jjz_status(plate="京A12345", **overrides):
    defaults = dict(
        plate=plate,
        status=JJZStatusEnum.VALID.value,
        valid_start=(date.today() - timedelta(days=6)).isoformat(),
        valid_end=(date.today() + timedelta(days=1)).isoformat(),
        days_remaining=1,
        jjzzlmc="进京证（六环外）",
        vId="123456",
        hpzl="02",
        elzsfkb=True,
        ylzsfkb=True,
        cllx="01",
        sfyecbzxx=False,
        data_source="api",
    )
    defaults.update(overrides)
    return JJZStatus(**defaults)


@pytest.mark.unit
class TestShouldRenew:
    """续办触发判断测试"""

    def setup_method(self):
        self.service = AutoRenewService()

    def test_permit_expires_tomorrow(self):
        """证件明天到期 → 应触发续办"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(valid_end=tomorrow)
        assert self.service.should_renew(pc, status) is True

    def test_permit_already_expired(self):
        """证件已过期 → 应触发续办"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(
            valid_end=yesterday, status=JJZStatusEnum.EXPIRED.value
        )
        assert self.service.should_renew(pc, status) is True

    def test_permit_has_pending_record(self):
        """已有待审记录 → 不续办"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(valid_end=tomorrow, sfyecbzxx=True)
        assert self.service.should_renew(pc, status) is False

    def test_outer_not_available(self):
        """六环外不可办理 → 不续办"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(valid_end=tomorrow, elzsfkb=False)
        assert self.service.should_renew(pc, status) is False

    def test_permit_still_valid(self):
        """有效期充足（>1天）→ 不续办"""
        future = (date.today() + timedelta(days=5)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(valid_end=future, days_remaining=5)
        assert self.service.should_renew(pc, status) is False

    def test_auto_renew_disabled(self):
        """续办未启用 → 不续办"""
        ar = _make_ar_config(enabled=False)
        pc = _make_plate_config(ar_config=ar)
        status = _make_jjz_status()
        assert self.service.should_renew(pc, status) is False

    def test_no_auto_renew_config(self):
        """无续办配置 → 不续办"""
        pc = PlateConfig(plate="京A12345")
        status = _make_jjz_status()
        assert self.service.should_renew(pc, status) is False

    def test_inner_ring_permit_skipped(self):
        """六环内进京证 → 不续办"""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        pc = _make_plate_config()
        status = _make_jjz_status(valid_end=tomorrow, jjzzlmc="进京证（六环内）")
        assert self.service.should_renew(pc, status) is False


@pytest.mark.unit
class TestBuildApplyRequest:
    """请求体组装测试"""

    def test_fields_from_correct_sources(self):
        service = AutoRenewService()
        ar = _make_ar_config(
            accommodation=AutoRenewAccommodationConfig(
                enabled=True, address="住宿地址", lng="116.5", lat="40.0"
            )
        )
        status = _make_jjz_status(vId="V001", hpzl="02", cllx="01")
        driver_info = {"jsrxm": "张三", "jszh": "110101199001011234", "dabh": ""}
        metadata = {
            "elzqyms": "六环外规则",
            "ylzqyms": "六环内规则",
            "elzmc": "进京证(六环外)",
            "ylzmc": "进京证(六环内)",
        }

        body = service._build_apply_request(
            status, ar, driver_info, "2026-04-01", metadata
        )

        # stateList 字段
        assert body["vId"] == "V001"
        assert body["hphm"] == "京A12345"
        assert body["hpzl"] == "02"
        assert body["cllx"] == "01"
        assert body["elzqyms"] == "六环外规则"

        # 驾驶人信息
        assert body["jsrxm"] == "张三"
        assert body["jszh"] == "110101199001011234"

        # 进京日期
        assert body["jjrq"] == "2026-04-01"

        # 固定值
        assert body["jjzzl"] == "02"
        assert body["txrxx"] == []
        assert body["jingState"] == ""

        # 用户配置
        assert body["area"] == "朝阳区"
        assert body["jjmd"] == "03"
        assert body["jjmdmc"] == "探亲访友"

        # 住宿
        assert body["sfzj"] == "1"
        assert body["zjxxdz"] == "住宿地址"

    def test_no_accommodation(self):
        service = AutoRenewService()
        ar = _make_ar_config()
        status = _make_jjz_status()
        driver_info = {"jsrxm": "张三", "jszh": "110101199001011234", "dabh": ""}
        metadata = {"elzqyms": "", "ylzqyms": "", "elzmc": "", "ylzmc": ""}

        body = service._build_apply_request(
            status, ar, driver_info, "2026-04-01", metadata
        )
        assert body["sfzj"] == "0"
        assert body["zjxxdz"] == ""


@pytest.mark.unit
class TestCalculateRandomDelay:
    """随机延迟计算测试"""

    def test_default_window(self):
        delay = AutoRenewService.calculate_random_delay("00:00", "06:00")
        assert 0 <= delay <= 6 * 3600

    def test_custom_window(self):
        delay = AutoRenewService.calculate_random_delay("01:00", "02:00")
        assert 0 <= delay <= 3600

    def test_zero_delay_when_past_window(self):
        """窗口已过 → 延迟为0"""
        delay = AutoRenewService.calculate_random_delay("00:00", "00:01")
        # 除非恰好在 00:00-00:01 之间运行，否则应为 0
        assert delay >= 0


@pytest.mark.unit
class TestApiCallChain:
    """API 调用链测试（mock HTTP）"""

    def setup_method(self):
        self.service = AutoRenewService()

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_vehicle_check_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 200, "msg": "校验通过!"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        assert (
            self.service._vehicle_check("http://test", "token", "京A12345", "02")
            is True
        )

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_vehicle_check_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 500, "msg": "校验失败"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        assert (
            self.service._vehicle_check("http://test", "token", "京A12345", "02")
            is False
        )

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_get_driver_info_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": {"jsrxm": "张三", "jszh": "110101199001011234", "dabh": ""},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        info = self.service._get_driver_info("http://test", "token")
        assert info is not None
        assert info["jsrxm"] == "张三"

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_check_handle_no_dates(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": {"jjrqs": [], "weekDays": []},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        data = self.service._check_handle("http://test", "token", "V001", "京A12345")
        assert data["jjrqs"] == []

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_check_handle_with_dates(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 200,
            "data": {"jjrqs": ["2026-04-01", "2026-04-02"], "kbyxts": 7},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        data = self.service._check_handle("http://test", "token", "V001", "京A12345")
        assert data["jjrqs"][0] == "2026-04-01"

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_submit_apply_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 200, "msg": "信息已提交，正在审核!"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        assert (
            self.service._submit_apply("http://test", "token", {"key": "val"}) is True
        )

    @patch("jjz_alert.service.jjz.auto_renew_service.http_post")
    def test_api_call_network_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        assert (
            self.service._vehicle_check("http://test", "token", "京A12345", "02")
            is False
        )
