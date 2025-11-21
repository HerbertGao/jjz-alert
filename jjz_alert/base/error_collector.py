"""
错误收集器
"""

from datetime import datetime
from typing import Any, Dict, List

from jjz_alert.base.error_exceptions import JJZError


class ErrorCollector:
    """错误收集器，用于监控和统计错误"""

    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.error_counts: Dict[str, int] = {}

    def record_error(self, error: Exception, context: str = ""):
        """记录错误"""
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "context": context,
        }

        if isinstance(error, JJZError):
            error_info.update(
                {"error_code": error.error_code, "details": error.details}
            )

        self.errors.append(error_info)

        # 统计错误数量
        error_type = error_info["type"]
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        # 限制错误记录数量，保留最近的100条
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]

    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误统计摘要"""
        return {
            "total_errors": len(self.errors),
            "error_counts": self.error_counts.copy(),
            "recent_errors": self.errors[-10:] if self.errors else [],
        }

    def clear_errors(self):
        """清除错误记录"""
        self.errors.clear()
        self.error_counts.clear()


# 全局错误收集器实例
error_collector = ErrorCollector()
