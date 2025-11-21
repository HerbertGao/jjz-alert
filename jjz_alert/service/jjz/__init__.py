"""
进京证服务模块

提供进京证相关的业务逻辑处理
"""

from .jjz_service import JJZService, jjz_service
from .jjz_status import JJZStatus

__all__ = ["JJZService", "JJZStatus", "jjz_service"]
