import logging

import pytest

from jjz_alert.base import http


class DummyResponse:
    def __init__(self, marker):
        self.marker = marker


def _patch_session(monkeypatch, outcomes):
    """Patch Session class in http module to yield predefined outcomes."""

    class DummySession:
        call_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def get(self, *args, **kwargs):
            return self._consume("get", *args, **kwargs)

        def post(self, *args, **kwargs):
            return self._consume("post", *args, **kwargs)

        def _consume(self, action, *args, **kwargs):
            DummySession.call_count += 1
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(http, "Session", DummySession)
    monkeypatch.setattr(http, "time", type("T", (), {"sleep": staticmethod(lambda *a: None)}))
    return DummySession


def test_http_get_success(monkeypatch):
    expected = DummyResponse("ok")
    _patch_session(monkeypatch, [expected])

    result = http.http_get("https://example.com", headers={"X": "1"})

    assert result is expected


def test_http_get_retries_then_succeeds(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    outcomes = [
        RuntimeError("boom1"),
        RuntimeError("boom2"),
        DummyResponse("good"),
    ]
    DummySession = _patch_session(monkeypatch, outcomes)

    result = http.http_get("https://example.com/api", max_retries=3)

    assert result.marker == "good"
    assert DummySession.call_count == 3
    assert "重试 2/3" in caplog.text


def test_http_post_eventually_fails(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    outcomes = [
        RuntimeError("fail-1"),
        RuntimeError("fail-2"),
    ]
    _patch_session(monkeypatch, outcomes)

    with pytest.raises(RuntimeError):
        http.http_post("https://example.com/post", max_retries=2)

    assert "HTTP POST请求最终失败" in caplog.text


def test_http_get_eventually_fails(monkeypatch, caplog):
    """测试HTTP GET所有重试都失败"""
    caplog.set_level(logging.ERROR)
    outcomes = [
        RuntimeError("fail-1"),
        RuntimeError("fail-2"),
        RuntimeError("fail-3"),
    ]
    _patch_session(monkeypatch, outcomes)

    with pytest.raises(RuntimeError):
        http.http_get("https://example.com/get", max_retries=3)

    assert "HTTP GET请求最终失败" in caplog.text


def test_http_post_success(monkeypatch):
    """测试HTTP POST成功返回"""
    expected = DummyResponse("post_ok")
    _patch_session(monkeypatch, [expected])

    result = http.http_post(
        "https://example.com/post",
        headers={"Content-Type": "application/json"},
        json_data={"key": "value"},
    )

    assert result is expected

