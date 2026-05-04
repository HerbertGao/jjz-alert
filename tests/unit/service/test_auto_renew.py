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
                plate_config, status, {"data": {}}, [self._make_account()]
            )
        assert result.success is True
        assert result.step == "dedup_skip"

    @pytest.mark.asyncio
    async def test_no_account_returns_init_error(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
        result = await service.execute_renew(
            plate_config, status, {"data": {}}, accounts=None
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
                plate_config, status, {"data": {}}, [self._make_account()]
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
                plate_config, status, {"data": {}}, [self._make_account()]
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
                plate_config, status, {"data": {}}, [self._make_account()]
            )
        assert result.success is False
        assert result.step == "check_handle"

    @pytest.mark.asyncio
    async def test_full_success_path(self):
        service = AutoRenewService()
        plate_config = _make_plate_config()
        status = _make_jjz_status()
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
            return_value={"jjrqs": ["2026-04-01"]},
        ), patch.object(
            service, "_check_road_info", return_value=True
        ), patch.object(
            service, "_submit_apply", return_value=True
        ):
            result = await service.execute_renew(
                plate_config, status, {"data": {}}, [self._make_account()]
            )
        assert result.success is True
        assert result.step == "done"
        assert result.jjrq == "2026-04-01"
        # 成功后必须写入当日防重 key
        mock_mark.assert_awaited_once_with(plate_config.plate)


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
