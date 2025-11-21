"""
JJZ-Alert 配置管理模块

支持结构化配置及环境变量覆盖
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from jjz_alert.config.config_models import (
    RedisConfig,
    CacheConfig,
    APIConfig,
    RemindConfig,
    LogConfig,
    AdminConfig,
    HomeAssistantConfig,
    MessageTemplateConfig,
    GlobalConfig,
    JJZConfig,
    JJZAccount,
    NotificationConfig,
    PlateConfig,
    AppConfig,
)

# 导出所有配置模型
__all__ = [
    "RedisConfig",
    "CacheConfig",
    "APIConfig",
    "RemindConfig",
    "LogConfig",
    "AdminConfig",
    "HomeAssistantConfig",
    "MessageTemplateConfig",
    "GlobalConfig",
    "JJZConfig",
    "JJZAccount",
    "NotificationConfig",
    "PlateConfig",
    "AppConfig",
    "ConfigManager",
    "config_manager",
    "get_redis_config",
    "get_cache_config",
    "get_homeassistant_config",
    "get_plates",
    "get_jjz_accounts",
    "get_admin_notifications",
]


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

            self._config = self._parse_structured_config(self._raw_config)
            logging.info(f"成功加载配置文件: {self.config_file}")

        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            self._config = AppConfig()

    def _parse_structured_config(self, v2_config: Dict) -> AppConfig:
        """解析配置格式"""
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
                        enable=api_data.get(
                            "enable", config.global_config.remind.api.enable
                        ),
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
                rest_url = ha_data.get(
                    "rest_url", ha_data.get("url", "http://homeassistant.local:8123")
                )
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
                    traffic_reminder_prefix=template_data.get(
                        "traffic_reminder_prefix"
                    ),
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
# 接口函数
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


def get_plates() -> List[PlateConfig]:
    """获取车牌配置列表"""
    config = config_manager.load_config()
    return config.plates


def get_jjz_accounts() -> List[JJZAccount]:
    """获取进京证账户列表"""
    config = config_manager.load_config()
    return config.jjz_accounts


def get_admin_notifications() -> List[NotificationConfig]:
    """获取管理员推送配置"""
    config = config_manager.load_config()
    return config.global_config.admin.notifications
