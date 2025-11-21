"""
jjz_alert 顶级包

用于统一暴露 config、service、utils 等子模块，避免在项目根目录散落多个包。
"""

__all__ = [
    "config",
    "service",
    "utils",
]
