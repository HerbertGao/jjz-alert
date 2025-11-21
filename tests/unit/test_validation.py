"""
配置验证模块单元测试
"""

import pytest

from jjz_alert.config.config import (
    AppConfig,
    GlobalConfig,
    RedisConfig,
    CacheConfig,
    RemindConfig,
    HomeAssistantConfig,
    JJZAccount,
    JJZConfig,
    PlateConfig,
    NotificationConfig,
    AdminConfig,
)
from jjz_alert.config.validation import (
    ConfigValidator,
    ConfigValidationError,
    validate_config,
)


@pytest.mark.unit
class TestConfigValidator:
    """配置验证器测试"""

    def test_validate_redis_config_valid(self):
        """测试Redis配置验证 - 有效"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="localhost", port=6379, db=0)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True
        assert len(validator.errors) == 0

    def test_validate_redis_config_empty_host(self):
        """测试Redis配置验证 - 空主机地址"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="", port=6379, db=0)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("Redis主机地址不能为空" in error for error in validator.errors)

    def test_validate_redis_config_invalid_port(self):
        """测试Redis配置验证 - 无效端口"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="localhost", port=70000, db=0)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("Redis端口号无效" in error for error in validator.errors)

    def test_validate_redis_config_invalid_db(self):
        """测试Redis配置验证 - 无效数据库编号"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="localhost", port=6379, db=20)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("Redis数据库编号无效" in error for error in validator.errors)

    def test_validate_cache_config_short_ttl(self):
        """测试缓存配置验证 - TTL过短"""
        config = AppConfig()
        config.global_config.cache = CacheConfig(push_history_ttl=3600)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any("推送历史缓存时间过短" in warning for warning in validator.warnings)

    def test_validate_remind_config_enabled_no_times(self):
        """测试定时提醒配置验证 - 启用但未配置时间"""
        config = AppConfig()
        config.global_config.remind = RemindConfig(enable=True, times=[])

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "启用了定时提醒但未配置提醒时间" in warning
            for warning in validator.warnings
        )

    def test_validate_remind_config_invalid_time_format(self):
        """测试定时提醒配置验证 - 无效时间格式"""
        config = AppConfig()
        config.global_config.remind = RemindConfig(
            enable=True, times=["25:00", "08:00"]
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("时间格式无效" in error for error in validator.errors)

    def test_validate_remind_config_valid_time_format(self):
        """测试定时提醒配置验证 - 有效时间格式"""
        config = AppConfig()
        config.global_config.remind = RemindConfig(
            enable=True, times=["08:00", "12:00", "18:00"]
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True
        assert len(validator.errors) == 0

    def test_validate_homeassistant_config_disabled(self):
        """测试Home Assistant配置验证 - 未启用"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(enabled=False)

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True

    def test_validate_homeassistant_config_enabled_no_url(self):
        """测试Home Assistant配置验证 - 启用但未配置URL"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True, rest_url=""
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "启用Home Assistant但未配置URL" in error for error in validator.errors
        )

    def test_validate_homeassistant_config_invalid_url(self):
        """测试Home Assistant配置验证 - 无效URL"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True, rest_url="invalid-url"
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("Home Assistant URL格式无效" in error for error in validator.errors)

    def test_validate_homeassistant_config_url_no_scheme(self):
        """测试Home Assistant配置验证 - URL无协议"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",  # 先通过URL格式验证
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        # 由于URL格式有效，会检查协议，但http://开头是有效的
        # 所以这个测试需要测试一个无效的URL格式
        config.global_config.homeassistant.rest_url = "invalid-url"
        validator2 = ConfigValidator()
        result2 = validator2.validate(config)

        assert result2 is False
        assert any("Home Assistant URL格式无效" in error for error in validator2.errors)

    def test_validate_homeassistant_config_url_missing_port(self):
        """测试Home Assistant配置验证 - URL缺少端口"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Home Assistant URL建议包含端口号" in warning
            for warning in validator.warnings
        )

    def test_validate_homeassistant_config_no_token(self):
        """测试Home Assistant配置验证 - 未配置令牌"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True, rest_url="http://homeassistant.local:8123", rest_token=""
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "启用Home Assistant但未配置访问令牌" in error for error in validator.errors
        )

    def test_validate_homeassistant_config_short_token(self):
        """测试Home Assistant配置验证 - 令牌过短"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True, rest_url="http://homeassistant.local:8123", rest_token="short"
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Home Assistant访问令牌长度过短" in warning
            for warning in validator.warnings
        )

    def test_validate_homeassistant_config_empty_entity_prefix(self):
        """测试Home Assistant配置验证 - 空实体前缀"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "Home Assistant实体前缀不能为空" in error for error in validator.errors
        )

    def test_validate_homeassistant_config_invalid_entity_prefix(self):
        """测试Home Assistant配置验证 - 无效实体前缀"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="Invalid-Prefix",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "Home Assistant实体前缀格式无效" in error for error in validator.errors
        )

    def test_validate_homeassistant_config_valid_entity_prefix(self):
        """测试Home Assistant配置验证 - 有效实体前缀"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True

    def test_validate_homeassistant_config_invalid_retry_count(self):
        """测试Home Assistant配置验证 - 无效重试次数"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
            rest_retry_count=0,
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "Home Assistant重试次数不能小于1" in error for error in validator.errors
        )

    def test_validate_homeassistant_config_high_retry_count(self):
        """测试Home Assistant配置验证 - 重试次数过多"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
            rest_retry_count=15,
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Home Assistant重试次数过多" in warning for warning in validator.warnings
        )

    def test_validate_homeassistant_config_short_timeout(self):
        """测试Home Assistant配置验证 - 超时时间过短"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
            rest_timeout=3,
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Home Assistant请求超时时间过短" in warning
            for warning in validator.warnings
        )

    def test_validate_homeassistant_config_long_timeout(self):
        """测试Home Assistant配置验证 - 超时时间过长"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="http://homeassistant.local:8123",
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
            rest_timeout=120,
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Home Assistant请求超时时间过长" in warning
            for warning in validator.warnings
        )

    def test_validate_jjz_accounts_empty(self):
        """测试进京证账户配置验证 - 空列表"""
        config = AppConfig()
        config.jjz_accounts = []

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any("未配置任何进京证账户" in warning for warning in validator.warnings)

    def test_validate_jjz_accounts_duplicate_names(self):
        """测试进京证账户配置验证 - 重复名称"""
        config = AppConfig()
        config.jjz_accounts = [
            JJZAccount(
                name="账户1", jjz=JJZConfig(token="token1", url="https://example.com")
            ),
            JJZAccount(
                name="账户1", jjz=JJZConfig(token="token2", url="https://example.com")
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("进京证账户名称重复" in error for error in validator.errors)

    def test_validate_jjz_accounts_missing_token(self):
        """测试进京证账户配置验证 - 缺少token"""
        config = AppConfig()
        config.jjz_accounts = [
            JJZAccount(
                name="账户1", jjz=JJZConfig(token="", url="https://example.com")
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "进京证账户" in error and "缺少token" in error for error in validator.errors
        )

    def test_validate_jjz_accounts_missing_url(self):
        """测试进京证账户配置验证 - 缺少URL"""
        config = AppConfig()
        config.jjz_accounts = [
            JJZAccount(name="账户1", jjz=JJZConfig(token="token1", url="")),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "进京证账户" in error and "缺少URL" in error for error in validator.errors
        )

    def test_validate_jjz_accounts_invalid_url(self):
        """测试进京证账户配置验证 - 无效URL"""
        config = AppConfig()
        config.jjz_accounts = [
            JJZAccount(name="账户1", jjz=JJZConfig(token="token1", url="invalid-url")),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "进京证账户" in error and "URL格式无效" in error
            for error in validator.errors
        )

    def test_validate_plates_empty(self):
        """测试车牌配置验证 - 空列表"""
        config = AppConfig()
        config.plates = []

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any("未配置任何车牌号" in warning for warning in validator.warnings)

    def test_validate_plates_invalid_format(self):
        """测试车牌配置验证 - 无效格式"""
        config = AppConfig()
        config.plates = [
            PlateConfig(plate="INVALID"),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("车牌号格式无效" in error for error in validator.errors)

    def test_validate_plates_valid_format(self):
        """测试车牌配置验证 - 有效格式"""
        config = AppConfig()
        config.plates = [
            PlateConfig(plate="京A12345"),
            PlateConfig(plate="沪B67890"),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True

    def test_validate_plates_duplicate(self):
        """测试车牌配置验证 - 重复车牌"""
        config = AppConfig()
        config.plates = [
            PlateConfig(plate="京A12345"),
            PlateConfig(plate="京A12345"),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("车牌号重复" in error for error in validator.errors)

    def test_validate_plates_invalid_icon_url(self):
        """测试车牌配置验证 - 无效图标URL"""
        config = AppConfig()
        config.plates = [
            PlateConfig(plate="京A12345", icon="invalid-url"),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("图标URL格式无效" in error for error in validator.errors)

    def test_validate_plates_no_notifications(self):
        """测试车牌配置验证 - 无推送配置"""
        config = AppConfig()
        config.plates = [
            PlateConfig(plate="京A12345", notifications=[]),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any("未配置任何推送通道" in warning for warning in validator.warnings)

    def test_validate_admin_notifications_empty(self):
        """测试管理员推送配置验证 - 空列表"""
        config = AppConfig()
        config.global_config.admin = AdminConfig(notifications=[])

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any("未配置管理员推送通道" in warning for warning in validator.warnings)

    def test_validate_notification_unknown_type(self):
        """测试推送配置验证 - 未知类型"""
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                notifications=[NotificationConfig(type="unknown", urls=[])],
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("未知的推送类型" in error for error in validator.errors)

    def test_validate_apprise_config_empty_urls(self):
        """测试Apprise推送配置验证 - 空URL列表"""
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                notifications=[NotificationConfig(type="apprise", urls=[])],
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any("Apprise推送URL列表不能为空" in error for error in validator.errors)

    def test_validate_apprise_config_empty_url(self):
        """测试Apprise推送配置验证 - 空URL"""
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                notifications=[NotificationConfig(type="apprise", urls=[""])],
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "Apprise URL" in error and "不能为空" in error for error in validator.errors
        )

    def test_validate_apprise_config_invalid_url(self):
        """测试Apprise推送配置验证 - 无效URL"""
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                notifications=[
                    NotificationConfig(type="apprise", urls=["invalid://url"])
                ],
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True  # 警告不影响验证结果
        assert any(
            "Apprise URL" in warning and "格式可能无效" in warning
            for warning in validator.warnings
        )

    def test_validate_apprise_config_valid_urls(self):
        """测试Apprise推送配置验证 - 有效URL"""
        config = AppConfig()
        config.plates = [
            PlateConfig(
                plate="京A12345",
                notifications=[
                    NotificationConfig(type="apprise", urls=["bark://token@host"])
                ],
            ),
        ]

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True

    def test_validate_url_valid(self):
        """测试URL验证 - 有效URL"""
        validator = ConfigValidator()

        assert validator._validate_url("http://example.com") is True
        assert validator._validate_url("https://example.com/path") is True
        assert validator._validate_url("http://example.com:8080") is True

    def test_validate_url_invalid(self):
        """测试URL验证 - 无效URL"""
        validator = ConfigValidator()

        assert validator._validate_url("invalid-url") is False
        assert validator._validate_url("") is False
        assert validator._validate_url("://") is False

    def test_validate_apprise_url_valid(self):
        """测试Apprise URL验证 - 有效URL"""
        validator = ConfigValidator()

        assert validator._validate_apprise_url("bark://token@host") is True
        assert validator._validate_apprise_url("tgram://token") is True
        assert validator._validate_apprise_url("mailto://user@example.com") is True

    def test_validate_apprise_url_invalid(self):
        """测试Apprise URL验证 - 无效URL"""
        validator = ConfigValidator()

        assert validator._validate_apprise_url("invalid://url") is False
        assert validator._validate_apprise_url("no-scheme") is False

    def test_validate_plate_number_valid(self):
        """测试车牌号验证 - 有效格式"""
        validator = ConfigValidator()

        assert validator._validate_plate_number("京A12345") is True
        assert validator._validate_plate_number("沪B67890") is True
        assert validator._validate_plate_number("粤C123AB") is True

    def test_validate_plate_number_invalid(self):
        """测试车牌号验证 - 无效格式"""
        validator = ConfigValidator()

        assert validator._validate_plate_number("INVALID") is False
        assert validator._validate_plate_number("12345") is False
        assert validator._validate_plate_number("") is False

    def test_validate_time_format_valid(self):
        """测试时间格式验证 - 有效格式"""
        validator = ConfigValidator()

        assert validator._validate_time_format("08:00") is True
        assert validator._validate_time_format("12:30") is True
        assert validator._validate_time_format("23:59") is True

    def test_validate_time_format_invalid(self):
        """测试时间格式验证 - 无效格式"""
        validator = ConfigValidator()

        assert validator._validate_time_format("25:00") is False
        assert validator._validate_time_format("12:60") is False
        assert (
            validator._validate_time_format("8:00") is True
        )  # 正则表达式允许0-19，所以8:00是有效的
        assert validator._validate_time_format("invalid") is False
        assert validator._validate_time_format("24:00") is False  # 24小时制最大是23:59

    def test_validate_entity_prefix_valid(self):
        """测试实体前缀验证 - 有效格式"""
        validator = ConfigValidator()

        assert validator._validate_entity_prefix("jjz_alert") is True
        assert validator._validate_entity_prefix("test_123") is True
        assert validator._validate_entity_prefix("a") is True

    def test_validate_entity_prefix_invalid(self):
        """测试实体前缀验证 - 无效格式"""
        validator = ConfigValidator()

        assert validator._validate_entity_prefix("Invalid-Prefix") is False
        assert validator._validate_entity_prefix("123prefix") is False  # 不能以数字开头
        assert validator._validate_entity_prefix("prefix with spaces") is False
        assert validator._validate_entity_prefix("UPPERCASE") is False

    def test_get_validation_summary(self):
        """测试获取验证摘要"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="", port=6379, db=0)
        config.plates = [PlateConfig(plate="INVALID")]

        validator = ConfigValidator()
        validator.validate(config)

        summary = validator.get_validation_summary()

        assert summary["valid"] is False
        assert summary["error_count"] > 0
        assert "errors" in summary
        assert "warnings" in summary

    def test_validate_exception_handling(self):
        """测试验证异常处理"""
        validator = ConfigValidator()

        # 创建一个会导致异常的配置对象
        class BadConfig:
            def __getattr__(self, name):
                raise Exception("Unexpected error")

        bad_config = BadConfig()

        result = validator.validate(bad_config)

        assert result is False

    def test_validate_config_helper_function(self):
        """测试验证配置快捷函数"""
        config = AppConfig()
        config.global_config.redis = RedisConfig(host="localhost", port=6379, db=0)

        result = validate_config(config)

        assert result is True

    def test_validate_homeassistant_config_url_no_http_scheme(self):
        """测试Home Assistant URL必须以http://或https://开头"""
        config = AppConfig()
        config.global_config.homeassistant = HomeAssistantConfig(
            enabled=True,
            rest_url="ftp://homeassistant.local:8123",  # 无效的协议
            rest_token="valid_token_12345678901234567890123456789012345678901234567890",
            rest_entity_prefix="jjz_alert",
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is False
        assert any(
            "Home Assistant URL必须以http://或https://开头" in error
            for error in validator.errors
        )

    def test_validate_admin_notifications(self):
        """测试管理员推送配置验证"""
        config = AppConfig()
        config.global_config.admin = AdminConfig(
            notifications=[
                NotificationConfig(type="apprise", urls=["bark://token@host"]),
                NotificationConfig(type="apprise", urls=["tgram://token"]),
            ]
        )

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result is True
        assert len(validator.errors) == 0

    def test_validate_url_exception_handling(self):
        """测试URL验证的异常处理"""
        validator = ConfigValidator()

        # 创建一个会导致urlparse抛出异常的URL
        # 实际上，urlparse很少抛出异常，但我们可以测试边界情况
        # 例如None值或其他特殊值

        # 测试空字符串（已经在test_validate_url_invalid中测试）
        assert validator._validate_url("") is False

        # 测试None值（如果传入None）
        # 但由于类型检查，这不太可能发生
        # 我们可以测试一个会导致异常的URL格式
        # 实际上，urlparse对大多数输入都很宽容

        # 更实际的方法是测试一个会导致urlparse返回无效结果的URL
        # 但根据代码逻辑，只要result.scheme和result.netloc都存在就返回True
        # 所以异常处理主要是防御性编程

        # 让我们测试一个会导致异常的边界情况
        # 由于urlparse的健壮性，我们需要通过mock来测试
        from unittest.mock import patch

        with patch("jjz_alert.config.validation.urlparse") as mock_parse:
            mock_parse.side_effect = Exception("解析失败")
            result = validator._validate_url("http://example.com")
            assert result is False
