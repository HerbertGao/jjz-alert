"""
自动续办决策器（基于覆盖缺口的口径）

输入：
  - plate_config：车牌配置（含 auto_renew 块）
  - outer_renew_status：六环外最新记录（仅用于读取车辆级字段 elzsfkb / sfyecbzxx）
  - today_covered / tomorrow_covered：全车牌（六环内 ∪ 六环外）的覆盖布尔，
    由 JJZService 在批量查询时基于 blztmc + 有效期算出

输出五种结果：SKIP / RENEW_TODAY / RENEW_TOMORROW / PENDING / NOT_AVAILABLE

互斥规则下：六环内与六环外不会同时生效；服务端在六环内活跃时把 elzsfkb 置为 False。
"已有覆盖 + elzsfkb=False" 不再误判为告警，按本决策矩阵静默 SKIP。
"""

from enum import Enum

from jjz_alert.config.config_models import PlateConfig
from jjz_alert.service.jjz.jjz_status import JJZStatus


class RenewDecision(str, Enum):
    SKIP = "skip"
    RENEW_TODAY = "renew_today"
    RENEW_TOMORROW = "renew_tomorrow"
    PENDING = "pending"
    NOT_AVAILABLE = "not_available"


def decide(
    *,
    plate_config: PlateConfig,
    outer_renew_status: JJZStatus | None,
    today_covered: bool,
    tomorrow_covered: bool,
) -> RenewDecision:
    """决定一辆车在当前查询时刻的续办分支。

    决策树：
        auto_renew 未启用                       → SKIP
        无六环外历史记录                        → SKIP（缺 vId 等续办字段）
        sfyecbzxx == True                       → PENDING（已有待审，最高优先级）
        today_covered == True：
            tomorrow_covered == True            → SKIP（双覆盖，无需操作）
            tomorrow_covered == False:
                elzsfkb == True                 → RENEW_TOMORROW（明日缺，今日派发）
                elzsfkb == False                → SKIP（政策窗口未开，等下一轮）
        today_covered == False:
            elzsfkb == True                     → RENEW_TODAY（今日断档，立即派发；
                                                    服务端实际给的日期由 useful 过滤精判）
            elzsfkb == False:
                tomorrow_covered == True        → SKIP（已有明日兜底）
                tomorrow_covered == False       → NOT_AVAILABLE（真断档+不可办，告警）
    """
    ar = plate_config.auto_renew
    if not ar or not ar.enabled:
        return RenewDecision.SKIP

    if outer_renew_status is None:
        return RenewDecision.SKIP

    if outer_renew_status.sfyecbzxx:
        return RenewDecision.PENDING

    elzsfkb_open = (
        outer_renew_status.elzsfkb is not False
    )  # None 当作 True，与旧行为对齐

    if today_covered:
        if tomorrow_covered:
            return RenewDecision.SKIP
        if elzsfkb_open:
            return RenewDecision.RENEW_TOMORROW
        return RenewDecision.SKIP  # 政策窗口未开

    # today_covered is False
    if elzsfkb_open:
        return RenewDecision.RENEW_TODAY
    if tomorrow_covered:
        return RenewDecision.SKIP  # 已有明日兜底
    return RenewDecision.NOT_AVAILABLE


__all__ = ["RenewDecision", "decide"]
