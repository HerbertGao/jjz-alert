"""
进京证状态枚举定义

定义进京证各种状态的常量，避免使用魔法值
"""

from enum import Enum


class JJZStatusEnum(str, Enum):
    """进京证状态枚举"""
    
    # 有效状态
    VALID = "valid"          # 审核通过且在有效期内
    
    # 过期状态
    EXPIRED = "expired"      # 已过有效期
    
    # 审核中状态
    PENDING = "pending"      # 审核中/待审核
    
    # 无效状态
    INVALID = "invalid"      # 审核被拒绝或其他无效状态
    
    # 错误状态
    ERROR = "error"          # 查询错误或系统异常
    
    # 未知状态
    UNKNOWN = "unknown"      # 未知状态，用于初始化
    
    def __str__(self) -> str:
        """返回状态值字符串"""
        return self.value
    
    @classmethod
    def from_string(cls, status_str: str) -> 'JJZStatusEnum':
        """从字符串创建状态枚举"""
        if not status_str:
            return cls.UNKNOWN
            
        status_str = status_str.lower().strip()
        
        # 尝试直接匹配
        for status in cls:
            if status.value == status_str:
                return status
        
        # 兼容性映射
        status_mapping = {
            'approved': cls.VALID,
            'active': cls.VALID,
            'effective': cls.VALID,
            'reviewing': cls.PENDING,
            'auditing': cls.PENDING,
            'rejected': cls.INVALID,
            'denied': cls.INVALID,
            'failed': cls.ERROR,
            'exception': cls.ERROR,
        }
        
        return status_mapping.get(status_str, cls.UNKNOWN)
    
    @property
    def is_valid(self) -> bool:
        """判断是否为有效状态"""
        return self == self.VALID
    
    @property
    def is_expired(self) -> bool:
        """判断是否为过期状态"""
        return self == self.EXPIRED
    
    @property
    def is_pending(self) -> bool:
        """判断是否为审核中状态"""
        return self == self.PENDING
    
    @property
    def is_invalid(self) -> bool:
        """判断是否为无效状态"""
        return self == self.INVALID
    
    @property
    def is_error(self) -> bool:
        """判断是否为错误状态"""
        return self == self.ERROR
    
    @property
    def is_actionable(self) -> bool:
        """判断是否为可操作状态（有效或即将过期）"""
        return self in (self.VALID, self.EXPIRED)
    
    @property
    def needs_attention(self) -> bool:
        """判断是否需要关注（过期、错误、无效）"""
        return self in (self.EXPIRED, self.ERROR, self.INVALID)
    
    @property
    def description(self) -> str:
        """获取状态描述"""
        descriptions = {
            self.VALID: "有效",
            self.EXPIRED: "已过期", 
            self.PENDING: "审核中",
            self.INVALID: "无效",
            self.ERROR: "错误",
            self.UNKNOWN: "未知"
        }
        return descriptions.get(self, "未知")


# 导出常用的状态常量，方便使用
class JJZStatus:
    """JJZ状态常量类，提供便捷的状态常量访问"""
    
    VALID = JJZStatusEnum.VALID
    EXPIRED = JJZStatusEnum.EXPIRED
    PENDING = JJZStatusEnum.PENDING
    INVALID = JJZStatusEnum.INVALID
    ERROR = JJZStatusEnum.ERROR
    UNKNOWN = JJZStatusEnum.UNKNOWN
    
    @classmethod
    def all_statuses(cls) -> list:
        """获取所有状态值"""
        return [status.value for status in JJZStatusEnum]
    
    @classmethod
    def valid_statuses(cls) -> list:
        """获取有效的状态值（排除错误和未知）"""
        return [
            cls.VALID.value,
            cls.EXPIRED.value,
            cls.PENDING.value,
            cls.INVALID.value
        ]