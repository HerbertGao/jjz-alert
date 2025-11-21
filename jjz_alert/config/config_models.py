"""
配置数据模型定义
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RedisConfig:
    """Redis配置"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    connection_pool_size: int = 10


@dataclass
class CacheConfig:
    """缓存策略配置"""

    push_history_ttl: int = 2592000  # 推送历史缓存30天


@dataclass
class APIConfig:
    """API服务配置"""

    enable: bool = True
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class RemindConfig:
    """定时提醒配置"""

    enable: bool = True
    times: List[str] = field(default_factory=lambda: ["08:00", "12:00", "18:00"])
    api: "APIConfig" = field(default_factory=APIConfig)


@dataclass
class LogConfig:
    """日志配置"""

    level: str = "INFO"


@dataclass
class AdminConfig:
    """管理员配置"""

    notifications: List["NotificationConfig"] = field(default_factory=list)


@dataclass
class HomeAssistantConfig:
    """Home Assistant配置"""

    enabled: bool = False
    # 二选一：使用 REST API 同步或 MQTT Discovery 推送
    # 可选值: 'rest' 或 'mqtt'（默认 rest 保持向后兼容）
    integration_mode: str = "rest"
    url: str = "http://homeassistant.local:8123"
    token: str = ""
    entity_prefix: str = "jjz_alert"

    # 同步配置
    sync_after_query: bool = True  # 查询后同步（推荐）

    # 错误处理
    retry_count: int = 3  # 同步失败重试次数
    timeout: int = 30  # 请求超时(秒)

    # 设备和实体创建策略
    create_device_per_plate: bool = True  # 为每个车牌创建独立设备
    device_manufacturer: str = "进京证提醒"  # 设备制造商
    device_model: str = "jjz_alert"  # 设备型号

    # MQTT Discovery（可选）
    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: str = "jjz_alert"
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_base_topic: str = "jjz_alert"
    mqtt_qos: int = 1
    mqtt_retain: bool = True


@dataclass
class MessageTemplateConfig:
    """消息模板配置"""

    valid_status: Optional[str] = None
    expired_status: Optional[str] = None
    pending_status: Optional[str] = None
    error_status: Optional[str] = None
    traffic_reminder_prefix: Optional[str] = None
    sycs_part: Optional[str] = None


@dataclass
class GlobalConfig:
    """全局配置"""

    log: LogConfig = field(default_factory=LogConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    remind: RemindConfig = field(default_factory=RemindConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    homeassistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    message_templates: MessageTemplateConfig = field(
        default_factory=MessageTemplateConfig
    )


@dataclass
class JJZConfig:
    """进京证配置"""

    token: str
    url: str


@dataclass
class JJZAccount:
    """进京证账户配置"""

    name: str
    jjz: JJZConfig


@dataclass
class NotificationConfig:
    """推送通知配置"""

    type: str  # "apprise"
    urls: List[str] = field(default_factory=list)
    server: Optional[str] = None


@dataclass
class PlateConfig:
    """车牌配置"""

    plate: str
    display_name: Optional[str] = None
    icon: Optional[str] = None
    notifications: List[NotificationConfig] = field(default_factory=list)


@dataclass
class AppConfig:
    """应用完整配置"""

    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    jjz_accounts: List[JJZAccount] = field(default_factory=list)
    plates: List[PlateConfig] = field(default_factory=list)

