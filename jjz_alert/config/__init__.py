"""
JJZ-Alert 配置管理包
"""

#
from .config import (
    # 数据类
    AppConfig,
    GlobalConfig,
    RedisConfig,
    CacheConfig,
    APIConfig,
    LogConfig,
    AdminConfig,
    RemindConfig,
    HomeAssistantConfig,
    JJZAccount,
    PlateConfig,
    NotificationConfig,
    # 配置管理器
    ConfigManager,
    config_manager,
    # 接口函数
    get_redis_config,
    get_cache_config,
    get_homeassistant_config,
    get_plates,
    get_jjz_accounts,
    get_admin_notifications,
)

# 配置验证
from .validation import (
    ConfigValidator,
    ConfigValidationError,
    validate_config,
)

__all__ = [
    # 数据类
    "AppConfig",
    "GlobalConfig",
    "RedisConfig",
    "CacheConfig",
    "RemindConfig",
    "HomeAssistantConfig",
    "JJZAccount",
    "PlateConfig",
    "NotificationConfig",
    # 配置管理
    "ConfigManager",
    "config_manager",
    "get_redis_config",
    "get_cache_config",
    "get_homeassistant_config",
    "get_plates",
    "get_jjz_accounts",
    "get_admin_notifications",
    # 配置验证
    "ConfigValidator",
    "ConfigValidationError",
    "validate_config",
]
