"""
JJZ-Alert 配置管理包

提供v1.x和v2.0配置管理支持
"""

# v2.0 新功能导入
from .config_v2 import (
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

    # v2.0 接口函数
    get_redis_config,
    get_cache_config,
    get_homeassistant_config,
    get_plates_v2,
    get_jjz_accounts_v2,
    get_admin_notifications,
)

# 配置验证
from .validation import (
    ConfigValidator,
    ConfigValidationError,
    validate_config,
)

__all__ = [
    # v2.0 数据类
    'AppConfig',
    'GlobalConfig',
    'RedisConfig',
    'CacheConfig',
    'RemindConfig',
    'HomeAssistantConfig',
    'JJZAccount',
    'PlateConfig',
    'NotificationConfig',

    # v2.0 配置管理
    'ConfigManager',
    'config_manager',
    'get_redis_config',
    'get_cache_config',
    'get_homeassistant_config',
    'get_plates_v2',
    'get_jjz_accounts_v2',
    'get_admin_notifications',

    # 配置验证
    'ConfigValidator',
    'ConfigValidationError',
    'validate_config',
]
