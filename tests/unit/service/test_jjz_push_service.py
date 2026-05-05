"""
JJZPushService 主路径关键 wiring 测试

聚焦 process_single_plate 在 plate_renew_contexts 含"仅有六环内 renew_status"
时也能正确进入决策器并派发续办协程；这是 spec auto-renew "续办触发判断" 的
remind 主路径，run_renew_only_workflow 是其凌晨兜底镜像。
"""

import datetime
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


def _make_config():
    config = AppConfig()
    config.global_config.auto_renew = GlobalAutoRenewConfig(
        min_delay_seconds=0, max_delay_seconds=0
    )
    config.jjz_accounts = [MagicMock(name="account-stub")]
    config.plates = [
        PlateConfig(
            plate="京A12345",
            display_name="京A12345",
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


def _make_inner_only_status():
    """仅有六环内 record 的 JJZStatus，已失效；vehicle 层字段满足续办条件"""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return JJZStatus(
        plate="京A12345",
        status=JJZStatusEnum.EXPIRED.value,
        valid_start=yesterday,
        valid_end=yesterday,
        jjzzlmc="进京证(六环内)",
        blztmc="审核通过(已失效)",
        vId="V001",
        hpzl="02",
        cllx="K33",
        elzsfkb=True,
        ylzsfkb=True,
        sfyecbzxx=False,
        sycs="7",
        data_source="api",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_push_workflow_dispatches_renew_for_inner_only_plate():
    """process_single_plate（remind 主路径）必须把"仅有六环内 ctx + RENEW_TODAY"
    决策派发到 schedule_renew，不得因 renew_status.jjzzlmc 不含"六环外"而跳过。
    """
    from jjz_alert.service.notification import jjz_push_service as pm

    config = _make_config()
    inner_status = _make_inner_only_status()
    fake_account = MagicMock(name="account-stub")
    plate_renew_contexts = {
        "京A12345": (
            {"data": {}},
            fake_account,
            inner_status,
            False,  # today_covered
            False,  # tomorrow_covered
            date.today(),
        )
    }
    all_jjz_results = {"京A12345": inner_status}

    # mock datetime 让走当日推送分支（hour=10），避免次日推送复杂逻辑
    fixed_now = datetime.datetime(2025, 8, 15, 10, 0, 0)

    service = pm.JJZPushService()

    with patch.object(
        pm.config_manager, "load_config", return_value=config
    ), patch.object(
        service.cache_service, "delete_jjz_data", new=AsyncMock(return_value=True)
    ), patch.object(
        service.jjz_service,
        "get_multiple_status_with_context",
        new=AsyncMock(return_value=(all_jjz_results, plate_renew_contexts)),
    ), patch.object(
        service.traffic_service,
        "get_smart_traffic_rules",
        new=AsyncMock(return_value={"target_rule": None}),
    ), patch.object(
        service.traffic_service,
        "check_multiple_plates",
        new=AsyncMock(return_value={}),
    ), patch.object(
        pm.batch_pusher, "get_batch_urls_for_plate", return_value=[]
    ), patch(
        "jjz_alert.service.notification.jjz_push_service.push_jjz_status",
        new=AsyncMock(return_value={"success": True, "success_count": 1}),
    ), patch(
        "jjz_alert.service.notification.jjz_push_service.push_jjz_reminder",
        new=AsyncMock(return_value={"success": True}),
    ), patch(
        "jjz_alert.service.jjz.renew_trigger.schedule_renew",
        new=AsyncMock(),
    ) as mock_schedule, patch(
        "jjz_alert.service.notification.jjz_push_service.datetime"
    ) as mock_datetime:
        # datetime 被整体替换，需要保留模块原行为
        mock_datetime.datetime.now.return_value = fixed_now
        mock_datetime.date.today.return_value = fixed_now.date()
        mock_datetime.timedelta = datetime.timedelta

        result = await service.execute_push_workflow(
            plate_numbers=None, force_refresh=False, include_ha_sync=False
        )

        # schedule_renew 必须被派发（核心断言）
        mock_schedule.assert_awaited_once()
        # 派发参数中 renew_status 是仅有六环内的那条
        call_kwargs = mock_schedule.await_args.kwargs
        call_args = mock_schedule.await_args.args
        # schedule_renew 既支持位置又支持 kwargs，统一从 args+kwargs 提取
        # 签名: (plate_config, jjz_status, response_data, accounts, decision, ...)
        passed_status = (
            call_args[1] if len(call_args) >= 2 else call_kwargs.get("jjz_status")
        )
        assert passed_status is inner_status

        # 工作流结果反映派发成功
        assert result["total_plates"] == 1
