"""
自动续办服务单元测试
"""

import asyncio
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
from jjz_alert.service.jjz.renew_decider import RenewDecision


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

        assert body["vId"] == "V001"
        assert body["hphm"] == "京A12345"
        assert body["hpzl"] == "02"
        assert body["cllx"] == "01"
        assert body["elzqyms"] == "六环外规则"
        assert body["jsrxm"] == "张三"
        assert body["jszh"] == "110101199001011234"
        assert body["jjrq"] == "2026-04-01"
        assert body["jjzzl"] == "02"
        assert body["txrxx"] == []
        assert body["jingState"] == ""
        assert body["area"] == "朝阳区"
        assert body["jjmd"] == "03"
        assert body["jjmdmc"] == "探亲访友"
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


@pytest.mark.unit
class TestScheduleRenew:
    """续办派发器集成测试（mock sleep + execute_renew）"""

    @pytest.mark.asyncio
    async def test_dispatch_runs_execute_and_push(self):
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()
        response_data = {"data": {}}

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(return_value=False),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock(
                return_value=RenewResult(
                    plate=plate_config.plate,
                    success=True,
                    message="ok",
                    step="done",
                    jjrq="2026-04-01",
                )
            )
            mock_service.push_renew_result = AsyncMock(return_value=None)

            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                response_data,
                accounts=None,
                decision=RenewDecision.RENEW_TOMORROW,
                min_delay=0,
                max_delay=0,
            )

            mock_service.execute_renew.assert_awaited_once()
            mock_service.push_renew_result.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dedup_skips_execute(self):
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(return_value=True),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock()
            mock_service.push_renew_result = AsyncMock()

            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                {"data": {}},
                accounts=None,
                decision=RenewDecision.RENEW_TODAY,
                min_delay=0,
                max_delay=0,
            )

            mock_service.execute_renew.assert_not_called()
            mock_service.push_renew_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_global_lock_serializes_concurrent_dispatches(self):
        """多协程并发时通过全局锁串行执行（threading.Lock 跨 loop/线程安全）"""
        from jjz_alert.service.jjz import renew_trigger

        running = 0
        max_concurrent = 0
        order = []

        async def fake_execute_renew(plate_config, *args, **kwargs):
            nonlocal running, max_concurrent
            running += 1
            max_concurrent = max(max_concurrent, running)
            order.append(plate_config.plate)
            await asyncio.sleep(0)
            running -= 1
            return RenewResult(
                plate=plate_config.plate,
                success=True,
                message="ok",
                step="done",
            )

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(return_value=False),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock(side_effect=fake_execute_renew)
            mock_service.push_renew_result = AsyncMock(return_value=None)

            tasks = [
                renew_trigger.schedule_renew(
                    _make_plate_config(plate=f"京A0000{i}"),
                    _make_jjz_status(plate=f"京A0000{i}"),
                    {"data": {}},
                    accounts=None,
                    decision=RenewDecision.RENEW_TODAY,
                    min_delay=0,
                    max_delay=0,
                )
                for i in range(4)
            ]
            await asyncio.gather(*tasks)

        assert max_concurrent == 1
        assert len(order) == 4


@pytest.mark.unit
class TestRenewDedupRedisOps:
    """续办当日防重 Redis key 接口契约测试

    防回归：`auto_renew_service` 与 `renew_trigger` 必须使用 `redis_ops.get` /
    `redis_ops.set`，而不是不存在的 `redis_get` / `redis_set` 模块级函数。
    """

    @pytest.mark.asyncio
    async def test_auto_renew_service_has_renewed_today_uses_redis_ops_get(self):
        from jjz_alert.config.redis import operations as ops_module

        service = AutoRenewService()
        with patch.object(
            ops_module.redis_ops, "get", new=AsyncMock(return_value="1")
        ) as mock_get:
            result = await service._has_renewed_today("京A12345")
        assert result is True
        mock_get.assert_awaited_once()
        called_key = mock_get.await_args.args[0]
        assert called_key.startswith("auto_renew:京A12345:")

    @pytest.mark.asyncio
    async def test_auto_renew_service_mark_renewed_today_uses_redis_ops_set(self):
        from jjz_alert.config.redis import operations as ops_module

        service = AutoRenewService()
        with patch.object(
            ops_module.redis_ops, "set", new=AsyncMock(return_value=True)
        ) as mock_set:
            await service._mark_renewed_today("京A12345")
        mock_set.assert_awaited_once()
        called_key = mock_set.await_args.args[0]
        assert called_key.startswith("auto_renew:京A12345:")
        assert mock_set.await_args.args[1] == "1"
        assert mock_set.await_args.kwargs.get("ttl") == 86400

    @pytest.mark.asyncio
    async def test_renew_trigger_has_renewed_today_uses_redis_ops_get(self):
        from jjz_alert.config.redis import operations as ops_module
        from jjz_alert.service.jjz import renew_trigger

        with patch.object(
            ops_module.redis_ops, "get", new=AsyncMock(return_value=None)
        ) as mock_get:
            result = await renew_trigger._has_renewed_today("京A12345")
        assert result is False
        mock_get.assert_awaited_once()
        called_key = mock_get.await_args.args[0]
        assert called_key.startswith("auto_renew:京A12345:")
