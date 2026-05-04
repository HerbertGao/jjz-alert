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
class TestPushRenewResult:
    """推送续办结果通知测试

    防回归：直接验证 push_renew_result 内部对 unified_pusher.push 的
    调用签名（plate_config 必填、title/body/priority 等），避免历史 bug
    重现——之前因 schedule_renew 测试整个 mock 了 auto_renew_service，
    导致这个方法的签名错误一直没被测出来，直到生产 WARNING 暴露。
    """

    @pytest.mark.asyncio
    async def test_success_pushes_with_correct_signature(self):
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate,
            success=True,
            message="ok",
            step="done",
            jjrq="2026-04-01",
        )
        with patch.object(
            up_module, "push", new=AsyncMock(return_value=None)
        ) as mock_push:
            await service.push_renew_result(plate_config, result)
        # 必须只调用一次：不是按 plate.notifications 在外层循环
        mock_push.assert_awaited_once()
        kwargs = mock_push.await_args.kwargs
        assert kwargs.get("plate_config") is plate_config  # 关键：必填参数
        assert kwargs.get("title") == "进京证自动续办成功"
        # body 应包含进京日期值（模板渲染后）
        body = kwargs.get("body") or ""
        assert result.jjrq in body
        # 历史 bug 关键词检查：不应再传 notification_config / plate kwargs
        assert "notification_config" not in kwargs
        assert "plate" not in kwargs

    @pytest.mark.asyncio
    async def test_failure_pushes_high_priority(self):
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )
        from jjz_alert.service.notification.push_priority import PushPriority

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate,
            success=False,
            message="API 超时",
            step="check_handle",
        )
        with patch.object(
            up_module, "push", new=AsyncMock(return_value=None)
        ) as mock_push:
            await service.push_renew_result(plate_config, result)
        mock_push.assert_awaited_once()
        kwargs = mock_push.await_args.kwargs
        assert kwargs.get("priority") == PushPriority.HIGH
        assert kwargs.get("plate_config") is plate_config

    @pytest.mark.asyncio
    async def test_token_failure_uses_token_expired_template(self):
        """失败消息命中 token/unauthorized/401/403/认证失败/令牌 任一关键词时
        切换到 Token 失效模板，标题改为 "Token已失效" 提示用户手动更新配置"""
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate,
            success=False,
            message="API 返回 401 unauthorized",
            step="vehicle_check",
        )
        with patch.object(
            up_module, "push", new=AsyncMock(return_value=None)
        ) as mock_push:
            await service.push_renew_result(plate_config, result)
        kwargs = mock_push.await_args.kwargs
        assert "Token" in kwargs["title"]

    @pytest.mark.asyncio
    async def test_push_exception_is_logged_not_raised(self):
        """unified_pusher.push 抛异常时被吞 + 记 ERROR，不影响调用方"""
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate, success=True, message="ok", step="done"
        )
        with patch.object(
            up_module, "push", new=AsyncMock(side_effect=RuntimeError("push fail"))
        ):
            # 不应抛出
            await service.push_renew_result(plate_config, result)

    @pytest.mark.asyncio
    async def test_dedup_skip_does_not_push(self):
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate,
            success=True,
            message="当日已提交续办",
            step="dedup_skip",
        )
        with patch.object(
            up_module, "push", new=AsyncMock(return_value=None)
        ) as mock_push:
            await service.push_renew_result(plate_config, result)
        mock_push.assert_not_called()


@pytest.mark.unit
class TestExecuteRenewOrchestration:
    """execute_renew 端到端编排测试（mock 各步骤验证流程控制）

    覆盖之前因依赖完整 API 链而未单测的路径：dedup 跳过、vId 缺失、
    各步失败的提前返回、空 jjrqs、成功路径的 jjrq 取值与 redis 写入。
    """

    def _make_account(
        self, token="t", url="https://x:443/pro/applyRecordController/stateList"
    ):
        from jjz_alert.config.config_models import JJZAccount, JJZConfig

        return JJZAccount(name="acc1", jjz=JJZConfig(token=token, url=url))

    @pytest.mark.asyncio
    async def test_dedup_skip_path(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        with patch.object(
            service, "_has_renewed_today", new=AsyncMock(return_value=True)
        ):
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is True
        assert result.step == "dedup_skip"

    @pytest.mark.asyncio
    async def test_no_account_returns_init_error(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        result = await service.execute_renew(
            plate_config,
            status,
            {"data": {}},
            accounts=None,
            today_covered=False,
            tomorrow_covered=False,
        )
        assert result.success is False
        assert result.step == "init"

    @pytest.mark.asyncio
    async def test_missing_vid_returns_validation_error(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status(vId=None)
        with patch.object(
            service, "_has_renewed_today", new=AsyncMock(return_value=False)
        ):
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is False
        assert result.step == "validate_fields"

    @pytest.mark.asyncio
    async def test_vehicle_check_failure(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        service._last_api_error = "vehicle invalid"
        with patch.object(
            service, "_has_renewed_today", new=AsyncMock(return_value=False)
        ), patch.object(service, "_vehicle_check", return_value=False):
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is False
        assert result.step == "vehicle_check"

    @pytest.mark.asyncio
    async def test_check_handle_empty_jjrqs(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        with patch.object(
            service, "_has_renewed_today", new=AsyncMock(return_value=False)
        ), patch.object(service, "_vehicle_check", return_value=True), patch.object(
            service,
            "_get_driver_info",
            return_value={"jsrxm": "x", "jszh": "y", "dabh": ""},
        ), patch.object(
            service, "_driver_check", return_value=True
        ), patch.object(
            service, "_check_handle", return_value={"jjrqs": []}
        ):
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is False
        assert result.step == "check_handle"

    @pytest.mark.asyncio
    async def test_full_success_path(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        # 服务端给的进京日期必须是今天/明天且对应日未覆盖才会通过 useful 过滤；
        # 这里模拟"今日断档（today_covered=False），服务端给今日"的典型 RENEW_TODAY 派发
        today_str = date.today().isoformat()
        with patch.object(
            service, "_has_renewed_today", new=AsyncMock(return_value=False)
        ), patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ) as mock_mark, patch.object(
            service, "_vehicle_check", return_value=True
        ), patch.object(
            service,
            "_get_driver_info",
            return_value={"jsrxm": "张三", "jszh": "110", "dabh": ""},
        ), patch.object(
            service, "_driver_check", return_value=True
        ), patch.object(
            service,
            "_check_handle",
            return_value={"jjrqs": [today_str]},
        ), patch.object(
            service, "_check_road_info", return_value=True
        ), patch.object(
            service, "_submit_apply", return_value=True
        ):
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is True
        assert result.step == "done"
        assert result.jjrq == today_str
        # 成功后必须写入当日防重 key
        mock_mark.assert_awaited_once_with(plate_config.plate)


@pytest.mark.unit
class TestUsefulFilter:
    """useful 过滤器单测：纯函数，验证日期过滤规则"""

    def test_today_passes_when_today_uncovered(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        useful = AutoRenewService._filter_useful(
            [today.isoformat()],
            today_covered=False,
            tomorrow_covered=False,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == [today.isoformat()]

    def test_today_filtered_when_today_covered(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        useful = AutoRenewService._filter_useful(
            [today.isoformat()],
            today_covered=True,
            tomorrow_covered=False,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == []

    def test_tomorrow_filtered_when_tomorrow_covered(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        useful = AutoRenewService._filter_useful(
            [tomorrow.isoformat()],
            today_covered=False,
            tomorrow_covered=True,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == []

    def test_future_date_filtered_when_tomorrow_covered(self):
        """晚于明天的日期：tomorrow_covered=True 时也应过滤掉"""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        useful = AutoRenewService._filter_useful(
            [day_after.isoformat()],
            today_covered=False,
            tomorrow_covered=True,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == []

    def test_future_date_passes_when_tomorrow_uncovered(self):
        """晚于明天的日期：tomorrow_covered=False 时保留（连续段填补未来真空）"""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        useful = AutoRenewService._filter_useful(
            [day_after.isoformat()],
            today_covered=False,
            tomorrow_covered=False,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == [day_after.isoformat()]

    def test_unparseable_date_dropped(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        useful = AutoRenewService._filter_useful(
            ["not-a-date", today.isoformat()],
            today_covered=False,
            tomorrow_covered=False,
            today=today,
            tomorrow=tomorrow,
        )
        assert useful == [today.isoformat()]


@pytest.mark.unit
class TestExecuteRenewJjrqsBranches:
    """execute_renew 在 useful 过滤后的三态分支（设计 D4）"""

    def _make_account(
        self, token="t", url="https://x:443/pro/applyRecordController/stateList"
    ):
        from jjz_alert.config.config_models import JJZAccount, JJZConfig

        return JJZAccount(name="acc1", jjz=JJZConfig(token=token, url=url))

    def _patch_chain(self, service, jjrqs):
        """通用：mock 前 4 步 API + checkHandle 返回指定 jjrqs"""
        return [
            patch.object(
                service, "_has_renewed_today", new=AsyncMock(return_value=False)
            ),
            patch.object(service, "_vehicle_check", return_value=True),
            patch.object(
                service,
                "_get_driver_info",
                return_value={"jsrxm": "x", "jszh": "y", "dabh": ""},
            ),
            patch.object(service, "_driver_check", return_value=True),
            patch.object(service, "_check_handle", return_value={"jjrqs": jjrqs}),
            patch.object(service, "_check_road_info", return_value=True),
            patch.object(service, "_submit_apply", return_value=True),
        ]

    @pytest.mark.asyncio
    async def test_jjrqs_today_uncovered_submits(self):
        """服务端给今天 + today_cov=False → 提交今天，写防重 key"""
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        today_str = date.today().isoformat()
        from contextlib import ExitStack

        with ExitStack() as stack, patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ) as mock_mark:
            for p in self._patch_chain(service, [today_str]):
                stack.enter_context(p)
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is True
        assert result.skipped is False
        assert result.step == "done"
        assert result.jjrq == today_str
        mock_mark.assert_awaited_once_with(plate_config.plate)

    @pytest.mark.asyncio
    async def test_jjrqs_tomorrow_covered_silent_skip(self):
        """服务端给明天 + tomorrow_cov=True → useful=[]，静默 skipped=True，写防重 key"""
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        from contextlib import ExitStack

        with ExitStack() as stack, patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ) as mock_mark, patch.object(
            service, "_submit_apply", return_value=True
        ) as mock_submit:
            for p in self._patch_chain(service, [tomorrow_str]):
                stack.enter_context(p)
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=True,
            )
        assert result.success is False
        assert result.skipped is True
        assert result.step == "useful_filter_skip"
        # 静默 SKIP 必须写防重 key 避免下一轮 remind 重复派发
        mock_mark.assert_awaited_once_with(plate_config.plate)
        # 不应进入 _submit_apply
        mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_jjrqs_future_uncovered_submits(self):
        """服务端给后天 + tomorrow_cov=False → useful=[后天]，提交后天"""
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        day_after_str = (date.today() + timedelta(days=2)).isoformat()
        from contextlib import ExitStack

        with ExitStack() as stack, patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ):
            for p in self._patch_chain(service, [day_after_str]):
                stack.enter_context(p)
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is True
        assert result.skipped is False
        assert result.jjrq == day_after_str

    @pytest.mark.asyncio
    async def test_jjrqs_empty_alerts_no_dedup(self):
        """jjrqs=[] → 旧告警路径，不写防重 key（保留服务端异常告警语义）"""
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        from contextlib import ExitStack

        with ExitStack() as stack, patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ) as mock_mark:
            for p in self._patch_chain(service, []):
                stack.enter_context(p)
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=False,
            )
        assert result.success is False
        assert result.skipped is False
        assert result.step == "check_handle"
        mock_mark.assert_not_called()

    @pytest.mark.asyncio
    async def test_jjrqs_all_unparseable_alerts_no_dedup(self):
        """jjrqs=[""] / ["not-a-date"] 等全部无法解析 → 告警路径，不写防重 key

        防回归：之前 useful 过滤会把无法解析的日期一起丢掉，导致这种数据异常
        被误判为"全部已被覆盖"走静默 SKIP，吞掉服务端异常并错误写防重 key。
        """
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        from contextlib import ExitStack

        for bad_jjrqs in [[""], ["not-a-date"], ["", "still-bad"]]:
            with ExitStack() as stack, patch.object(
                service, "_mark_renewed_today", new=AsyncMock(return_value=None)
            ) as mock_mark:
                for p in self._patch_chain(service, bad_jjrqs):
                    stack.enter_context(p)
                result = await service.execute_renew(
                    plate_config,
                    status,
                    {"data": {}},
                    [self._make_account()],
                    today_covered=False,
                    tomorrow_covered=False,
                )
            assert result.success is False, f"bad_jjrqs={bad_jjrqs}"
            assert result.skipped is False, f"bad_jjrqs={bad_jjrqs}"
            assert result.step == "check_handle", f"bad_jjrqs={bad_jjrqs}"
            mock_mark.assert_not_called()

    @pytest.mark.asyncio
    async def test_jjrqs_only_past_dates_alerts_no_dedup(self):
        """jjrqs=[昨天] 只含过去日期 → 告警路径，不写防重 key

        防回归（Copilot review 发现）：旧 `_has_parseable_date` 只检查能否解析，
        ``[昨天]`` 能解析但实际不可办，会被错判为"全部已被覆盖"走静默 SKIP，
        吞掉服务端数据异常并错误写防重 key。修复后用 `_has_useful_candidate`，
        只认 ``>= today`` 的合法日期。
        """
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        from contextlib import ExitStack

        for bad_jjrqs in [
            [yesterday_str],
            [yesterday_str, "not-a-date"],
            [(date.today() - timedelta(days=7)).isoformat()],
        ]:
            with ExitStack() as stack, patch.object(
                service, "_mark_renewed_today", new=AsyncMock(return_value=None)
            ) as mock_mark:
                for p in self._patch_chain(service, bad_jjrqs):
                    stack.enter_context(p)
                result = await service.execute_renew(
                    plate_config,
                    status,
                    {"data": {}},
                    [self._make_account()],
                    today_covered=False,
                    tomorrow_covered=False,
                )
            assert result.success is False, f"bad_jjrqs={bad_jjrqs}"
            assert result.skipped is False, f"bad_jjrqs={bad_jjrqs}"
            assert result.step == "check_handle", f"bad_jjrqs={bad_jjrqs}"
            mock_mark.assert_not_called()

    @pytest.mark.asyncio
    async def test_jjrqs_mixed_parseable_and_unparseable(self):
        """jjrqs 混合合法/非法 + 合法日期已被覆盖 → 走 useful=[] 静默 SKIP（明日是 >= today 的有效候选）"""
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        from contextlib import ExitStack

        with ExitStack() as stack, patch.object(
            service, "_mark_renewed_today", new=AsyncMock(return_value=None)
        ) as mock_mark:
            # 一个非法 + 一个合法（明天）+ tomorrow_cov=True → useful=[]，但有可解析日期
            for p in self._patch_chain(service, ["not-a-date", tomorrow_str]):
                stack.enter_context(p)
            result = await service.execute_renew(
                plate_config,
                status,
                {"data": {}},
                [self._make_account()],
                today_covered=False,
                tomorrow_covered=True,
            )
        assert result.success is False
        assert result.skipped is True  # 静默 SKIP，因为合法日期被本地覆盖
        assert result.step == "useful_filter_skip"
        mock_mark.assert_awaited_once_with(plate_config.plate)


@pytest.mark.unit
class TestPushSkippedResult:
    """skipped=True 时不推送通知"""

    @pytest.mark.asyncio
    async def test_skipped_does_not_push(self):
        from jjz_alert.service.notification.unified_pusher import (
            unified_pusher as up_module,
        )

        service = AutoRenewService()
        plate_config = _make_plate_config()
        result = RenewResult(
            plate=plate_config.plate,
            success=False,
            message="服务端可办日期已被本地覆盖",
            step="useful_filter_skip",
            skipped=True,
        )
        with patch.object(
            up_module, "push", new=AsyncMock(return_value=None)
        ) as mock_push:
            await service.push_renew_result(plate_config, result)
        mock_push.assert_not_called()


@pytest.mark.unit
class TestExtractAccountInfo:
    """extract_account_info 辅助函数测试"""

    def test_empty_returns_none(self):
        assert AutoRenewService.extract_account_info(None) == (None, None)
        assert AutoRenewService.extract_account_info([]) == (None, None)

    def test_extracts_base_url_before_pro(self):
        from jjz_alert.config.config_models import JJZAccount, JJZConfig

        accounts = [
            JJZAccount(
                name="a",
                jjz=JJZConfig(
                    token="tok",
                    url="https://jjz.beijing.gov.cn:2443/pro/applyRecordController/stateList",
                ),
            )
        ]
        token, base = AutoRenewService.extract_account_info(accounts)
        assert token == "tok"
        assert base == "https://jjz.beijing.gov.cn:2443"

    def test_fallback_when_no_pro_in_url(self):
        from jjz_alert.config.config_models import JJZAccount, JJZConfig

        accounts = [
            JJZAccount(
                name="a", jjz=JJZConfig(token="tok", url="https://x.example.com/foo")
            )
        ]
        _, base = AutoRenewService.extract_account_info(accounts)
        assert base == "https://x.example.com"


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
                today_covered=False,
                tomorrow_covered=False,
            )

            mock_service.execute_renew.assert_awaited_once()
            # 防签名退化：today_covered/tomorrow_covered 必须经关键字透传，
            # 且值与上层传入一致（False/False），不是凭空被某处覆盖为默认
            kwargs = mock_service.execute_renew.await_args.kwargs
            assert kwargs.get("today_covered") is False
            assert kwargs.get("tomorrow_covered") is False
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
                today_covered=False,
                tomorrow_covered=False,
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
                    today_covered=False,
                    tomorrow_covered=False,
                )
                for i in range(4)
            ]
            await asyncio.gather(*tasks)

        assert max_concurrent == 1
        assert len(order) == 4

    @pytest.mark.asyncio
    async def test_negative_min_delay_clamped_to_zero(self):
        """min_delay < 0 时强制 clamp 为 0，避免 random.randint 崩溃"""
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()
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
                    plate=plate_config.plate, success=True, message="ok", step="done"
                )
            )
            mock_service.push_renew_result = AsyncMock(return_value=None)
            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                {"data": {}},
                accounts=None,
                decision=RenewDecision.RENEW_TODAY,
                min_delay=-10,
                max_delay=-5,
                today_covered=False,
                tomorrow_covered=False,
            )
            mock_service.execute_renew.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_renew_exception_falls_back_to_failure_result(self):
        """execute_renew 抛异常时仍要走 push_renew_result（步骤=exception）"""
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()
        captured = {}

        async def _fake_push(plate_cfg, result):
            captured["result"] = result

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(return_value=False),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock(side_effect=RuntimeError("boom"))
            mock_service.push_renew_result = AsyncMock(side_effect=_fake_push)
            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                {"data": {}},
                accounts=None,
                decision=RenewDecision.RENEW_TODAY,
                min_delay=0,
                max_delay=0,
                today_covered=False,
                tomorrow_covered=False,
            )
        assert captured["result"].success is False
        assert captured["result"].step == "exception"
        assert "boom" in captured["result"].message

    @pytest.mark.asyncio
    async def test_push_renew_result_failure_is_swallowed(self):
        """push_renew_result 抛异常不应让 schedule_renew 整体崩溃"""
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()

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
                    plate=plate_config.plate, success=True, message="ok", step="done"
                )
            )
            mock_service.push_renew_result = AsyncMock(
                side_effect=RuntimeError("push fail")
            )
            # 不应抛出
            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                {"data": {}},
                accounts=None,
                decision=RenewDecision.RENEW_TODAY,
                min_delay=0,
                max_delay=0,
                today_covered=False,
                tomorrow_covered=False,
            )

    @pytest.mark.asyncio
    async def test_has_renewed_today_logs_warning_on_redis_error(self, caplog):
        """_has_renewed_today 异常时记录 WARNING 而非静默吞，保证可观测"""
        from jjz_alert.config.redis import operations as ops_module
        from jjz_alert.service.jjz import renew_trigger
        import logging as _logging

        with patch.object(
            ops_module.redis_ops,
            "get",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            with caplog.at_level(_logging.WARNING):
                result = await renew_trigger._has_renewed_today("京A12345")
        assert result is False  # 不阻塞，但有日志可见
        assert any("读取防重复记录失败" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_cancel_during_lock_wait_does_not_leak_lock(self):
        """协程在等锁时被取消，全局锁不应泄漏。

        防回归：旧实现 `await asyncio.to_thread(LOCK.acquire)` 在协程取消时
        工作线程仍可能成功持锁，导致 try/finally 不可达、锁永久泄漏。
        改用 `acquire(blocking=False) + sleep` 轮询后，取消时锁未持有，
        其它协程可以正常获取。
        """
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()

        # 占住全局锁，让派发协程在 sleep 轮询里等待
        renew_trigger.RENEW_GLOBAL_LOCK.acquire()
        try:
            # 注意：故意不 mock `asyncio.sleep`——patch 是模块级替换，会同时拦
            # 截测试自己的 `await asyncio.sleep(...)`，导致协程没机会真正进入
            # acquire 轮询就被 cancel，测试空过。这里用真实 sleep（外层 delay=0
            # 跳过快，内层 acquire 轮询是真实 0.1s sleep）确保 cancel 落点在
            # acquire 阻塞期。
            with patch(
                "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
                new=AsyncMock(return_value=False),
            ):
                task = asyncio.create_task(
                    renew_trigger.schedule_renew(
                        plate_config,
                        jjz_status,
                        {"data": {}},
                        accounts=None,
                        decision=RenewDecision.RENEW_TODAY,
                        min_delay=0,
                        max_delay=0,
                        today_covered=False,
                        tomorrow_covered=False,
                    )
                )
                # 等真实 0.15s 让协程过完 outer delay（=0）进入 acquire 轮询
                # （> 一次 0.1s 轮询周期保证至少一次 acquire 失败 + 进入 sleep）
                await asyncio.sleep(0.15)
                # 此时协程在 acquire(blocking=False) + asyncio.sleep(0.1) 循环里
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            renew_trigger.RENEW_GLOBAL_LOCK.release()

        # 关键断言：取消后锁可立刻被外部获取（无泄漏）
        assert renew_trigger.RENEW_GLOBAL_LOCK.acquire(blocking=False) is True
        renew_trigger.RENEW_GLOBAL_LOCK.release()

    @pytest.mark.asyncio
    async def test_same_plate_concurrent_dedup_skips_second(self):
        """同车牌并发派发：第一个执行后写 dedup key，第二个抢到锁后通过
        dedup 检查跳过 execute_renew，不会重复提交。"""
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()
        execute_calls = []
        # 真实模拟"第一个成功后写 dedup → 第二个抢到锁后读取并跳过"的并发顺序：
        # 用一个 set 替代 Redis dedup key 的存在性。fake_execute_renew 写入；
        # fake_has_renewed 检查是否已写入（不靠 hits 计数器伪装）。
        marked_plates: set[str] = set()

        async def fake_execute_renew(p_config, *args, **kwargs):
            execute_calls.append(p_config.plate)
            # 模拟 production 内部的 _mark_renewed_today（execute_renew 写 Redis）
            marked_plates.add(p_config.plate)
            return RenewResult(
                plate=p_config.plate, success=True, message="ok", step="done"
            )

        async def fake_has_renewed(plate):
            return plate in marked_plates

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(side_effect=fake_has_renewed),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock(side_effect=fake_execute_renew)
            mock_service.push_renew_result = AsyncMock(return_value=None)

            await asyncio.gather(
                renew_trigger.schedule_renew(
                    plate_config,
                    jjz_status,
                    {"data": {}},
                    accounts=None,
                    decision=RenewDecision.RENEW_TOMORROW,
                    min_delay=0,
                    max_delay=0,
                    today_covered=False,
                    tomorrow_covered=False,
                ),
                renew_trigger.schedule_renew(
                    plate_config,
                    jjz_status,
                    {"data": {}},
                    accounts=None,
                    decision=RenewDecision.RENEW_TOMORROW,
                    min_delay=0,
                    max_delay=0,
                    today_covered=False,
                    tomorrow_covered=False,
                ),
            )

        # 关键断言：execute_renew 只被调用一次（第二个抢到锁后读到 marked → 跳过）
        assert len(execute_calls) == 1
        assert plate_config.plate in marked_plates

    @pytest.mark.asyncio
    async def test_push_runs_outside_global_lock(self):
        """push_renew_result 必须在锁外执行：慢推送不应阻塞下一个车牌的续办 API。

        防回归（Copilot review 发现）：把 push 放在锁内会让通知投递的网络延迟
        变成续办积压。验证方法：让 push 在执行时检查锁是否已被释放。
        """
        from jjz_alert.service.jjz import renew_trigger

        plate_config = _make_plate_config()
        jjz_status = _make_jjz_status()
        push_saw_lock_held: list[bool] = []

        async def fake_push(*args, **kwargs):
            # 在 push 期间检查全局锁是否已经被释放
            lock_held = not renew_trigger.RENEW_GLOBAL_LOCK.acquire(blocking=False)
            push_saw_lock_held.append(lock_held)
            if not lock_held:
                renew_trigger.RENEW_GLOBAL_LOCK.release()

        with patch(
            "jjz_alert.service.jjz.renew_trigger._has_renewed_today",
            new=AsyncMock(return_value=False),
        ), patch(
            "jjz_alert.service.jjz.renew_trigger.auto_renew_service"
        ) as mock_service:
            mock_service.execute_renew = AsyncMock(
                return_value=RenewResult(
                    plate=plate_config.plate,
                    success=True,
                    message="ok",
                    step="done",
                )
            )
            mock_service.push_renew_result = AsyncMock(side_effect=fake_push)

            await renew_trigger.schedule_renew(
                plate_config,
                jjz_status,
                {"data": {}},
                accounts=None,
                decision=RenewDecision.RENEW_TODAY,
                min_delay=0,
                max_delay=0,
                today_covered=False,
                tomorrow_covered=False,
            )

        assert push_saw_lock_held == [False], (
            "push_renew_result 必须在 RENEW_GLOBAL_LOCK 释放后调用，"
            "否则慢推送会阻塞下一个车牌的续办 API 调用"
        )


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
        expected_key = f"auto_renew:京A12345:{date.today().isoformat()}"
        with patch.object(
            ops_module.redis_ops, "get", new=AsyncMock(return_value="1")
        ) as mock_get:
            result = await service._has_renewed_today("京A12345")
        assert result is True
        mock_get.assert_awaited_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_auto_renew_service_mark_renewed_today_uses_redis_ops_set(self):
        from jjz_alert.config.redis import operations as ops_module

        service = AutoRenewService()
        expected_key = f"auto_renew:京A12345:{date.today().isoformat()}"
        with patch.object(
            ops_module.redis_ops, "set", new=AsyncMock(return_value=True)
        ) as mock_set:
            await service._mark_renewed_today("京A12345")
        mock_set.assert_awaited_once_with(expected_key, "1", ttl=86400)

    @pytest.mark.asyncio
    async def test_renew_trigger_has_renewed_today_uses_redis_ops_get(self):
        from jjz_alert.config.redis import operations as ops_module
        from jjz_alert.service.jjz import renew_trigger

        expected_key = f"auto_renew:京A12345:{date.today().isoformat()}"
        with patch.object(
            ops_module.redis_ops, "get", new=AsyncMock(return_value=None)
        ) as mock_get:
            result = await renew_trigger._has_renewed_today("京A12345")
        assert result is False
        mock_get.assert_awaited_once_with(expected_key)
