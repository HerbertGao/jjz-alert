"""
仅续办工作流单元测试
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jjz_alert.config.config_models import (
    AppConfig,
    AutoRenewConfig,
    AutoRenewDestinationConfig,
    GlobalAutoRenewConfig,
    PlateConfig,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


def _make_config_with_renew_plate():
    config = AppConfig()
    config.global_config.auto_renew = GlobalAutoRenewConfig(
        min_delay_seconds=0, max_delay_seconds=0
    )
    config.plates = [
        PlateConfig(
            plate="京A12345",
            auto_renew=AutoRenewConfig(
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
            ),
        )
    ]
    return config


def _make_renew_status(plate="京A12345", **overrides):
    today = date.today()
    defaults = dict(
        plate=plate,
        status=JJZStatusEnum.VALID.value,
        valid_start=(today - timedelta(days=2)).isoformat(),
        valid_end=today.isoformat(),
        jjzzlmc="进京证（六环外）",
        vId="V001",
        hpzl="02",
        elzsfkb=True,
        sfyecbzxx=False,
    )
    defaults.update(overrides)
    return JJZStatus(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_dispatches_renew_today():
    from jjz_alert.service.jjz import renew_workflow

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status(
        valid_end=(date.today() - timedelta(days=1)).isoformat(),
        status=JJZStatusEnum.EXPIRED.value,
    )
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, False, False)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()

        mock_schedule.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_skips_when_no_renew_plates():
    from jjz_alert.service.jjz import renew_workflow

    config = AppConfig()  # 无 plates

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()

        mock_schedule.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_no_pushes_to_status_endpoints():
    """验证仅续办工作流不调用 push_jjz_status / push_jjz_reminder"""
    from jjz_alert.service.jjz import renew_workflow

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status(valid_end=date.today().isoformat())
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, False, False)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch(
        "jjz_alert.service.notification.push_helpers.push_jjz_status",
        new=AsyncMock(),
    ) as mock_push_status, patch(
        "jjz_alert.service.notification.push_helpers.push_jjz_reminder",
        new=AsyncMock(),
    ) as mock_push_reminder, patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ):
        await renew_workflow.run_renew_only_workflow()

        # 关键断言：兜底工作流不发状态/提醒推送
        mock_push_status.assert_not_called()
        mock_push_reminder.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_skips_plate_without_context():
    """ctx is None 时跳过派发，不调用 schedule_renew"""
    from jjz_alert.service.jjz import renew_workflow

    config = _make_config_with_renew_plate()

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, {})),  # 空 plate_renew_contexts
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()
        mock_schedule.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_handles_query_failure():
    """get_multiple_status_with_context 抛异常时优雅退出，不崩溃"""
    from jjz_alert.service.jjz import renew_workflow

    config = _make_config_with_renew_plate()

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(side_effect=RuntimeError("网络故障")),
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        # 不应抛出
        await renew_workflow.run_renew_only_workflow()
        mock_schedule.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_handles_decision_exception():
    """decide() 抛异常时跳过该车牌但不影响其他车牌"""
    from jjz_alert.service.jjz import renew_workflow

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status()
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, False, False)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch.object(
        renew_workflow, "decide", side_effect=RuntimeError("decide failed")
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        # 不应抛出
        await renew_workflow.run_renew_only_workflow()
        mock_schedule.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_passes_coverage_to_schedule():
    """RENEW_TOMORROW 派发时必须把 today_cov / tomorrow_cov 透传给 schedule_renew"""
    from jjz_alert.service.jjz import renew_workflow
    from jjz_alert.service.jjz.renew_decider import RenewDecision

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status(valid_end=date.today().isoformat())
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, True, False)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch.object(
        renew_workflow, "decide", return_value=RenewDecision.RENEW_TOMORROW
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()
        mock_schedule.assert_awaited_once()
        kwargs = mock_schedule.await_args.kwargs
        assert kwargs.get("today_covered") is True
        assert kwargs.get("tomorrow_covered") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_silent_skip_does_not_dispatch_or_alert():
    """SKIP 决策（如已有覆盖 + elzsfkb=False）：既不派发续办，也不发告警"""
    from jjz_alert.service.jjz import renew_workflow
    from jjz_alert.service.jjz.renew_decider import RenewDecision

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status(elzsfkb=False)
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, True, True)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch.object(
        renew_workflow, "decide", return_value=RenewDecision.SKIP
    ), patch(
        "jjz_alert.service.jjz.auto_renew_service.auto_renew_service.push_renew_result",
        new=AsyncMock(return_value=None),
    ) as mock_push, patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()
        mock_schedule.assert_not_called()
        mock_push.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_renew_only_workflow_not_available_pushes_alert():
    """决策为 NOT_AVAILABLE 时调用 push_renew_result 发不可办告警"""
    from jjz_alert.service.jjz import renew_workflow
    from jjz_alert.service.jjz.renew_decider import RenewDecision

    config = _make_config_with_renew_plate()
    renew_status = _make_renew_status(elzsfkb=False)
    fake_account = MagicMock()
    plate_renew_contexts = {
        "京A12345": ({"data": {}}, fake_account, renew_status, False, False)
    }

    with patch.object(
        renew_workflow.config_manager, "load_config", return_value=config
    ), patch.object(
        renew_workflow.JJZService,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=({}, plate_renew_contexts)),
    ), patch.object(
        renew_workflow, "decide", return_value=RenewDecision.NOT_AVAILABLE
    ), patch(
        "jjz_alert.service.jjz.auto_renew_service.auto_renew_service.push_renew_result",
        new=AsyncMock(return_value=None),
    ) as mock_push, patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule:
        await renew_workflow.run_renew_only_workflow()
        mock_push.assert_awaited_once()
        # 不再派发续办
        mock_schedule.assert_not_called()
        # 验证告警内容
        call_result = mock_push.await_args.args[1]
        assert call_result.success is False
        assert call_result.step == "eligibility_check"
