"""日志初始化工具

- 读取 `config.yaml` 中的 `global.log.level` 字段，动态设置日志级别。
- 支持结构化日志记录，便于监控和分析。
- 统一格式：`[LEVEL] YYYY-MM-DD HH:MM:SS 模块名: 消息`。

使用方法：只需在程序入口或模块顶部 `import utils.logger`，即可完成全局初始化。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from config.config_v2 import config_manager


class LogCategory(Enum):
    """日志分类"""
    SYSTEM = "system"  # 系统级日志
    BUSINESS = "business"  # 业务逻辑日志
    PERFORMANCE = "performance"  # 性能相关日志
    SECURITY = "security"  # 安全相关日志
    API = "api"  # API调用日志
    ERROR = "error"  # 错误日志


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, logger_name: str):
        self.logger = logging.getLogger(logger_name)

    def log_structured(
            self,
            level: int,
            message: str,
            category: LogCategory = LogCategory.SYSTEM,
            extra_data: Optional[Dict[str, Any]] = None,
            user_id: Optional[str] = None,
            request_id: Optional[str] = None,
            plate_number: Optional[str] = None,
            operation: Optional[str] = None
    ):
        """记录结构化日志"""

        structured_data = {
            "timestamp": datetime.now().isoformat(),
            "category": category.value,
            "message": message,
            "level": logging.getLevelName(level)
        }

        # 添加可选字段
        if user_id:
            structured_data["user_id"] = user_id
        if request_id:
            structured_data["request_id"] = request_id
        if plate_number:
            structured_data["plate_number"] = plate_number
        if operation:
            structured_data["operation"] = operation
        if extra_data:
            structured_data["extra"] = extra_data

        # 记录日志
        self.logger.log(level, f"STRUCTURED: {json.dumps(structured_data, ensure_ascii=False)}")

    def log_api_call(
            self,
            method: str,
            endpoint: str,
            status_code: int,
            response_time_ms: float,
            user_id: Optional[str] = None,
            request_id: Optional[str] = None,
            extra_data: Optional[Dict[str, Any]] = None
    ):
        """记录API调用日志"""
        api_data = {
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "response_time_ms": response_time_ms
        }

        if extra_data:
            api_data.update(extra_data)

        level = logging.INFO if 200 <= status_code < 400 else logging.WARNING

        self.log_structured(
            level=level,
            message=f"API调用: {method} {endpoint} -> {status_code} ({response_time_ms}ms)",
            category=LogCategory.API,
            extra_data=api_data,
            user_id=user_id,
            request_id=request_id,
            operation="api_call"
        )

    def log_business_operation(
            self,
            operation: str,
            plate_number: str,
            success: bool,
            duration_ms: Optional[float] = None,
            extra_data: Optional[Dict[str, Any]] = None
    ):
        """记录业务操作日志"""
        business_data = {
            "success": success,
            "operation": operation
        }

        if duration_ms is not None:
            business_data["duration_ms"] = duration_ms
        if extra_data:
            business_data.update(extra_data)

        level = logging.INFO if success else logging.WARNING
        message = f"业务操作{'成功' if success else '失败'}: {operation}"

        self.log_structured(
            level=level,
            message=message,
            category=LogCategory.BUSINESS,
            extra_data=business_data,
            plate_number=plate_number,
            operation=operation
        )

    def log_performance(
            self,
            operation: str,
            duration_ms: float,
            success: bool = True,
            extra_data: Optional[Dict[str, Any]] = None
    ):
        """记录性能日志"""
        perf_data = {
            "duration_ms": duration_ms,
            "success": success
        }

        if extra_data:
            perf_data.update(extra_data)

        # 根据性能阈值确定日志级别
        if duration_ms > 5000:  # 超过5秒
            level = logging.WARNING
        elif duration_ms > 1000:  # 超过1秒
            level = logging.INFO
        else:
            level = logging.DEBUG

        self.log_structured(
            level=level,
            message=f"性能监控: {operation} 耗时 {duration_ms}ms",
            category=LogCategory.PERFORMANCE,
            extra_data=perf_data,
            operation=operation
        )

    def log_security_event(
            self,
            event_type: str,
            severity: str,
            description: str,
            user_id: Optional[str] = None,
            source_ip: Optional[str] = None,
            extra_data: Optional[Dict[str, Any]] = None
    ):
        """记录安全事件日志"""
        security_data = {
            "event_type": event_type,
            "severity": severity,
            "description": description
        }

        if source_ip:
            security_data["source_ip"] = source_ip
        if extra_data:
            security_data.update(extra_data)

        level = logging.ERROR if severity in ["high", "critical"] else logging.WARNING

        self.log_structured(
            level=level,
            message=f"安全事件: {event_type} - {description}",
            category=LogCategory.SECURITY,
            extra_data=security_data,
            user_id=user_id,
            operation="security_event"
        )


def get_structured_logger(name: str) -> StructuredLogger:
    """获取结构化日志记录器"""
    return StructuredLogger(name)


def _get_level_from_config() -> int:
    """从配置文件读取日志等级，默认 INFO。"""
    try:
        config = config_manager.load_config()
        level_str: str = config.global_config.log.level.upper()
    except Exception:
        level_str = "INFO"
    return {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }.get(level_str, logging.INFO)


logging.basicConfig(
    level=_get_level_from_config(),
    format="[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
