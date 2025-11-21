"""
进京证状态枚举定义
"""

from enum import Enum


class JJZStatusEnum(str, Enum):
    """进京证状态枚举"""

    VALID = "valid"
    EXPIRED = "expired"
    PENDING = "pending"
    INVALID = "invalid"
    ERROR = "error"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, status_str: str) -> "JJZStatusEnum":
        if not status_str:
            return cls.UNKNOWN

        status_str = status_str.lower().strip()

        for status in cls:
            if status.value == status_str:
                return status

        status_mapping = {
            "approved": cls.VALID,
            "active": cls.VALID,
            "effective": cls.VALID,
            "reviewing": cls.PENDING,
            "auditing": cls.PENDING,
            "rejected": cls.INVALID,
            "denied": cls.INVALID,
            "failed": cls.ERROR,
            "exception": cls.ERROR,
        }

        return status_mapping.get(status_str, cls.UNKNOWN)

    @property
    def is_valid(self) -> bool:
        return self == self.VALID

    @property
    def is_expired(self) -> bool:
        return self == self.EXPIRED

    @property
    def is_pending(self) -> bool:
        return self == self.PENDING

    @property
    def is_invalid(self) -> bool:
        return self == self.INVALID

    @property
    def is_error(self) -> bool:
        return self == self.ERROR

    @property
    def is_actionable(self) -> bool:
        return self in (self.VALID, self.EXPIRED)

    @property
    def needs_attention(self) -> bool:
        return self in (self.EXPIRED, self.ERROR, self.INVALID)

    @property
    def description(self) -> str:
        descriptions = {
            self.VALID: "有效",
            self.EXPIRED: "已过期",
            self.PENDING: "审核中",
            self.INVALID: "无效",
            self.ERROR: "错误",
            self.UNKNOWN: "未知",
        }
        return descriptions.get(self, "未知")


__all__ = ["JJZStatusEnum"]
