"""
自动续办决策器

基于 PlateConfig + JJZStatus 决定续办分支：
  SKIP / RENEW_TODAY / RENEW_TOMORROW / PENDING / NOT_AVAILABLE

优先级：PENDING > NOT_AVAILABLE > RENEW_* > SKIP
"""

from datetime import date, timedelta
from enum import Enum

from jjz_alert.config.config_models import PlateConfig
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


class RenewDecision(str, Enum):
    SKIP = "skip"
    RENEW_TODAY = "renew_today"
    RENEW_TOMORROW = "renew_tomorrow"
    PENDING = "pending"
    NOT_AVAILABLE = "not_available"


def decide(plate_config: PlateConfig, jjz_status: JJZStatus) -> RenewDecision:
    """
    决定一辆车在当前查询时刻的续办分支。

    判断口径：以 jjz_status.valid_end 与本地 today/tomorrow 比较；
    sfyecbzxx / elzsfkb 二次校验由 vehicle 级字段提供。
    """
    ar = plate_config.auto_renew
    if not ar or not ar.enabled:
        return RenewDecision.SKIP

    # 续办仅支持六环外（execute_renew 固定 jjzzl="02"）；
    # 当车牌最新记录不是六环外（jjzzlmc 缺失或不含"六环外"）时跳过
    if not jjz_status.jjzzlmc or "六环外" not in jjz_status.jjzzlmc:
        return RenewDecision.SKIP

    if jjz_status.sfyecbzxx:
        return RenewDecision.PENDING

    if jjz_status.elzsfkb is False:
        return RenewDecision.NOT_AVAILABLE

    today = date.today()
    tomorrow = today + timedelta(days=1)

    valid_end_str = jjz_status.valid_end
    valid_end_date = None
    if valid_end_str:
        try:
            valid_end_date = date.fromisoformat(valid_end_str)
        except (ValueError, TypeError):
            valid_end_date = None

    # INVALID 表示"无任何进京证记录"或解析失败，缺少 vId 等续办字段，
    # 即使派发也会在 execute_renew 失败；与用户设计共识"不考虑无续办上下文"一致，
    # 显式跳过避免无意义派发。
    if jjz_status.status == JJZStatusEnum.EXPIRED.value:
        return RenewDecision.RENEW_TODAY

    if valid_end_date is None:
        return RenewDecision.SKIP

    if valid_end_date < today:
        return RenewDecision.RENEW_TODAY

    if valid_end_date < tomorrow:
        return RenewDecision.RENEW_TOMORROW

    return RenewDecision.SKIP


__all__ = ["RenewDecision", "decide"]
