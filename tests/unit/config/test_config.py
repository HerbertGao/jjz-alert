"""
Config 模块单元测试
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import yaml

from jjz_alert.config.config import (
    ConfigManager,
    config_manager,
    get_redis_config,
    get_cache_config,
    get_homeassistant_config,
    get_plates,
    get_jjz_accounts,
    get_admin_notifications,
)
from jjz_alert.config.config_models import AppConfig


@pytest.mark.unit
class TestConfigManager:
    """ConfigManager测试类"""

    def test_load_config_success(self, tmp_path):
        """测试加载配置文件 - 成功"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "log": {"level": "DEBUG"},
                "redis": {"host": "localhost", "port": 6379},
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_config_file_not_exists(self, tmp_path):
        """测试加载配置文件 - 文件不存在"""
        config_file = tmp_path / "nonexistent.yaml"
        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config is not None
        assert isinstance(config, AppConfig)

    def test_load_config_file_error(self, tmp_path):
        """测试加载配置文件 - 文件读取错误"""
        config_file = tmp_path / "config.yaml"
        # 创建无效的 YAML 文件
        config_file.write_text("invalid: yaml: content: [", encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # 应该返回默认配置
        assert config is not None
        assert isinstance(config, AppConfig)

    def test_reload_config(self, tmp_path):
        """测试强制重新加载配置"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {"log": {"level": "INFO"}},
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config1 = manager.load_config()

        # 修改配置文件
        config_data["global"]["log"]["level"] = "DEBUG"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        # 重新加载
        config2 = manager.reload_config()

        assert config1 is not None
        assert config2 is not None

    def test_apply_env_overrides_redis(self, tmp_path, monkeypatch):
        """测试环境变量覆盖 - Redis配置"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "redis": {"host": "localhost", "port": 6379, "db": 0},
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        # 设置环境变量
        monkeypatch.setenv("REDIS_HOST", "redis.example.com")
        monkeypatch.setenv("REDIS_PORT", "6380")
        monkeypatch.setenv("REDIS_DB", "1")
        monkeypatch.setenv("REDIS_PASSWORD", "test_password")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config.global_config.redis.host == "redis.example.com"
        assert config.global_config.redis.port == 6380
        assert config.global_config.redis.db == 1
        assert config.global_config.redis.password == "test_password"

    def test_apply_env_overrides_log_level(self, tmp_path, monkeypatch):
        """测试环境变量覆盖 - 日志级别"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {"log": {"level": "INFO"}},
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        # 设置环境变量
        monkeypatch.setenv("LOG_LEVEL", "debug")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config.global_config.log.level == "DEBUG"


@pytest.mark.unit
class TestConfigFunctions:
    """配置函数测试类"""

    def test_get_redis_config(self, tmp_path):
        """测试获取Redis配置"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "redis": {"host": "test_host", "port": 6380},
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            mock_config = AppConfig()
            mock_config.global_config.redis.host = "test_host"
            mock_config.global_config.redis.port = 6380
            mock_manager.load_config.return_value = mock_config

            redis_config = get_redis_config()

            assert redis_config.host == "test_host"
            assert redis_config.port == 6380
            mock_manager.load_config.assert_called_once()

    def test_get_cache_config(self, tmp_path):
        """测试获取缓存配置"""
        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            mock_config = AppConfig()
            mock_config.global_config.cache.push_history_ttl = 3600
            mock_manager.load_config.return_value = mock_config

            cache_config = get_cache_config()

            assert cache_config.push_history_ttl == 3600
            mock_manager.load_config.assert_called_once()

    def test_get_homeassistant_config(self, tmp_path):
        """测试获取Home Assistant配置"""
        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            mock_config = AppConfig()
            mock_config.global_config.homeassistant.enabled = True
            mock_manager.load_config.return_value = mock_config

            ha_config = get_homeassistant_config()

            assert ha_config.enabled is True
            mock_manager.load_config.assert_called_once()

    def test_get_plates(self, tmp_path):
        """测试获取车牌配置列表"""
        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            from jjz_alert.config.config_models import PlateConfig

            mock_config = AppConfig()
            mock_config.plates = [
                PlateConfig(plate="京A12345", display_name="测试车辆"),
            ]
            mock_manager.load_config.return_value = mock_config

            plates = get_plates()

            assert len(plates) == 1
            assert plates[0].plate == "京A12345"
            mock_manager.load_config.assert_called_once()

    def test_get_jjz_accounts(self, tmp_path):
        """测试获取进京证账户列表"""
        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            from jjz_alert.config.config_models import JJZAccount, JJZConfig

            mock_config = AppConfig()
            mock_config.jjz_accounts = [
                JJZAccount(
                    name="测试账户",
                    jjz=JJZConfig(token="test_token", url="https://test.example.com"),
                ),
            ]
            mock_manager.load_config.return_value = mock_config

            accounts = get_jjz_accounts()

            assert len(accounts) == 1
            assert accounts[0].name == "测试账户"
            mock_manager.load_config.assert_called_once()

    def test_get_admin_notifications(self, tmp_path):
        """测试获取管理员推送配置"""
        with patch("jjz_alert.config.config.config_manager") as mock_manager:
            from jjz_alert.config.config_models import NotificationConfig

            mock_config = AppConfig()
            mock_config.global_config.admin.notifications = [
                NotificationConfig(type="apprise", urls=["test://url"]),
            ]
            mock_manager.load_config.return_value = mock_config

            notifications = get_admin_notifications()

            assert len(notifications) == 1
            assert notifications[0].type == "apprise"
            mock_manager.load_config.assert_called_once()


@pytest.mark.unit
class TestHomeAssistantValidation:
    """Home Assistant 配置验证测试类"""

    def test_ha_disabled_when_rest_url_missing(self, tmp_path):
        """测试 REST 模式缺少 rest_url 时禁用 HA"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "rest",
                    "rest_token": "test_token",
                    # rest_url 缺失
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该被禁用
        assert config.global_config.homeassistant.enabled is False

    def test_ha_disabled_when_rest_token_missing(self, tmp_path):
        """测试 REST 模式缺少 rest_token 时禁用 HA"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "rest",
                    "rest_url": "http://homeassistant.local:8123",
                    # rest_token 缺失
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该被禁用
        assert config.global_config.homeassistant.enabled is False

    def test_ha_disabled_when_mqtt_host_missing(self, tmp_path):
        """测试 MQTT 模式缺少 mqtt_host 时禁用 HA"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "mqtt",
                    # mqtt_host 缺失
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该被禁用
        assert config.global_config.homeassistant.enabled is False

    def test_ha_enabled_when_rest_config_valid(self, tmp_path):
        """测试 REST 模式配置完整时保持启用状态"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "rest",
                    "rest_url": "http://homeassistant.local:8123",
                    "rest_token": "test_token",
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该保持启用
        assert config.global_config.homeassistant.enabled is True
        assert (
            config.global_config.homeassistant.rest_url
            == "http://homeassistant.local:8123"
        )
        assert config.global_config.homeassistant.rest_token == "test_token"

    def test_ha_enabled_when_mqtt_config_valid(self, tmp_path):
        """测试 MQTT 模式配置完整时保持启用状态"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "mqtt",
                    "mqtt_host": "mqtt.example.com",
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该保持启用
        assert config.global_config.homeassistant.enabled is True
        assert config.global_config.homeassistant.mqtt_host == "mqtt.example.com"

    def test_ha_disabled_when_multiple_fields_missing(self, tmp_path):
        """测试 REST 模式多个必需字段缺失时禁用 HA"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "rest",
                    # rest_url 和 rest_token 都缺失
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # HA 应该被禁用
        assert config.global_config.homeassistant.enabled is False

    def test_ha_reads_custom_rest_config_values(self, tmp_path):
        """测试读取自定义 REST 配置值"""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "global": {
                "homeassistant": {
                    "enabled": True,
                    "integration_mode": "rest",
                    "rest_url": "http://homeassistant.local:8123",
                    "rest_token": "test_token_123456789012345678901234567890123456789012345",
                    "rest_entity_prefix": "custom_prefix",
                    "rest_device_manufacturer": "Custom Manufacturer",
                    "rest_device_model": "Custom Model",
                    "rest_retry_count": 5,
                    "rest_timeout": 60,
                }
            },
            "jjz_accounts": [],
            "plates": [],
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # 验证自定义配置值被正确读取
        assert config.global_config.homeassistant.enabled is True
        assert config.global_config.homeassistant.rest_entity_prefix == "custom_prefix"
        assert (
            config.global_config.homeassistant.rest_device_manufacturer
            == "Custom Manufacturer"
        )
        assert config.global_config.homeassistant.rest_device_model == "Custom Model"
        assert config.global_config.homeassistant.rest_retry_count == 5
        assert config.global_config.homeassistant.rest_timeout == 60
