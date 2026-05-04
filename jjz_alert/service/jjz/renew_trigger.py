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
    except Exception as e:
        # 不让异常阻断派发流程，但要可见——历史上 ImportError
        # 静默吞掉造成防重失效长期未被发现
        logger.warning("[renew] 读取防重复记录失败 plate=%s: %s", plate, e)
        return False


async def schedule_renew(
    plate_config: PlateConfig,
    jjz_status: JJZStatus,
    response_data: Dict[str, Any],
    accounts: Optional[List[Any]],
    decision: RenewDecision,
    min_delay: int = 30,
    max_delay: int = 180,
    *,
    today_covered: bool,
    tomorrow_covered: bool,
) -> None:
    """
    异步派发一辆车的续办：随机延迟 → 抢全局锁 → 二次校验 → 执行续办 → 推送结果。

    today_covered / tomorrow_covered 透传给 execute_renew，用于 checkHandle 后的
    useful 过滤（服务端给的日期已被本地覆盖时静默 SKIP）。

    Note:
        `today_covered` / `tomorrow_covered` 必传（无默认值），与 `decide()` 的
        keyword-only 强制理由一致：遗漏会静默走"无覆盖"路径，潜在错误难以发现，
        因此让 Python 在调用时立刻 TypeError 而非默认 False 静默错路径。
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

    # 用 threading.Lock 跨 loop 串行。
    # 不能用 `await asyncio.to_thread(LOCK.acquire)`：协程被取消时工作线程
    # 仍会成功拿锁但 try/finally 不可达，导致锁永久泄漏、后续续办全部死锁。
    # 改用非阻塞 acquire + sleep 轮询：取消时锁要么没拿到（自然不泄漏），
    # 要么已经持有并进入 try/finally。
    while not RENEW_GLOBAL_LOCK.acquire(blocking=False):
        await asyncio.sleep(0.1)

    # 锁的目的是续办 API 调用串行错峰反爬。push 通知走外部网络（Bark/Server酱
    # /Webhook 等），与 API 错峰无关——必须在锁外执行，否则慢推送会让下一个
    # 车牌的续办积压。dedup_skip 时直接 return（finally 释放锁），不进入推送。
    result: Optional[RenewResult] = None
    try:
        if await _has_renewed_today(plate):
            logger.info("[renew] skipped plate=%s reason=dedup_key_exists", plate)
            return

        try:
            result = await auto_renew_service.execute_renew(
                plate_config,
                jjz_status,
                response_data,
                accounts,
                today_covered=today_covered,
                tomorrow_covered=tomorrow_covered,
            )
        except Exception as exc:
            logger.error("[renew] execute_renew exception plate=%s: %s", plate, exc)
            result = RenewResult(
                plate=plate,
                success=False,
                message=f"续办异常: {exc}",
                step="exception",
            )
    finally:
        RENEW_GLOBAL_LOCK.release()

    # 锁外推送：通知延迟不阻塞下一个车牌进入 execute_renew
    if result is None:  # 仅 dedup_skip 路径
        return
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


__all__ = ["RENEW_GLOBAL_LOCK", "schedule_renew"]
