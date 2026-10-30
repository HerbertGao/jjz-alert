"""
jjz_alert 顶级包

用于统一暴露 config、service、utils 等子模块，避免在项目根目录散落多个包。
"""

# 单一版本来源。开发版 PR 只改这一行；API / Home Assistant 从这里导入。
__version__ = "2.6.0"

__all__ = [
    "__version__",
    "config",
    "service",
    "utils",
]
