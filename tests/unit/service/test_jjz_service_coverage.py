"""
JJZService 覆盖信号计算测试

验证 `_is_effective_on` 与 `_query_multiple_status` 在多记录、互斥状态、
有效期边界、解析失败等情况下的 today_covered / tomorrow_covered 计算。
"""

from datetime import date

import pytest

from jjz_alert.service.jjz.jjz_service import _is_effective_on
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum

_UNSET = object()


def _record(
    blztmc="审核通过(生效中)", valid_start=_UNSET, valid_end=_UNSET, **overrides
):
    today = date.today()
    defaults = dict(
        plate="京A12345",
        status=JJZStatusEnum.VALID.value,
        valid_start=today.isoformat() if valid_start is _UNSET else valid_start,
        valid_end=today.isoformat() if valid_end is _UNSET else valid_end,
        blztmc=blztmc,
        jjzzlmc="进京证（六环外）",
        data_source="api",
    )
    defaults.update(overrides)
    return JJZStatus(**defaults)


@pytest.mark.unit
class TestIsEffectiveOn:
    def test_effective_when_in_range_and_active(self):
        rec = _record(
            blztmc="审核通过(生效中)",
            valid_start="2025-08-10",
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is True

    def test_effective_when_pending_future_start(self):
        """已批准待生效记录覆盖未来日期"""
        rec = _record(
            blztmc="审核通过(待生效)",
            valid_start="2025-08-15",
            valid_end="2025-08-22",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is True
        assert _is_effective_on(rec, date(2025, 8, 22)) is True

    def test_not_effective_outside_range(self):
        rec = _record(
            blztmc="审核通过(生效中)",
            valid_start="2025-08-10",
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 9)) is False
        assert _is_effective_on(rec, date(2025, 8, 21)) is False

    def test_not_effective_when_blztmc_lapsed(self):
        rec = _record(
            blztmc="已失效",
            valid_start="2025-08-10",
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is False

    def test_not_effective_when_blztmc_missing(self):
        rec = _record(
            blztmc=None,
            valid_start="2025-08-10",
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is False

    def test_not_effective_when_valid_start_missing(self):
        rec = _record(
            blztmc="审核通过(生效中)",
            valid_start=None,
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is False

    def test_not_effective_when_valid_end_missing(self):
        rec = _record(
            blztmc="审核通过(生效中)",
            valid_start="2025-08-10",
            valid_end=None,
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is False

    def test_not_effective_when_dates_unparseable(self):
        rec = _record(
            blztmc="审核通过(生效中)",
            valid_start="not-a-date",
            valid_end="2025-08-20",
        )
        assert _is_effective_on(rec, date(2025, 8, 15)) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueryMultipleStatusCoverage:
    """通过 _query_multiple_status 端到端验证 today_cov / tomorrow_cov 计算"""

    @pytest.fixture
    def jjz_service(self):
        from unittest.mock import AsyncMock, Mock

        from jjz_alert.service.jjz.jjz_service import JJZService

        mock_cache = Mock()
        mock_cache.get_jjz_data = AsyncMock()
        mock_cache.cache_jjz_data = AsyncMock()
        mock_cache.delete_jjz_data = AsyncMock()
        return JJZService(mock_cache)

    async def _query(self, jjz_service, account, bzclxx, today_iso="2025-08-15"):
        """通用查询入口：mock load_accounts + check_jjz_status + 固定 today"""
        from unittest.mock import patch

        with patch.object(jjz_service, "load_accounts", return_value=[account]):
            with patch.object(
                jjz_service,
                "check_jjz_status",
                return_value={"data": {"bzclxx": bzclxx}},
            ):
                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date.fromisoformat(today_iso)
                    mock_date.fromisoformat = date.fromisoformat
                    return await jjz_service.get_multiple_status_with_context(
                        ["京A12345"]
                    )

    async def test_outer_active_today_covers_today(
        self, jjz_service, sample_jjz_account
    ):
        bzclxx = [
            {
                "hphm": "京A12345",
                "sycs": "8",
                "bzxx": [
                    {
                        "jjzzlmc": "进京证(六环外)",
                        "blztmc": "审核通过(生效中)",
                        "blzt": "1",
                        "sqsj": "2025-08-10 09:00:00",
                        "yxqs": "2025-08-10",
                        "yxqz": "2025-08-15",  # 今天到期
                        "sxsyts": "0",
                    }
                ],
            }
        ]
        _, ctxs = await self._query(jjz_service, sample_jjz_account, bzclxx)
        ctx = ctxs["京A12345"]
        assert ctx[3] is True  # today_cov
        assert ctx[4] is False  # tomorrow_cov
        assert ctx[5] == date(2025, 8, 15)  # today_anchor 与 mock 的 today 一致

    async def test_inner_active_inner_outer_mutual_exclusion(
        self, jjz_service, sample_jjz_account
    ):
        """六环内活跃（生效中），六环外已失效（互斥规则）：
        today_cov 由六环内提供，tomorrow_cov 也由六环内提供（valid_end=8-20 仍覆盖 8-16）"""
        bzclxx = [
            {
                "hphm": "京A12345",
                "sycs": "8",
                "bzxx": [
                    {
                        "jjzzlmc": "进京证(六环外)",
                        "blztmc": "已失效",  # 互斥下被服务端置为失效
                        "blzt": "0",
                        "sqsj": "2025-08-10 09:00:00",
                        "yxqs": "2025-08-10",
                        "yxqz": "2025-08-20",
                        "sxsyts": "5",
                    },
                    {
                        "jjzzlmc": "进京证(六环内)",
                        "blztmc": "审核通过(生效中)",
                        "blzt": "1",
                        "sqsj": "2025-08-15 09:00:00",
                        "yxqs": "2025-08-15",
                        "yxqz": "2025-08-20",
                        "sxsyts": "5",
                    },
                ],
            }
        ]
        _, ctxs = await self._query(jjz_service, sample_jjz_account, bzclxx)
        ctx = ctxs["京A12345"]
        assert ctx[3] is True  # today_cov 由六环内提供
        assert ctx[4] is True  # tomorrow_cov 由六环内提供
        # 续办上下文取所有记录中 apply_time 最新一条（六环内）；
        # 下游消费方仅依赖 vehicle 层字段，记录类型不影响续办语义
        assert ctx[2].jjzzlmc == "进京证(六环内)"

    async def test_pending_future_record_covers_tomorrow(
        self, jjz_service, sample_jjz_account
    ):
        """六环外今日到期 + 六环内明日起待生效 → today_cov=Y, tomorrow_cov=Y"""
        bzclxx = [
            {
                "hphm": "京A12345",
                "sycs": "8",
                "bzxx": [
                    {
                        "jjzzlmc": "进京证(六环外)",
                        "blztmc": "审核通过(生效中)",
                        "blzt": "1",
                        "sqsj": "2025-08-10 09:00:00",
                        "yxqs": "2025-08-10",
                        "yxqz": "2025-08-15",
                        "sxsyts": "0",
                    },
                    {
                        "jjzzlmc": "进京证(六环内)",
                        "blztmc": "审核通过(待生效)",
                        "blzt": "6",
                        "sqsj": "2025-08-15 09:00:00",
                        "yxqs": "2025-08-16",
                        "yxqz": "2025-08-22",
                        "sxsyts": "7",
                    },
                ],
            }
        ]
        _, ctxs = await self._query(jjz_service, sample_jjz_account, bzclxx)
        ctx = ctxs["京A12345"]
        assert ctx[3] is True  # 今天有六环外
        assert ctx[4] is True  # 明天有六环内待生效

    async def test_all_records_lapsed_no_coverage(
        self, jjz_service, sample_jjz_account
    ):
        """所有记录都已失效 → today_cov=N, tomorrow_cov=N"""
        bzclxx = [
            {
                "hphm": "京A12345",
                "sycs": "8",
                "bzxx": [
                    {
                        "jjzzlmc": "进京证(六环外)",
                        "blztmc": "已失效",
                        "blzt": "0",
                        "sqsj": "2025-08-01 09:00:00",
                        "yxqs": "2025-08-01",
                        "yxqz": "2025-08-10",
                        "sxsyts": "0",
                    }
                ],
            }
        ]
        _, ctxs = await self._query(jjz_service, sample_jjz_account, bzclxx)
        ctx = ctxs["京A12345"]
        assert ctx[3] is False
        assert ctx[4] is False

    async def test_outer_today_only_tomorrow_uncovered(
        self, jjz_service, sample_jjz_account
    ):
        """今天有六环外、明天没有任何记录 → today_cov=Y, tomorrow_cov=N
        典型场景：触发 RENEW_TOMORROW"""
        bzclxx = [
            {
                "hphm": "京A12345",
                "sycs": "8",
                "bzxx": [
                    {
                        "jjzzlmc": "进京证(六环外)",
                        "blztmc": "审核通过(生效中)",
                        "blzt": "1",
                        "sqsj": "2025-08-08 09:00:00",
                        "yxqs": "2025-08-08",
                        "yxqz": "2025-08-15",
                        "sxsyts": "0",
                    }
                ],
            }
        ]
        _, ctxs = await self._query(jjz_service, sample_jjz_account, bzclxx)
        ctx = ctxs["京A12345"]
        assert ctx[3] is True
        assert ctx[4] is False
