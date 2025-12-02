"""
配置验证模块

验证配置文件的正确性和完整性
"""

import logging
import re
from typing import List, Dict, Any
from urllib.parse import urlparse

from jjz_alert.config.config import (
    AppConfig,
    NotificationConfig,
    JJZAccount,
    PlateConfig,
)
from jjz_alert.config.config_models import AppriseUrlConfig


class ConfigValidator:
    """配置验证器"""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, config: AppConfig) -> bool:
        """验证完整配置"""
        self.errors.clear()
        self.warnings.clear()

        try:
            self._validate_global_config(config)
            self._validate_jjz_accounts(config.jjz_accounts)
            self._validate_plates(config.plates)
            self._validate_admin_notifications(config.global_config.admin.notifications)

            # 记录验证结果
            if self.errors:
                for error in self.errors:
                    logging.error(f"配置验证错误: {error}")
                return False

            if self.warnings:
                for warning in self.warnings:
                    logging.warning(f"配置验证警告: {warning}")

            logging.info("配置验证通过")
            return True

        except Exception as e:
            logging.error(f"配置验证异常: {e}")
            return False

    def _validate_global_config(self, config: AppConfig):
        """验证全局配置"""
        # 验证Redis配置
        redis_config = config.global_config.redis
        if not redis_config.host:
            self.errors.append("Redis主机地址不能为空")

        if not (1 <= redis_config.port <= 65535):
            self.errors.append(f"Redis端口号无效: {redis_config.port}")

        if not (0 <= redis_config.db <= 15):
            self.errors.append(f"Redis数据库编号无效: {redis_config.db}")

        # 验证缓存配置
        cache_config = config.global_config.cache
        if cache_config.push_history_ttl < 86400:
            self.warnings.append("推送历史缓存时间过短，建议至少1天")

        # 验证定时提醒配置
        remind_config = config.global_config.remind
        if remind_config.enable and not remind_config.times:
            self.warnings.append("启用了定时提醒但未配置提醒时间")

        for time_str in remind_config.times:
            if not self._validate_time_format(time_str):
                self.errors.append(f"时间格式无效: {time_str}")

        # 验证Home Assistant配置
        ha_config = config.global_config.homeassistant
        if ha_config.enabled:
            self._validate_homeassistant_config(ha_config)

    def _validate_homeassistant_config(self, ha_config):
        """验证Home Assistant配置"""
        # 检查集成模式
        integration_mode = ha_config.integration_mode.lower()

        if integration_mode == "rest":
            # REST 模式验证
            if not ha_config.rest_url:
                self.errors.append("启用Home Assistant但未配置URL")
            elif not self._validate_url(ha_config.rest_url):
                self.errors.append(f"Home Assistant URL格式无效: {ha_config.rest_url}")
            else:
                # 检查URL格式是否符合HA规范
                if not (
                    ha_config.rest_url.startswith("http://")
                    or ha_config.rest_url.startswith("https://")
                ):
                    self.errors.append("Home Assistant URL必须以http://或https://开头")

                # 检查是否包含端口
                if (
                    ":8123" not in ha_config.rest_url
                    and "homeassistant.local" in ha_config.rest_url
                ):
                    self.warnings.append("Home Assistant URL建议包含端口号:8123")

            if not ha_config.rest_token:
                self.errors.append("启用Home Assistant但未配置访问令牌")
            elif len(ha_config.rest_token) < 50:
                self.warnings.append("Home Assistant访问令牌长度过短，可能无效")

            # 验证实体前缀
            if not ha_config.rest_entity_prefix:
                self.errors.append("Home Assistant实体前缀不能为空")
            elif not self._validate_entity_prefix(ha_config.rest_entity_prefix):
                self.errors.append(
                    f"Home Assistant实体前缀格式无效: {ha_config.rest_entity_prefix}"
                )

            # 验证错误处理
            if ha_config.rest_retry_count < 1:
                self.errors.append("Home Assistant重试次数不能小于1")
            elif ha_config.rest_retry_count > 10:
                self.warnings.append("Home Assistant重试次数过多，建议不超过10次")

            if ha_config.rest_timeout < 5:
                self.warnings.append("Home Assistant请求超时时间过短，建议至少5秒")
            elif ha_config.rest_timeout > 60:
                self.warnings.append("Home Assistant请求超时时间过长，建议不超过60秒")

        elif integration_mode == "mqtt":
            # MQTT 模式验证
            if not ha_config.mqtt_host:
                self.errors.append("启用Home Assistant MQTT模式但未配置MQTT主机地址")

            if not (1 <= ha_config.mqtt_port <= 65535):
                self.errors.append(f"MQTT端口号无效: {ha_config.mqtt_port}")

            # 验证客户端ID
            if not ha_config.mqtt_client_id:
                self.warnings.append("MQTT客户端ID未配置，将使用默认值")

            # 验证QoS级别
            if ha_config.mqtt_qos not in (0, 1, 2):
                self.errors.append(
                    f"MQTT QoS级别无效: {ha_config.mqtt_qos}，必须为0、1或2"
                )
        else:
            self.errors.append(
                f"Home Assistant集成模式无效: {integration_mode}，必须为'rest'或'mqtt'"
            )

    def _validate_jjz_accounts(self, accounts: List[JJZAccount]):
        """验证进京证账户配置"""
        if not accounts:
            self.warnings.append("未配置任何进京证账户")
            return

        account_names = set()
        for i, account in enumerate(accounts):
            # 验证账户名称唯一性
            if account.name in account_names:
                self.errors.append(f"进京证账户名称重复: {account.name}")
            account_names.add(account.name)

            # 验证必填字段
            if not account.jjz.token:
                self.errors.append(f"进京证账户[{i}]缺少token")

            if not account.jjz.url:
                self.errors.append(f"进京证账户[{i}]缺少URL")
            elif not self._validate_url(account.jjz.url):
                self.errors.append(f"进京证账户[{i}]URL格式无效: {account.jjz.url}")

    def _validate_plates(self, plates: List[PlateConfig]):
        """验证车牌配置"""
        if not plates:
            self.warnings.append("未配置任何车牌号")
            return

        plate_numbers = set()
        for i, plate in enumerate(plates):
            # 验证车牌号格式
            if not self._validate_plate_number(plate.plate):
                self.errors.append(f"车牌号格式无效: {plate.plate}")

            # 验证车牌号唯一性
            if plate.plate in plate_numbers:
                self.errors.append(f"车牌号重复: {plate.plate}")
            plate_numbers.add(plate.plate)

            # 验证图标URL（如果有）
            if plate.icon and not self._validate_url(plate.icon):
                self.errors.append(f"车牌{plate.plate}图标URL格式无效: {plate.icon}")

            # 验证推送配置
            if not plate.notifications:
                self.warnings.append(f"车牌{plate.plate}未配置任何推送通道")
            else:
                for j, notification in enumerate(plate.notifications):
                    self._validate_notification_config(
                        notification, f"车牌{plate.plate}推送配置[{j}]"
                    )

    def _validate_admin_notifications(self, notifications: List[NotificationConfig]):
        """验证管理员推送配置"""
        if not notifications:
            self.warnings.append("未配置管理员推送通道")
            return

        for i, notification in enumerate(notifications):
            self._validate_notification_config(notification, f"管理员推送配置[{i}]")

    def _validate_notification_config(
        self, notification: NotificationConfig, context: str
    ):
        """验证推送配置"""
        if notification.type == "apprise":
            self._validate_apprise_config(notification, context)
        else:
            self.errors.append(f"{context}: 未知的推送类型: {notification.type}")

    def _validate_apprise_config(self, notification: NotificationConfig, context: str):
        """验证Apprise推送配置"""
        if not notification.urls:
            self.errors.append(f"{context}: Apprise推送URL列表不能为空")

        for i, url_item in enumerate(notification.urls):
            # 支持两种格式：纯字符串或 AppriseUrlConfig 对象
            if isinstance(url_item, AppriseUrlConfig):
                url = url_item.url
                batch_key = url_item.batch_key
                # 验证 batch_key 格式（如果有）
                if batch_key is not None and not isinstance(batch_key, str):
                    self.errors.append(
                        f"{context}: Apprise URL[{i}] batch_key 必须是字符串"
                    )
                elif batch_key is not None and len(batch_key) == 0:
                    self.warnings.append(
                        f"{context}: Apprise URL[{i}] batch_key 为空字符串，将被忽略"
                    )
            elif isinstance(url_item, str):
                url = url_item
            else:
                self.errors.append(
                    f"{context}: Apprise URL[{i}] 格式无效，必须是字符串或对象"
                )
                continue

            if not url:
                self.errors.append(f"{context}: Apprise URL[{i}]不能为空")
            elif not self._validate_apprise_url(url):
                self.warnings.append(f"{context}: Apprise URL[{i}]格式可能无效: {url}")

    def _validate_url(self, url: str) -> bool:
        """验证URL格式"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def _validate_apprise_url(self, url: str) -> bool:
        """验证Apprise URL格式"""
        # Apprise支持多种URL格式，这里做基础验证
        if "://" not in url:
            return False

        # 检查是否为已知的Apprise服务前缀
        known_prefixes = [
            "bark://",
            "tgram://",
            "mailto://",
            "wxwork://",
            "dingding://",
            "slack://",
            "discord://",
            "teams://",
            "webhook://",
            "json://",
        ]

        return any(url.startswith(prefix) for prefix in known_prefixes)

    def _validate_plate_number(self, plate: str) -> bool:
        """验证车牌号格式"""
        # 简单的车牌号格式验证（支持中国车牌）
        # 京A12345, 京A123AB等格式
        pattern = r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9]{4,5}[A-Z0-9挂学警港澳]?$"
        return re.match(pattern, plate) is not None

    def _validate_time_format(self, time_str: str) -> bool:
        """验证时间格式 HH:MM"""
        pattern = r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$"
        return re.match(pattern, time_str) is not None

    def _validate_entity_prefix(self, prefix: str) -> bool:
        """验证Home Assistant实体前缀格式"""
        # HA实体前缀只能包含小写字母、数字和下划线，不能以数字开头
        pattern = r"^[a-z][a-z0-9_]*$"
        return re.match(pattern, prefix) is not None

    def get_validation_summary(self) -> Dict[str, Any]:
        """获取验证摘要"""
        return {
            "valid": len(self.errors) == 0,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors.copy(),
            "warnings": self.warnings.copy(),
        }


def validate_config(config: AppConfig) -> bool:
    """验证配置的快捷函数"""
    validator = ConfigValidator()
    return validator.validate(config)
