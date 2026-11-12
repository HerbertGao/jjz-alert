"""查询令牌配置的解析与校验。"""

import logging

import pytest
import yaml

from jjz_alert.config.config import ConfigManager
from jjz_alert.config.config_models import ApiTokenConfig, AppConfig
from jjz_alert.config.validation import ConfigValidator


@pytest.mark.unit
class TestApiTokenConfigParsing:
    def test_parses_token_plate_bindings(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "global": {
                        "remind": {
                            "api": {
                                "enable": True,
                                "tokens": [
                                    {
                                        "token": "  replace-with-your-api-token  ",
                                        "plates": [
                                            " 京a00000 ",
                                            "京A00000",
                                            "京B00000",
                                        ],
                                    }
                                ],
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        config = ConfigManager(str(config_file)).load_config()
        tokens = config.global_config.remind.api.tokens

        assert len(tokens) == 1
        assert tokens[0].token == "replace-with-your-api-token"
        assert tokens[0].plates == ["京A00000", "京B00000"]

    def test_empty_token_is_dropped_and_duplicates_merge(self, tmp_path, caplog):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "global": {
                        "remind": {
                            "api": {
                                "tokens": [
                                    {"token": "   ", "plates": ["京A00000"]},
                                    {"token": "client-token", "plates": ["京a00000"]},
                                    {"token": "client-token", "plates": ["京B00000"]},
                                ]
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            config = ConfigManager(str(config_file)).load_config()

        tokens = config.global_config.remind.api.tokens
        assert len(tokens) == 1
        assert tokens[0].token == "client-token"
        assert tokens[0].plates == ["京A00000", "京B00000"]
        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "client-token" not in logged
        assert "京A00000" not in logged

    def test_missing_tokens_leave_the_list_empty(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({"global": {"remind": {"api": {"enable": True}}}}),
            encoding="utf-8",
        )

        config = ConfigManager(str(config_file)).load_config()
        assert config.global_config.remind.api.tokens == []


@pytest.mark.unit
class TestApiTokenValidation:
    def test_warns_when_api_has_no_usable_token(self):
        config = AppConfig()
        validator = ConfigValidator()

        assert validator.validate(config) is True
        assert any("未配置可用的查询令牌" in warning for warning in validator.warnings)

    def test_warns_when_token_has_no_plates(self):
        config = AppConfig()
        config.global_config.remind.api.tokens = [
            ApiTokenConfig(token="replace-with-your-api-token", plates=[])
        ]
        validator = ConfigValidator()

        assert validator.validate(config) is True
        assert any("未绑定车牌" in warning for warning in validator.warnings)
        assert all(
            "replace-with-your-api-token" not in warning
            for warning in validator.warnings
        )
