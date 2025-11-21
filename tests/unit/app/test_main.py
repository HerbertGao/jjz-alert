import logging
import sys
from dataclasses import dataclass
from types import ModuleType

import pytest

from main import main as run_main


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
