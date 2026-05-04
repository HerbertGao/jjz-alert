"""
仅续办工作流：批量查询 stateList → 决策 → 派发，不发任何状态/限行推送。

仅供"用户禁用 remind 但启用 auto_renew"场景下的兜底 cron 使用。
remind 启用时由 push_workflow 完成同样的决策+派发链路（同时含状态推送）。
"""

import asyncio
import logging

from jjz_alert.config.config import config_manager
from jjz_alert.service.cache.cache_service import CacheService
from jjz_alert.service.jjz.jjz_service import JJZService
from jjz_alert.service.jjz.renew_decider import RenewDecision, decide

logger = logging.getLogger(__name__)


async def run_renew_only_workflow() -> None:
    """
    仅执行续办决策与派发，不推送状态/限行通知。
    用于 remind 关闭但 auto_renew 启用时的凌晨兜底 cron。
    """
    app_config = config_manager.load_config()
    renew_plates = [
        p for p in app_config.plates if p.auto_renew and p.auto_renew.enabled
    ]
    if not renew_plates:
        logger.debug("[renew_only] 无启用自动续办的车牌，跳过")
        return

    plate_numbers = [p.plate for p in renew_plates]
    cache_service = CacheService()
    jjz_service = JJZService(cache_service)

    try:
        all_jjz_results, plate_renew_contexts = (
            await jjz_service.get_multiple_status_with_context(plate_numbers)
        )
    except Exception as exc:
        logger.error(f"[renew_only] 批量查询进京证状态失败: {exc}")
        return

    ar_global = app_config.global_config.auto_renew
    dispatched_tasks: list = []

    for plate_config in renew_plates:
        plate = plate_config.plate
        ctx = plate_renew_contexts.get(plate)
        if ctx is None:
            logger.debug(f"[renew_only] 车牌 {plate} 缺少续办上下文，跳过")
            continue
        (
            ctx_response_data,
            ctx_account,
            ctx_renew_status,
            ctx_today_cov,
            ctx_tomorrow_cov,
        ) = ctx

        try:
            decision = decide(
                plate_config=plate_config,
                outer_renew_status=ctx_renew_status,
                today_covered=ctx_today_cov,
                tomorrow_covered=ctx_tomorrow_cov,
            )
        except Exception as exc:
            logger.warning(f"[renew_only] 车牌 {plate} 决策异常: {exc}")
            continue

        logger.info(
            "[renew_only] decision plate=%s -> %s "
            "today_cov=%s tomorrow_cov=%s elzsfkb=%s sfyecbzxx=%s",
            plate,
            decision.value,
            ctx_today_cov,
            ctx_tomorrow_cov,
            ctx_renew_status.elzsfkb,
            ctx_renew_status.sfyecbzxx,
        )

        if decision in (RenewDecision.RENEW_TODAY, RenewDecision.RENEW_TOMORROW):
            from jjz_alert.service.jjz.renew_trigger import schedule_renew

            task = asyncio.create_task(
                schedule_renew(
                    plate_config,
                    ctx_renew_status,
                    ctx_response_data,
                    [ctx_account],
                    decision,
                    min_delay=ar_global.min_delay_seconds,
                    max_delay=ar_global.max_delay_seconds,
                    today_covered=ctx_today_cov,
                    tomorrow_covered=ctx_tomorrow_cov,
                )
            )
            dispatched_tasks.append(task)
            logger.info(f"[renew_only] dispatched plate={plate}")
        elif decision == RenewDecision.NOT_AVAILABLE:
            try:
                from jjz_alert.service.jjz.auto_renew_service import (
                    auto_renew_service,
                    RenewResult,
                )

                await auto_renew_service.push_renew_result(
                    plate_config,
                    RenewResult(
                        plate=plate,
                        success=False,
                        message="六环外进京证当前不可办理",
                        step="eligibility_check",
                    ),
                )
            except Exception as exc:
                logger.error(f"[renew_only] 车牌 {plate} NOT_AVAILABLE 通知失败: {exc}")

    # 仅等待本工作流派发的任务，避免在共享 loop 场景下误等其他任务
    if dispatched_tasks:
        await asyncio.gather(*dispatched_tasks, return_exceptions=True)


__all__ = ["run_renew_only_workflow"]
