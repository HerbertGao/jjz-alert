import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from main import main as run_main, schedule_jobs


@dataclass
class DummyPushService:
    """简单的推送服务桩对象，用于注入 main 测试结果"""

    result: dict

    async def push_all_plates(self):
        return self.result


def _mock_dependencies(monkeypatch, push_result):
    """统一的依赖注入，保证 main 运行时不访问真实资源"""

    # 初始化模板函数改为空操作，避免依赖真实配置
    monkeypatch.setattr(
        "jjz_alert.base.message_templates.initialize_templates_from_config",
        lambda config_manager: None,
    )

    # 构造一个轻量级模块，供 main 内的延迟导入使用
    dummy_module = ModuleType("jjz_alert.service.notification.jjz_push_service")
    dummy_module.jjz_push_service = DummyPushService(push_result)
    monkeypatch.setitem(
        sys.modules, "jjz_alert.service.notification.jjz_push_service", dummy_module
    )


@pytest.mark.asyncio
async def test_main_logs_ha_sync_success(monkeypatch, caplog):
    """当 HA 同步成功时，应记录成功日志"""
    caplog.set_level(logging.INFO)

    push_result = {
        "success": True,
        "success_plates": 2,
        "failed_plates": 0,
        "total_plates": 2,
        "errors": [],
        "ha_sync_result": {"success_plates": 2, "total_plates": 2, "errors": []},
    }

    _mock_dependencies(monkeypatch, push_result)

    await run_main()

    ha_messages = [record.message for record in caplog.records]
    assert any("Home Assistant同步完成" in msg for msg in ha_messages)


@pytest.mark.asyncio
async def test_main_logs_ha_sync_failure(monkeypatch, caplog):
    """当 HA 同步失败时，应记录警告日志"""
    caplog.set_level(logging.INFO)

    push_result = {
        "success": True,
        "success_plates": 0,
        "failed_plates": 0,
        "total_plates": 1,
        "errors": [],
        "ha_sync_result": {
            "success_plates": 0,
            "total_plates": 1,
            "errors": ["ha unavailable"],
        },
    }

    _mock_dependencies(monkeypatch, push_result)

    await run_main()

    ha_messages = [record.message for record in caplog.records]
    assert any("Home Assistant同步失败" in msg for msg in ha_messages)


# ---------- schedule_jobs 凌晨兜底 cron 注册行为测试 ----------


def _build_app_config(remind_enable, remind_times, auto_renew_enabled):
    """构造测试用 AppConfig，覆盖 remind 与 auto_renew 各种组合"""
    from jjz_alert.config.config_models import (
        AppConfig,
        AutoRenewConfig,
        GlobalConfig,
        PlateConfig,
        RemindConfig,
    )

    remind = RemindConfig(enable=remind_enable, times=list(remind_times))
    global_config = GlobalConfig(remind=remind)
    auto_renew = (
        AutoRenewConfig(enabled=True, purpose="test")
        if auto_renew_enabled
        else None
    )
    plate = PlateConfig(plate="京A12345", auto_renew=auto_renew)
    return AppConfig(global_config=global_config, plates=[plate])


def _patch_schedule_jobs(monkeypatch, app_config):
    """注入 schedule_jobs 所需的桩对象，返回收集到的 add_job 调用列表"""
    # main.schedule_jobs 内通过 `from jjz_alert.config.config import config_manager`
    # 延迟导入，因此需直接 patch 源模块上的属性
    from jjz_alert.config import config as _cfg_module

    fake_cm = MagicMock()
    fake_cm.load_config.return_value = app_config
    monkeypatch.setattr(_cfg_module, "config_manager", fake_cm)

    add_job_calls = []

    class FakeScheduler:
        def __init__(self, *args, **kwargs):
            pass

        def add_job(self, func, trigger, **kwargs):
            add_job_calls.append({"trigger": trigger, "kwargs": kwargs})

        def start(self):
            # 测试中不真正阻塞
            return None

    monkeypatch.setattr("main.BlockingScheduler", FakeScheduler)
    # 屏蔽信号注册（避免在非主线程下抛出 ValueError）
    monkeypatch.setattr("main.signal.signal", lambda *a, **kw: None)
    return add_job_calls


def _has_midnight_fallback(add_job_calls):
    """判断是否注册了 00:30 兜底 cron"""
    for call in add_job_calls:
        trigger = call["trigger"]
        fields = {f.name: str(f) for f in trigger.fields}
        if fields.get("hour") == "0" and fields.get("minute") == "30":
            return True
    return False


def test_midnight_fallback_when_remind_disabled(monkeypatch):
    """remind 关闭 + auto_renew 开启 -> 注册 00:30 兜底"""
    app_config = _build_app_config(
        remind_enable=False, remind_times=[], auto_renew_enabled=True
    )
    add_job_calls = _patch_schedule_jobs(monkeypatch, app_config)
    schedule_jobs()
    assert _has_midnight_fallback(add_job_calls)


def test_midnight_fallback_when_remind_lacks_post_midnight(monkeypatch):
    """remind 开启但无凌晨时刻 + auto_renew 开启 -> 注册 00:30 兜底"""
    app_config = _build_app_config(
        remind_enable=True,
        remind_times=["07:00", "23:55"],
        auto_renew_enabled=True,
    )
    add_job_calls = _patch_schedule_jobs(monkeypatch, app_config)
    schedule_jobs()
    assert _has_midnight_fallback(add_job_calls)


def test_no_fallback_when_remind_has_post_midnight(monkeypatch):
    """remind 已含凌晨时刻 (00:30) + auto_renew 开启 -> 不重复注册兜底"""
    app_config = _build_app_config(
        remind_enable=True,
        remind_times=["00:30", "12:00"],
        auto_renew_enabled=True,
    )
    add_job_calls = _patch_schedule_jobs(monkeypatch, app_config)
    schedule_jobs()
    # 应只注册 remind cron 中已存在的 00:30，而非额外的兜底任务
    midnight_jobs = [
        c
        for c in add_job_calls
        if {f.name: str(f) for f in c["trigger"].fields}.get("hour") == "0"
        and {f.name: str(f) for f in c["trigger"].fields}.get("minute") == "30"
    ]
    assert len(midnight_jobs) == 1


def test_no_fallback_when_no_auto_renew(monkeypatch):
    """auto_renew 关闭 -> 无论 remind 状态都不注册兜底"""
    # remind 关闭场景
    app_config = _build_app_config(
        remind_enable=False, remind_times=[], auto_renew_enabled=False
    )
    add_job_calls = _patch_schedule_jobs(monkeypatch, app_config)
    schedule_jobs()
    assert not _has_midnight_fallback(add_job_calls)

    # remind 开启且 times 不含凌晨场景
    app_config2 = _build_app_config(
        remind_enable=True,
        remind_times=["07:00", "23:55"],
        auto_renew_enabled=False,
    )
    add_job_calls2 = _patch_schedule_jobs(monkeypatch, app_config2)
    schedule_jobs()
    assert not _has_midnight_fallback(add_job_calls2)
