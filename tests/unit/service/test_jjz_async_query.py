"""异步进京证查询不得占用 API 事件循环。"""

import asyncio
import importlib
from unittest.mock import Mock

import pytest

from jjz_alert.service.jjz.jjz_service import JJZService

service_module = importlib.import_module("jjz_alert.service.jjz.jjz_service")


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_query_account_state_uses_async_http(monkeypatch):
    calls = []

    async def fake_post(url, headers=None, json_data=None, verify=False, max_retries=3):
        calls.append(url)
        await asyncio.sleep(0)
        return _Response({"data": {"bzclxx": []}})

    def sync_post(*args, **kwargs):
        raise AssertionError("同步 http_post 不应在事件循环上执行")

    monkeypatch.setattr(service_module, "http_post_async", fake_post)
    monkeypatch.setattr(service_module, "http_post", sync_post)

    service = JJZService(cache_service=Mock())
    result = await service._query_account_state(
        "https://example.test/state", "upstream-token"
    )

    assert result == {"data": {"bzclxx": []}}
    assert calls == ["https://example.test/state"]


@pytest.mark.asyncio
async def test_query_error_schedules_admin_notice_on_running_loop(monkeypatch):
    async def fake_post(url, headers=None, json_data=None, verify=False, max_retries=3):
        await asyncio.sleep(0)
        raise RuntimeError("TLS connect error: handshake")

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return None

    monkeypatch.setattr(service_module, "http_post_async", fake_post)
    monkeypatch.setattr(service_module.asyncio, "create_task", fake_create_task)

    service = JJZService(cache_service=Mock())
    result = await service._query_account_state(
        "https://example.test/state", "upstream-token"
    )

    assert result["error"].startswith("TLS/SSL连接错误")
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_replaced_sync_checker_is_still_used():
    service = JJZService(cache_service=Mock())
    service.check_jjz_status = Mock(return_value={"ok": True})

    result = await service._query_account_state("https://example.test/state", "token")

    assert result == {"ok": True}
    service.check_jjz_status.assert_called_once_with(
        "https://example.test/state", "token"
    )
