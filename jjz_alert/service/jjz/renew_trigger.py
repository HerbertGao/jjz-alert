"""
自动续办派发器

负责：
1. 拟人化随机延迟（min_delay_seconds ~ max_delay_seconds）
2. 全局锁串行执行 API 链（多车牌错峰，跨 loop/线程安全）
3. 复用现有 Redis 当日防重 key
4. 调用 execute_renew + push_renew_result
"""

import asyncio
import logging
import random
import threading
from datetime import date
from typing import Any, Dict, List, Optional

from jjz_alert.config.config_models import PlateConfig
from jjz_alert.service.jjz.auto_renew_service import (
    RenewResult,
    auto_renew_service,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.renew_decider import RenewDecision

logger = logging.getLogger(__name__)

# 跨事件循环/线程安全的全局锁
# （asyncio.Semaphore 仅在单 loop 内安全，BlockingScheduler 每次触发都新建 loop，
#  REST API 在独立线程也用自己 loop，必须用 threading.Lock + to_thread 抢锁）
RENEW_GLOBAL_LOCK = threading.Lock()


async def _has_renewed_today(plate: str) -> bool:
    try:
        from jjz_alert.config.redis.operations import redis_ops

        key = f"auto_renew:{plate}:{date.today().isoformat()}"
        return (await redis_ops.get(key)) is not None
    except Exception:
        return False


async def schedule_renew(
    plate_config: PlateConfig,
    jjz_status: JJZStatus,
    response_data: Dict[str, Any],
    accounts: Optional[List[Any]],
    decision: RenewDecision,
    min_delay: int = 30,
    max_delay: int = 180,
) -> None:
    """
    异步派发一辆车的续办：随机延迟 → 抢全局锁 → 二次校验 → 执行续办 → 推送结果。
    """
    plate = plate_config.plate

    if min_delay < 0:
        min_delay = 0
    if max_delay < min_delay:
        max_delay = min_delay
    delay = random.randint(min_delay, max_delay)

    logger.info(
        "[renew] dispatched plate=%s decision=%s delay=%ss",
        plate,
        decision.value,
        delay,
    )

    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logger.info("[renew] cancelled during sleep plate=%s", plate)
        raise

    # 用 threading.Lock 跨 loop 串行；await to_thread 让出协程并阻塞拿锁
    await asyncio.to_thread(RENEW_GLOBAL_LOCK.acquire)
    try:
        if await _has_renewed_today(plate):
            logger.info("[renew] skipped plate=%s reason=dedup_key_exists", plate)
            return

        try:
            result = await auto_renew_service.execute_renew(
                plate_config, jjz_status, response_data, accounts
            )
        except Exception as exc:
            logger.error("[renew] execute_renew exception plate=%s: %s", plate, exc)
            result = RenewResult(
                plate=plate,
                success=False,
                message=f"续办异常: {exc}",
                step="exception",
            )

        try:
            await auto_renew_service.push_renew_result(plate_config, result)
        except Exception as exc:
            logger.error("[renew] push_renew_result failed plate=%s: %s", plate, exc)

        logger.info(
            "[renew] completed plate=%s success=%s step=%s",
            plate,
            result.success,
            result.step,
        )
    finally:
        RENEW_GLOBAL_LOCK.release()


__all__ = ["RENEW_GLOBAL_LOCK", "schedule_renew"]
