"""进京证查询响应字段：剩余次数、审核原因、当日限行。"""

from datetime import date

import pytest

from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.permit_lookup import (
    lookup_traffic_limited_today,
    to_permit_payload,
    traffic_limited_today_value,
)
from jjz_alert.service.traffic.traffic_models import PlateTrafficStatus, TrafficRule
from jjz_alert.service.traffic.traffic_service import traffic_service

PLATE = "京A00000"


def _rule(is_limited: bool) -> TrafficRule:
    return TrafficRule(
        date=date(2026, 11, 12),
        limited_numbers="1和6" if is_limited else "不限行",
        limited_time="2026年11月12日",
        is_limited=is_limited,
    )


def _traffic(is_limited: bool, error_message=None, rule=None) -> PlateTrafficStatus:
    return PlateTrafficStatus(
        plate=PLATE,
        date=date(2026, 11, 12),
        is_limited=is_limited,
        tail_number="0",
        rule=rule,
        error_message=error_message,
    )


@pytest.mark.unit
class TestPermitPayloadFields:
    def test_maps_numeric_count_and_reason(self):
        payload = to_permit_payload(
            JJZStatus(
                plate=PLATE,
                status="valid",
                sycs="8",
                reject_reason="审核未通过",
            ),
            PLATE,
            traffic_limited_today=True,
        )

        assert payload["remaining_count"] == 8
        assert payload["reject_reason"] == "审核未通过"
        assert payload["traffic_limited_today"] is True
        assert payload["days_remaining"] is None
        assert isinstance(payload["remaining_count"], int)

    def test_integer_and_zero_counts_are_kept(self):
        assert (
            to_permit_payload(JJZStatus(plate=PLATE, status="valid", sycs=0), PLATE)[
                "remaining_count"
            ]
            == 0
        )
        assert (
            to_permit_payload(
                JJZStatus(plate=PLATE, status="valid", sycs=" 4 "), PLATE
            )["remaining_count"]
            == 4
        )

    def test_blank_or_non_numeric_count_and_reason_are_null(self):
        for sycs in (None, "", "   ", "未知", True):
            payload = to_permit_payload(
                JJZStatus(
                    plate=PLATE,
                    status="pending",
                    sycs=sycs,
                    reject_reason="  ",
                ),
                PLATE,
            )
            assert payload["remaining_count"] is None
            assert payload["reject_reason"] is None
            assert payload["traffic_limited_today"] is None


@pytest.mark.unit
class TestTrafficLimitedTodayValue:
    def test_uses_service_conclusion_when_rule_is_present(self):
        assert traffic_limited_today_value(_traffic(True, rule=_rule(True))) is True
        assert traffic_limited_today_value(_traffic(False, rule=_rule(False))) is False

    def test_failure_placeholder_is_null(self):
        failed = _traffic(False, error_message="未找到日期 2026-11-12 的限行规则")
        assert failed.is_limited is False
        assert traffic_limited_today_value(failed) is None
        assert traffic_limited_today_value(_traffic(False, rule=None)) is None
        assert traffic_limited_today_value(None) is None


@pytest.mark.unit
class TestLookupTrafficLimitedToday:
    @pytest.mark.asyncio
    async def test_reuses_check_plate_limited(self, monkeypatch):
        from unittest.mock import AsyncMock

        lookup = AsyncMock(return_value=_traffic(True, rule=_rule(True)))
        monkeypatch.setattr(traffic_service, "check_plate_limited", lookup)

        assert await lookup_traffic_limited_today(PLATE) is True
        lookup.assert_awaited_once_with(PLATE)

    @pytest.mark.asyncio
    async def test_exception_is_null_and_does_not_raise(self, monkeypatch):
        from unittest.mock import AsyncMock

        lookup = AsyncMock(side_effect=RuntimeError("down"))
        monkeypatch.setattr(traffic_service, "check_plate_limited", lookup)

        assert await lookup_traffic_limited_today(PLATE) is None
