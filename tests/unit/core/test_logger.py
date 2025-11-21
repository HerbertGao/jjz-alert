import json
import logging
from types import SimpleNamespace

import pytest

from jjz_alert.base import logger as base_logger


class DummyLogConfig(SimpleNamespace):
    level: str = "INFO"


def _build_config(level: str):
    return SimpleNamespace(
        global_config=SimpleNamespace(log=SimpleNamespace(level=level))
    )


def test_log_structured_outputs_json(caplog):
    caplog.set_level(logging.INFO)
    structured_logger = base_logger.get_structured_logger("jjz-test")

    structured_logger.log_structured(
        level=logging.INFO,
        message="hello",
        category=base_logger.LogCategory.API,
        user_id="u1",
        extra_data={"foo": "bar"},
    )

    record = caplog.records[-1]
    assert "STRUCTURED:" in record.message
    payload = json.loads(record.message.split("STRUCTURED: ")[1])
    assert payload["category"] == "api"
    assert payload["extra"]["foo"] == "bar"


def test_log_api_call_sets_warning_for_error(caplog):
    caplog.set_level(logging.WARNING)
    structured_logger = base_logger.get_structured_logger("jjz-test-api")

    structured_logger.log_api_call(
        method="GET",
        endpoint="/jjz",
        status_code=500,
        response_time_ms=123.4,
        extra_data={"retries": 1},
    )

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert "API调用" in record.message


def test_log_performance_thresholds(caplog):
    caplog.set_level(logging.DEBUG)
    structured_logger = base_logger.get_structured_logger("jjz-perf")

    structured_logger.log_performance("fast-op", duration_ms=200)
    structured_logger.log_performance("slow-op", duration_ms=2000)
    structured_logger.log_performance("very-slow-op", duration_ms=6000)

    levels = [record.levelno for record in caplog.records[-3:]]
    assert levels == [logging.DEBUG, logging.INFO, logging.WARNING]


def test_log_security_event_sets_error(caplog):
    caplog.set_level(logging.ERROR)
    structured_logger = base_logger.get_structured_logger("jjz-sec")

    structured_logger.log_security_event(
        event_type="intrusion",
        severity="high",
        description="unexpected access",
        user_id="42",
    )

    assert caplog.records[-1].levelno == logging.ERROR
    assert "安全事件" in caplog.records[-1].message


def test_get_level_from_config_reads_custom(monkeypatch):
    dummy_config = _build_config("DEBUG")
    monkeypatch.setattr(base_logger.config_manager, "load_config", lambda: dummy_config)

    level = base_logger._get_level_from_config()

    assert level == logging.DEBUG


def test_get_level_from_config_fallback_on_error(monkeypatch):
    def raise_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(base_logger.config_manager, "load_config", raise_error)

    level = base_logger._get_level_from_config()

    assert level == logging.INFO


def test_log_structured_with_request_id(caplog):
    """测试log_structured包含request_id字段"""
    caplog.set_level(logging.INFO)
    structured_logger = base_logger.get_structured_logger("jjz-test")

    structured_logger.log_structured(
        level=logging.INFO,
        message="test message",
        request_id="req-12345",
    )

    record = caplog.records[-1]
    payload = json.loads(record.message.split("STRUCTURED: ")[1])
    assert payload["request_id"] == "req-12345"


def test_log_performance_with_extra_data(caplog):
    """测试log_performance包含extra_data"""
    caplog.set_level(
        logging.DEBUG
    )  # 设置为DEBUG级别，因为duration_ms < 1000时使用DEBUG
    structured_logger = base_logger.get_structured_logger("jjz-perf")

    structured_logger.log_performance(
        operation="test-op",
        duration_ms=100.0,
        extra_data={"key": "value", "count": 42},
    )

    record = caplog.records[-1]
    payload = json.loads(record.message.split("STRUCTURED: ")[1])
    assert payload["extra"]["key"] == "value"
    assert payload["extra"]["count"] == 42


def test_log_security_event_with_source_ip(caplog):
    """测试log_security_event包含source_ip字段"""
    caplog.set_level(logging.WARNING)
    structured_logger = base_logger.get_structured_logger("jjz-sec")

    structured_logger.log_security_event(
        event_type="intrusion",
        severity="medium",
        description="test event",
        source_ip="192.168.1.100",
    )

    record = caplog.records[-1]
    payload = json.loads(record.message.split("STRUCTURED: ")[1])
    assert payload["extra"]["source_ip"] == "192.168.1.100"


def test_log_security_event_with_extra_data(caplog):
    """测试log_security_event包含extra_data"""
    caplog.set_level(logging.WARNING)
    structured_logger = base_logger.get_structured_logger("jjz-sec")

    structured_logger.log_security_event(
        event_type="intrusion",
        severity="medium",
        description="test event",
        extra_data={"attack_type": "sql_injection", "blocked": True},
    )

    record = caplog.records[-1]
    payload = json.loads(record.message.split("STRUCTURED: ")[1])
    assert payload["extra"]["attack_type"] == "sql_injection"
    assert payload["extra"]["blocked"] is True
