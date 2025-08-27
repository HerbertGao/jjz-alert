"""
JJZ-Alert v2.0 配置管理模块

支持新的配置文件结构，同时保持向后兼容
支持环境变量覆盖配置
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


# =============================================================================
# 配置数据类定义
# =============================================================================


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
    api: APIConfig = field(default_factory=APIConfig)


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
    device_manufacturer: str = "JJZ Alert"  # 设备制造商
    device_model: str = "Beijing Vehicle"  # 设备型号

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
    message_templates: MessageTemplateConfig = field(default_factory=MessageTemplateConfig)


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


# =============================================================================
# 配置加载和解析
# =============================================================================


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self._config: Optional[AppConfig] = None
        self._raw_config: Optional[Dict] = None

    def load_config(self, force_reload: bool = False) -> AppConfig:
        """加载配置文件"""
        if self._config is None or force_reload:
            self._load_from_file()
        return self._config

    def reload_config(self) -> AppConfig:
        """强制重新加载配置文件"""
        return self.load_config(force_reload=True)

    def _load_from_file(self):
        """从文件加载配置"""
        try:
            if not Path(self.config_file).exists():
                logging.warning(f"配置文件 {self.config_file} 不存在，使用默认配置")
                self._config = AppConfig()
                return

            with open(self.config_file, "r", encoding="utf-8") as f:
                self._raw_config = yaml.safe_load(f) or {}

            self._config = self._parse_config(self._raw_config)
            logging.info(f"成功加载配置文件: {self.config_file}")

        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            self._config = AppConfig()

    def _parse_config(self, raw_config: Dict) -> AppConfig:
        """解析配置数据"""
        # 检测配置文件格式
        if self._is_v1_config(raw_config):
            logging.info("检测到v1.x配置格式，进行兼容性转换")
            return self._convert_v1_to_v2(raw_config)
        else:
            logging.info("使用v2.0配置格式")
            return self._parse_v2_config(raw_config)

    def _is_v1_config(self, config: Dict) -> bool:
        """检测是否为v1.x配置格式"""
        return "plate_configs" in config

    def _convert_v1_to_v2(self, v1_config: Dict) -> AppConfig:
        """将v1.x配置转换为v2.0格式"""
        config = AppConfig()

        # 转换全局配置
        if "global" in v1_config:
            global_data = v1_config["global"]

            # 定时提醒配置（含 API 配置）
            if "remind" in global_data:
                remind_data = global_data["remind"]
                # 基础 remind
                config.global_config.remind = RemindConfig(
                    enable=remind_data.get("enable", True),
                    times=remind_data.get("times", ["08:00", "12:00", "18:00"]),
                )
                # 嵌套的 API 配置（host/port/enable）
                if isinstance(remind_data.get("api"), dict):
                    api_data = remind_data.get("api", {})
                    config.global_config.remind.api = APIConfig(
                        enable=api_data.get("enable", True),
                        host=api_data.get("host", config.global_config.remind.api.host),
                        port=api_data.get("port", config.global_config.remind.api.port),
                    )

            # 日志配置
            if "log" in global_data:
                log_data = global_data["log"]
                config.global_config.log = LogConfig(
                    level=log_data.get("level", "INFO")
                )

            # 管理员配置

        # 转换进京证账户配置
        if "jjz_accounts" in v1_config:
            for account_data in v1_config["jjz_accounts"]:
                if "jjz" in account_data:
                    jjz_data = account_data["jjz"]
                    jjz_config = JJZConfig(token=jjz_data["token"], url=jjz_data["url"])
                    account = JJZAccount(
                        name=account_data.get("name", "未知账户"), jjz=jjz_config
                    )
                    config.jjz_accounts.append(account)

        # 转换车牌配置
        if "plate_configs" in v1_config:
            for plate_data in v1_config["plate_configs"]:
                plate_config = PlateConfig(
                    plate=plate_data["plate"],
                    display_name=plate_data["plate"],  # v1中没有display_name，使用plate
                    icon=plate_data.get("plate_icon"),  # v1中的plate_icon
                )

                config.plates.append(plate_config)

        # 应用环境变量覆盖
        self._apply_env_overrides(config)

        return config

    def _parse_v2_config(self, v2_config: Dict) -> AppConfig:
        """解析v2.0配置格式"""
        config = AppConfig()

        # 解析全局配置
        if "global" in v2_config:
            global_data = v2_config["global"]

            # 定时提醒配置（含 API 配置）
            if "remind" in global_data:
                remind_data = global_data["remind"]
                # 基础 remind
                config.global_config.remind = RemindConfig(
                    enable=remind_data.get("enable", True),
                    times=remind_data.get("times", ["08:00", "12:00", "18:00"]),
                )
                # 嵌套的 API 配置（host/port/enable）
                if isinstance(remind_data.get("api"), dict):
                    api_data = remind_data.get("api", {})
                    config.global_config.remind.api = APIConfig(
                        enable=api_data.get("enable", config.global_config.remind.api.enable),
                        host=api_data.get("host", config.global_config.remind.api.host),
                        port=api_data.get("port", config.global_config.remind.api.port),
                    )

            # Redis配置
            if "redis" in global_data:
                redis_data = global_data["redis"]
                config.global_config.redis = RedisConfig(
                    host=redis_data.get("host", "localhost"),
                    port=redis_data.get("port", 6379),
                    db=redis_data.get("db", 0),
                    password=redis_data.get("password"),
                    connection_pool_size=redis_data.get("connection_pool_size", 10),
                )

            # 缓存配置
            if "cache" in global_data:
                cache_data = global_data["cache"]
                config.global_config.cache = CacheConfig(
                    push_history_ttl=cache_data.get("push_history_ttl", 2592000)
                )

            # Home Assistant配置
            if "homeassistant" in global_data:
                ha_data = global_data["homeassistant"]

                # 读取 REST 关键参数使用 rest_*，并兼容旧字段 url/token 作为回退
                rest_url = ha_data.get("rest_url", ha_data.get("url", "http://homeassistant.local:8123"))
                rest_token = ha_data.get("rest_token", ha_data.get("token", ""))

                # 其余 REST 参数统一使用内置默认值（不推荐用户修改）
                config.global_config.homeassistant = HomeAssistantConfig(
                    enabled=ha_data.get("enabled", False),
                    integration_mode=ha_data.get("integration_mode", "rest"),
                    url=rest_url,
                    token=rest_token,
                    entity_prefix="jjz_alert",

                    # 同步配置（默认值）
                    sync_after_query=True,

                    # 错误处理（默认值）
                    retry_count=3,
                    timeout=30,

                    # 设备创建策略（默认值）
                    create_device_per_plate=True,
                    device_manufacturer="JJZ Alert",
                    device_model="Beijing Vehicle",

                    # MQTT Discovery（可选）
                    mqtt_enabled=ha_data.get("mqtt_enabled", False),
                    mqtt_host=ha_data.get("mqtt_host", "localhost"),
                    mqtt_port=ha_data.get("mqtt_port", 1883),
                    mqtt_username=ha_data.get("mqtt_username"),
                    mqtt_password=ha_data.get("mqtt_password"),
                    # 以下为 MQTT 默认值，不在示例中暴露
                    mqtt_client_id="jjz_alert",
                    mqtt_discovery_prefix="homeassistant",
                    mqtt_base_topic="jjz_alert",
                    mqtt_qos=1,
                    mqtt_retain=True,
                )

            # 消息模板配置
            if "message_templates" in global_data:
                template_data = global_data["message_templates"]
                config.global_config.message_templates = MessageTemplateConfig(
                    valid_status=template_data.get("valid_status"),
                    expired_status=template_data.get("expired_status"),
                    pending_status=template_data.get("pending_status"),
                    error_status=template_data.get("error_status"),
                    traffic_reminder_prefix=template_data.get("traffic_reminder_prefix"),
                    sycs_part=template_data.get("sycs_part"),
                )

            # 管理员配置
            if "admin" in global_data and "notifications" in global_data["admin"]:
                for notif_data in global_data["admin"]["notifications"]:
                    notification = self._parse_notification_config(notif_data)
                    config.global_config.admin.notifications.append(notification)

            # 日志配置
            if "log" in global_data:
                log_data = global_data["log"]
                config.global_config.log = LogConfig(
                    level=log_data.get("level", "INFO")
                )
            elif "log_level" in global_data:  # 兼容旧的平级格式
                config.global_config.log = LogConfig(
                    level=global_data.get("log_level", "INFO")
                )

        # 解析进京证账户
        if "jjz_accounts" in v2_config:
            for account_data in v2_config["jjz_accounts"]:
                if "jjz" in account_data:
                    jjz_data = account_data["jjz"]
                    jjz_config = JJZConfig(token=jjz_data["token"], url=jjz_data["url"])
                    account = JJZAccount(
                        name=account_data.get("name", "未知账户"), jjz=jjz_config
                    )
                    config.jjz_accounts.append(account)

        # 解析车牌配置
        if "plates" in v2_config:
            for plate_data in v2_config["plates"]:
                plate_config = PlateConfig(
                    plate=plate_data["plate"],
                    display_name=plate_data.get("display_name"),
                    icon=plate_data.get("icon"),  # 添加图标字段解析
                )

                # 解析推送配置
                if "notifications" in plate_data:
                    for notif_data in plate_data["notifications"]:
                        notification = self._parse_notification_config(notif_data)
                        plate_config.notifications.append(notification)

                config.plates.append(plate_config)

        # 应用环境变量覆盖
        self._apply_env_overrides(config)

        return config

    def _parse_notification_config(self, notif_data: Dict) -> NotificationConfig:
        """解析推送配置"""
        notification = NotificationConfig(type=notif_data["type"])

        if notif_data["type"] == "apprise":
            # Apprise配置
            notification.urls = notif_data.get("urls", [])

        return notification

    def _apply_env_overrides(self, config: AppConfig):
        """应用环境变量覆盖"""
        # Redis配置覆盖
        if os.getenv("REDIS_HOST"):
            config.global_config.redis.host = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            config.global_config.redis.port = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_DB"):
            config.global_config.redis.db = int(os.getenv("REDIS_DB"))
        if os.getenv("REDIS_PASSWORD"):
            config.global_config.redis.password = os.getenv("REDIS_PASSWORD")

        # 日志级别覆盖
        if os.getenv("LOG_LEVEL"):
            config.global_config.log_level = os.getenv("LOG_LEVEL").upper()


# =============================================================================
# 全局配置管理器实例
# =============================================================================

# 全局配置管理器实例
config_manager = ConfigManager()


# =============================================================================
# v2.0 新接口函数
# =============================================================================


def get_redis_config() -> RedisConfig:
    """获取Redis配置"""
    config = config_manager.load_config()
    return config.global_config.redis


def get_cache_config() -> CacheConfig:
    """获取缓存配置"""
    config = config_manager.load_config()
    return config.global_config.cache


def get_homeassistant_config() -> HomeAssistantConfig:
    """获取Home Assistant配置"""
    config = config_manager.load_config()
    return config.global_config.homeassistant


def get_plates_v2() -> List[PlateConfig]:
    """获取车牌配置列表（v2.0格式）"""
    config = config_manager.load_config()
    return config.plates


def get_jjz_accounts_v2() -> List[JJZAccount]:
    """获取进京证账户列表（v2.0格式）"""
    config = config_manager.load_config()
    return config.jjz_accounts


def get_admin_notifications() -> List[NotificationConfig]:
    """获取管理员推送配置"""
    config = config_manager.load_config()
    return config.global_config.admin.notifications
