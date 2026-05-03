"""
续办决策器单元测试
"""

from datetime import date, timedelta

import pytest

from jjz_alert.config.config_models import (
    AutoRenewConfig,
    AutoRenewDestinationConfig,
    PlateConfig,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.jjz.renew_decider import RenewDecision, decide


def _ar(enabled=True):
    return AutoRenewConfig(
        enabled=enabled,
        purpose="03",
        purpose_name="探亲访友",
        destination=AutoRenewDestinationConfig(
            area="朝阳区",
            area_code="010",
            address="测试地址",
            lng="116.4",
            lat="39.9",
        ),
    )


def _plate(ar=None):
    return PlateConfig(plate="京A12345", display_name="测试车", auto_renew=ar)


def _status(**overrides):
    today = date.today()
    defaults = dict(
        plate="京A12345",
        status=JJZStatusEnum.VALID.value,
        valid_start=(today - timedelta(days=2)).isoformat(),
        valid_end=(today + timedelta(days=3)).isoformat(),
        days_remaining=3,
        jjzzlmc="进京证（六环外）",
        vId="V001",
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
class TestDecide:
    def test_today_valid_tomorrow_valid_skip(self):
        today = date.today()
        s = _status(valid_end=(today + timedelta(days=3)).isoformat())
        assert decide(_plate(_ar()), s) == RenewDecision.SKIP

    def test_today_valid_tomorrow_invalid_renew_tomorrow(self):
        today = date.today()
        s = _status(valid_end=today.isoformat())
        assert decide(_plate(_ar()), s) == RenewDecision.RENEW_TOMORROW

    def test_today_expired_renew_today(self):
        today = date.today()
        s = _status(
            valid_end=(today - timedelta(days=1)).isoformat(),
            status=JJZStatusEnum.EXPIRED.value,
        )
        assert decide(_plate(_ar()), s) == RenewDecision.RENEW_TODAY

    def test_status_invalid_skips(self):
        """INVALID 缺少 vId 等续办字段，显式跳过避免无意义派发"""
        s = _status(status=JJZStatusEnum.INVALID.value, valid_end=None)
        assert decide(_plate(_ar()), s) == RenewDecision.SKIP

    def test_pending_record_pending(self):
        today = date.today()
        s = _status(
            valid_end=(today - timedelta(days=1)).isoformat(),
            status=JJZStatusEnum.EXPIRED.value,
            sfyecbzxx=True,
        )
        assert decide(_plate(_ar()), s) == RenewDecision.PENDING

    def test_outer_not_available(self):
        today = date.today()
        s = _status(valid_end=today.isoformat(), elzsfkb=False)
        assert decide(_plate(_ar()), s) == RenewDecision.NOT_AVAILABLE

    def test_auto_renew_disabled(self):
        s = _status()
        assert decide(_plate(_ar(enabled=False)), s) == RenewDecision.SKIP

    def test_no_auto_renew_config(self):
        s = _status()
        assert decide(_plate(None), s) == RenewDecision.SKIP

    def test_inner_ring_permit_skipped(self):
        s = _status(jjzzlmc="进京证（六环内）")
        assert decide(_plate(_ar()), s) == RenewDecision.SKIP

    def test_missing_jjzzlmc_skipped(self):
        today = date.today()
        s = _status(
            jjzzlmc=None,
            status=JJZStatusEnum.VALID.value,
            valid_end=today.isoformat(),
        )
        assert decide(_plate(_ar()), s) == RenewDecision.SKIP

    def test_pending_takes_priority_over_not_available(self):
        today = date.today()
        s = _status(
            valid_end=today.isoformat(),
            sfyecbzxx=True,
            elzsfkb=False,
        )
        assert decide(_plate(_ar()), s) == RenewDecision.PENDING

    def test_invalid_valid_end_format_skips(self):
        s = _status(valid_end="not-a-date", status=JJZStatusEnum.VALID.value)
        assert decide(_plate(_ar()), s) == RenewDecision.SKIP
