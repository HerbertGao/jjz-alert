"""
续办决策器单元测试（基于覆盖缺口的新决策矩阵）
"""

import pytest

from jjz_alert.config.config_models import (
    AutoRenewConfig,
    AutoRenewDestinationConfig,
    PlateConfig,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.renew_decider import RenewDecision, decide


def _ar(enabled=True):
    return AutoRenewConfig(
        enabled=enabled,
        purpose="03",
        purpose_name="探亲访友",
        destination=AutoRenewDestinationConfig(
            area="朝阳区",
            area_code="010",
            address="测试地址",
            lng="116.4",
            lat="39.9",
        ),
    )


def _plate(ar=None):
    return PlateConfig(plate="京A12345", display_name="测试车", auto_renew=ar)


def _outer_status(*, elzsfkb=True, sfyecbzxx=False):
    """构造一条六环外车辆级字段；valid_end 等覆盖判断已移到外部信号，故此处不再设置"""
    return JJZStatus(
        plate="京A12345",
        status="valid",
        jjzzlmc="进京证（六环外）",
        vId="V001",
        hpzl="02",
        elzsfkb=elzsfkb,
        ylzsfkb=True,
        cllx="01",
        sfyecbzxx=sfyecbzxx,
        data_source="api",
    )


def _decide(plate_config, outer, today_cov, tomorrow_cov):
    return decide(
        plate_config=plate_config,
        outer_renew_status=outer,
        today_covered=today_cov,
        tomorrow_covered=tomorrow_cov,
    )


@pytest.mark.unit
class TestDecisionMatrix:
    """决策矩阵 9 条核心叶子（design.md D3）"""

    def test_today_y_tomorrow_y_elzsfkb_t_skip(self):
        """今天明天都覆盖 + elzsfkb=True → SKIP"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=True), True, True)
            == RenewDecision.SKIP
        )

    def test_today_y_tomorrow_y_elzsfkb_f_skip(self):
        """今天明天都覆盖 + elzsfkb=False → SKIP（覆盖优先于政策窗口）"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=False), True, True)
            == RenewDecision.SKIP
        )

    def test_today_y_tomorrow_n_elzsfkb_t_renew_tomorrow(self):
        """今日有覆盖、明日无覆盖、可办 → RENEW_TOMORROW"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=True), True, False)
            == RenewDecision.RENEW_TOMORROW
        )

    def test_today_y_tomorrow_n_elzsfkb_f_skip_policy_window(self):
        """今日有覆盖、明日无覆盖、不可办 → SKIP（政策窗口未开）"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=False), True, False)
            == RenewDecision.SKIP
        )

    def test_today_n_tomorrow_n_elzsfkb_t_renew_today(self):
        """今日断档、明日无覆盖、可办 → RENEW_TODAY"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=True), False, False)
            == RenewDecision.RENEW_TODAY
        )

    def test_today_n_tomorrow_y_elzsfkb_t_renew_today(self):
        """今日断档、明日有覆盖、可办 → RENEW_TODAY
        （决策器不替服务端预判明日已覆盖；后续 useful 过滤会处理）"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=True), False, True)
            == RenewDecision.RENEW_TODAY
        )

    def test_today_n_tomorrow_n_elzsfkb_f_not_available(self):
        """真断档：今日无覆盖、明日无覆盖、不可办 → NOT_AVAILABLE 告警"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=False), False, False)
            == RenewDecision.NOT_AVAILABLE
        )

    def test_today_n_tomorrow_y_elzsfkb_f_skip_has_fallback(self):
        """今日无覆盖、明日有兜底（如待生效六环内）、不可办 → SKIP 静默"""
        assert (
            _decide(_plate(_ar()), _outer_status(elzsfkb=False), False, True)
            == RenewDecision.SKIP
        )


@pytest.mark.unit
class TestPriorityAndEdges:
    """优先级与边界 5 条"""

    def test_pending_takes_priority(self):
        """sfyecbzxx=True 优先级最高，无视覆盖与 elzsfkb"""
        outer = _outer_status(elzsfkb=False, sfyecbzxx=True)
        assert _decide(_plate(_ar()), outer, False, False) == RenewDecision.PENDING
        assert _decide(_plate(_ar()), outer, True, True) == RenewDecision.PENDING

    def test_no_outer_record_skip(self):
        """无六环外记录 → SKIP（缺 vId 等续办字段）"""
        assert _decide(_plate(_ar()), None, False, False) == RenewDecision.SKIP
        assert _decide(_plate(_ar()), None, True, False) == RenewDecision.SKIP

    def test_auto_renew_disabled(self):
        assert (
            _decide(_plate(_ar(enabled=False)), _outer_status(), False, False)
            == RenewDecision.SKIP
        )

    def test_auto_renew_none(self):
        assert _decide(_plate(None), _outer_status(), False, False) == RenewDecision.SKIP

    def test_elzsfkb_none_treated_as_open(self):
        """elzsfkb=None（字段缺失）保守视为可办，与历史 _build_apply_request 默认值对齐"""
        outer = _outer_status(elzsfkb=None)
        # today 断档 + elzsfkb=None → 走可办路径返回 RENEW_TODAY
        assert _decide(_plate(_ar()), outer, False, False) == RenewDecision.RENEW_TODAY


@pytest.mark.unit
class TestKeywordOnlySignature:
    """决策器签名为 keyword-only，位置参数会立刻 TypeError"""

    def test_positional_args_rejected(self):
        with pytest.raises(TypeError):
            decide(_plate(_ar()), _outer_status(), False, False)  # type: ignore[misc]
