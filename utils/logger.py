"""日志初始化工具

- 读取 `config.yaml` 中的 `global.log.level` 字段，动态设置日志级别。
- 统一格式：`[LEVEL] YYYY-MM-DD HH:MM:SS 模块名: 消息`。

使用方法：只需在程序入口或模块顶部 `import utils.logger`，即可完成全局初始化。
"""
from __future__ import annotations

import logging

from config.config import load_yaml_config


def _get_level_from_config() -> int:
    """从配置文件读取日志等级，默认 INFO。"""
    cfg = load_yaml_config() or {}
    level_str: str = (
        cfg.get("global", {}).get("log", {}).get("level", "INFO")
    ).upper()
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
)
