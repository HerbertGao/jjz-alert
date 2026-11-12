"""进京证查询响应字段：剩余次数、审核原因、当日限行。"""

import asyncio
import inspect
import time
from datetime import date
from unittest.mock import AsyncMock

import pytest

from jjz_alert.service.jjz import permit_lookup
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.permit_lookup import (
    PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS,
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
        lookup = AsyncMock(return_value=_traffic(True, rule=_rule(True)))
        monkeypatch.setattr(traffic_service, "check_plate_limited", lookup)

        assert await lookup_traffic_limited_today(PLATE) is True
        lookup.assert_awaited_once_with(PLATE)

    @pytest.mark.asyncio
    async def test_exception_is_null_and_does_not_raise(self, monkeypatch):
        lookup = AsyncMock(side_effect=RuntimeError("down"))
        monkeypatch.setattr(traffic_service, "check_plate_limited", lookup)

        assert await lookup_traffic_limited_today(PLATE) is None

    def test_budget_covers_one_request_not_the_retry_cascade(self):
        # 套接字超时是 10 秒。预算要能等完这一次，但不能跟到多重重试。
        assert 10 < PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS <= 12

    @pytest.mark.asyncio
    async def test_timeout_returns_null_without_waiting_out_the_lookup(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            permit_lookup, "PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS", 0.05
        )

        async def slow(_plate):
            await asyncio.sleep(30)
            return _traffic(True, rule=_rule(True))

        monkeypatch.setattr(traffic_service, "check_plate_limited", slow)
        started = time.monotonic()

        assert await lookup_traffic_limited_today(PLATE) is None

        assert time.monotonic() - started < 1

    @pytest.mark.asyncio
    async def test_other_callers_keep_running_past_the_permit_deadline(
        self, monkeypatch
    ):
        """查询接口的时限不包住限行服务。直接调用仍会等完自己的查询。"""
        monkeypatch.setattr(
            permit_lookup, "PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS", 0.05
        )
        rule = TrafficRule(
            date=date.today(),
            limited_numbers="0和5",
            limited_time="2026年11月12日",
            is_limited=True,
        )

        async def slow_rule(_target_date, use_cache=True):
            await asyncio.sleep(0.2)
            return rule

        monkeypatch.setattr(traffic_service, "get_traffic_rule", slow_rule)

        started = time.monotonic()
        status = await traffic_service.check_plate_limited(PLATE)
        assert time.monotonic() - started >= 0.15
        assert status.is_limited is True
        assert status.error_message is None
        assert status.rule is rule

        started = time.monotonic()
        assert await lookup_traffic_limited_today(PLATE) is None
        assert time.monotonic() - started < 0.15

        assert traffic_service._max_retries == 3
        service_source = "\n".join(
            inspect.getsource(method)
            for method in (
                type(traffic_service).check_plate_limited,
                type(traffic_service)._fetch_rules_from_api,
                type(traffic_service).check_multiple_plates,
            )
        )
        assert "PERMIT_TRAFFIC_LOOKUP_TIMEOUT_SECONDS" not in service_source
        assert "for attempt in range(self._max_retries)" in service_source
