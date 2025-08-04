"""日志初始化工具

- 读取 `config.yaml` 中的 `global.log.level` 字段，动态设置日志级别。
- 统一格式：`[LEVEL] YYYY-MM-DD HH:MM:SS 模块名: 消息`。
- 为了与现有大量 `print()` 调用兼容，自动 monkey-patch `print()`，
  根据消息前缀 `[INFO] / [ERROR] / [WARN] / [DEBUG] / [CRITICAL]` 映射到
  对应的日志级别。无前缀时默认 INFO。

使用方法：仅需在程序入口（如 main.py）或其他模块最顶部 `import utils.logger`，
即可完成全局初始化。随后可以逐步将 `print()` 替换为 `logging.xxx`。
"""
from __future__ import annotations

import builtins
import logging

from config.config import load_yaml_config

# ---------------------------------------------------------------------------
# 读取配置中的日志级别
# ---------------------------------------------------------------------------

def _get_level_from_config() -> int:
    cfg = load_yaml_config()
    # 默认 INFO
    level_str = (
        (cfg or {}).get("global", {})
        .get("log", {})
        .get("level", "INFO")
        .upper()
    )
    return {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }.get(level_str, logging.INFO)


# ---------------------------------------------------------------------------
# 初始化 logging
# ---------------------------------------------------------------------------

_logging_level = _get_level_from_config()

logging.basicConfig(
    level=_logging_level,
    format="[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# monkey-patch print() -> logging
# ---------------------------------------------------------------------------

_original_print = builtins.print  # 备份，必要时仍可使用 original_print()

_prefix_to_level = {
    "[CRITICAL]": logging.CRITICAL,
    "[ERROR]": logging.ERROR,
    "[WARN]": logging.WARNING,
    "[WARNING]": logging.WARNING,
    "[INFO]": logging.INFO,
    "[DEBUG]": logging.DEBUG,
}


def _print_to_log(*args, **kwargs):  # type: ignore[override]
    """替代内置 print，将消息写入 logging。

    - 若检测到已声明的前缀，则按对应级别输出（并去掉前缀）；
    - 否则按 INFO 级别输出。
    """
    sep: str = kwargs.get("sep", " ")
    msg = sep.join(str(a) for a in args)

    level = logging.INFO
    for prefix, lvl in _prefix_to_level.items():
        if msg.startswith(prefix):
            msg = msg[len(prefix) :].lstrip()
            level = lvl
            break

    logging.log(level, msg)


# 替换内置 print，仅替换一次
if not getattr(builtins, "__logging_patch_done", False):
    builtins.print = _print_to_log  # type: ignore[assignment]
    builtins.__logging_patch_done = True  # type: ignore[attr-defined]
