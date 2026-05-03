"""
自动续办配置模型和校验测试
"""

import pytest
import yaml

from jjz_alert.config.config import ConfigManager
from jjz_alert.config.config_models import (
    AutoRenewConfig,
    AutoRenewDestinationConfig,
    AutoRenewAccommodationConfig,
    AutoRenewApplyLocationConfig,
    GlobalAutoRenewConfig,
    PlateConfig,
    GlobalConfig,
    AppConfig,
)
from jjz_alert.config.validation import ConfigValidator


@pytest.mark.unit
class TestAutoRenewConfigParsing:
    """续办配置解析测试"""

    def test_parse_full_auto_renew(self, tmp_path):
        """完整续办配置可正确解析"""
        config_data = {
            "global": {
                "redis": {"host": "localhost"},
                "auto_renew": {
                    "min_delay_seconds": 60,
                    "max_delay_seconds": 240,
                },
            },
            "plates": [
                {
                    "plate": "京A12345",
                    "auto_renew": {
                        "enabled": True,
                        "purpose": "03",
                        "purpose_name": "探亲访友",
                        "destination": {
                            "area": "朝阳区",
                            "area_code": "010",
                            "address": "测试地址",
                            "lng": "116.4",
                            "lat": "39.9",
                        },
                        "accommodation": {
                            "enabled": True,
                            "address": "住宿地址",
                            "lng": "116.5",
                            "lat": "40.0",
                        },
                        "apply_location": {
                            "lng": "116.3",
                            "lat": "39.8",
                        },
                    },
                    "notifications": [],
                }
            ],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        # 全局配置
        assert config.global_config.auto_renew.min_delay_seconds == 60
        assert config.global_config.auto_renew.max_delay_seconds == 240

        # 车牌配置
        plate = config.plates[0]
        assert plate.auto_renew is not None
        assert plate.auto_renew.enabled is True
        assert plate.auto_renew.purpose == "03"
        assert plate.auto_renew.destination.area == "朝阳区"
        assert plate.auto_renew.accommodation.enabled is True
        assert plate.auto_renew.accommodation.address == "住宿地址"
        assert plate.auto_renew.apply_location.lng == "116.3"

    def test_parse_no_auto_renew(self, tmp_path):
        """无续办配置时 auto_renew 为 None"""
        config_data = {
            "plates": [{"plate": "京A12345", "notifications": []}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config.plates[0].auto_renew is None

    def test_default_global_auto_renew(self, tmp_path):
        """未配置全局续办时使用默认值"""
        config_data = {"global": {"redis": {"host": "localhost"}}}
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        assert config.global_config.auto_renew.min_delay_seconds == 30
        assert config.global_config.auto_renew.max_delay_seconds == 180

    def test_legacy_time_window_fields_warn_and_use_defaults(self, tmp_path, caplog):
        """旧 time_window_* 字段保留时输出 WARN 但不阻塞，使用新字段默认值"""
        import logging as _logging

        config_data = {
            "global": {
                "redis": {"host": "localhost"},
                "auto_renew": {
                    "time_window_start": "00:00",
                    "time_window_end": "06:00",
                },
            }
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        with caplog.at_level(_logging.WARNING):
            config = manager.load_config()

        assert config.global_config.auto_renew.min_delay_seconds == 30
        assert config.global_config.auto_renew.max_delay_seconds == 180
        assert any("time_window_start" in r.message for r in caplog.records)

    def test_invalid_delay_value_falls_back_to_default(self, tmp_path, caplog):
        """min_delay_seconds 配为非数字时输出 WARN 并使用默认，且不丢失其他配置"""
        import logging as _logging

        config_data = {
            "global": {
                "redis": {"host": "localhost"},
                "auto_renew": {"min_delay_seconds": "not-a-number"},
            },
            "jjz_accounts": [
                {"name": "测试账户", "jjz": {"token": "t", "url": "https://x/pro/a"}}
            ],
            "plates": [{"plate": "京A12345", "notifications": []}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        with caplog.at_level(_logging.WARNING):
            config = manager.load_config()

        # 异常字段使用默认值
        assert config.global_config.auto_renew.min_delay_seconds == 30
        assert any("min_delay_seconds" in r.message for r in caplog.records)
        # 其他配置未丢失
        assert len(config.jjz_accounts) == 1
        assert len(config.plates) == 1
        assert config.plates[0].plate == "京A12345"

    def test_default_apply_location(self, tmp_path):
        """未配置 apply_location 时使用默认坐标（非 destination 坐标）"""
        config_data = {
            "plates": [
                {
                    "plate": "京A12345",
                    "auto_renew": {
                        "enabled": True,
                        "purpose": "03",
                        "purpose_name": "探亲访友",
                        "destination": {
                            "area": "朝阳区",
                            "area_code": "010",
                            "address": "测试",
                            "lng": "116.5",
                            "lat": "40.0",
                        },
                    },
                    "notifications": [],
                }
            ]
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        manager = ConfigManager(str(config_file))
        config = manager.load_config()

        loc = config.plates[0].auto_renew.apply_location
        assert loc.lng == "116.4"
        assert loc.lat == "39.9"


@pytest.mark.unit
class TestAutoRenewConfigValidation:
    """续办配置校验测试"""

    def _make_valid_config(self):
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                auto_renew=AutoRenewConfig(
                    enabled=True,
                    purpose="03",
                    purpose_name="探亲访友",
                    destination=AutoRenewDestinationConfig(
                        area="朝阳区",
                        area_code="010",
                        address="测试地址",
                        lng="116.4",
                        lat="39.9",
                    ),
                ),
            )
        ]
        return config

    def test_valid_config_passes(self):
        """合法配置通过校验"""
        validator = ConfigValidator()
        config = self._make_valid_config()
        assert validator.validate(config) is True

    def test_missing_required_field(self):
        """缺少必需字段报错"""
        validator = ConfigValidator()
        config = self._make_valid_config()
        config.plates[0].auto_renew.destination.area = ""
        validator.validate(config)
        assert any("destination.area" in e for e in validator.errors)

    def test_missing_purpose(self):
        """缺少进京目的报错"""
        validator = ConfigValidator()
        config = self._make_valid_config()
        config.plates[0].auto_renew.purpose = ""
        validator.validate(config)
        assert any("purpose" in e for e in validator.errors)

    def test_accommodation_missing_address(self):
        """启用住宿但缺少地址报错"""
        validator = ConfigValidator()
        config = self._make_valid_config()
        config.plates[0].auto_renew.accommodation = AutoRenewAccommodationConfig(
            enabled=True, address="", lng="116.4", lat="39.9"
        )
        validator.validate(config)
        assert any("accommodation.address" in e for e in validator.errors)

    def test_disabled_auto_renew_skips_validation(self):
        """续办未启用时不校验字段"""
        validator = ConfigValidator()
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                auto_renew=AutoRenewConfig(enabled=False),
            )
        ]
        assert validator.validate(config) is True

    def test_invalid_delay_range(self):
        """min > max 报错"""
        validator = ConfigValidator()
        config = AppConfig()
        config.global_config.auto_renew = GlobalAutoRenewConfig(
            min_delay_seconds=300, max_delay_seconds=60
        )
        validator.validate(config)
        assert any("min_delay_seconds" in e for e in validator.errors)

    def test_negative_delay(self):
        """负数延迟报错"""
        validator = ConfigValidator()
        config = AppConfig()
        config.global_config.auto_renew = GlobalAutoRenewConfig(
            min_delay_seconds=-1, max_delay_seconds=180
        )
        validator.validate(config)
        assert any("min_delay_seconds" in e for e in validator.errors)

    def test_valid_delay_range(self):
        """合法延迟范围通过"""
        validator = ConfigValidator()
        config = AppConfig()
        config.global_config.auto_renew = GlobalAutoRenewConfig(
            min_delay_seconds=30, max_delay_seconds=180
        )
        validator.validate(config)
        assert not any("delay" in e.lower() for e in validator.errors)
