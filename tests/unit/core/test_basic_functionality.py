"""
基础功能单元测试

验证核心模块的基本功能
"""

from datetime import date
from unittest.mock import Mock, AsyncMock, patch

import pytest

from jjz_alert.service.cache.cache_service import CacheService
from jjz_alert.service.jjz.jjz_service import JJZService, JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.traffic.traffic_service import TrafficService, TrafficRule


@pytest.mark.unit
class TestBasicFunctionality:
    """基础功能测试类"""

    def test_jjz_status_creation(self):
        """测试JJZStatus数据模型创建"""
        status = JJZStatus(
            plate="京A12345",
            status=JJZStatusEnum.VALID.value,
            apply_time="2025-08-15 10:00:00",
            valid_start="2025-08-15 00:00:00",
            valid_end="2025-08-20 23:59:59",
            days_remaining=5,
            data_source="api",
        )

        assert status.plate == "京A12345"
        assert status.status == JJZStatusEnum.VALID.value
        assert status.days_remaining == 5
        assert status.data_source == "api"

        # 测试转换为字典
        status_dict = status.to_dict()
        assert status_dict["plate"] == "京A12345"
        assert status_dict["status"] == JJZStatusEnum.VALID.value

    def test_traffic_rule_creation(self):
        """测试TrafficRule数据模型创建"""
        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="4和9",
            limited_time="2025年08月15日",
            is_limited=True,
            data_source="api",
        )

        assert rule.date == date(2025, 8, 15)
        assert rule.limited_numbers == "4和9"
        assert rule.is_limited is True
        assert rule.data_source == "api"

        # 测试转换为字典
        rule_dict = rule.to_dict()
        assert rule_dict["date"] == "2025-08-15"
        assert rule_dict["limited_numbers"] == "4和9"

    def test_plate_tail_number_extraction(self):
        """测试车牌尾号提取"""
        # 使用TrafficService的方法测试
        with patch(
            "jjz_alert.service.cache.cache_service.RedisOperations"
        ) as mock_ops_class:
            mock_ops = Mock()
            mock_ops_class.return_value = mock_ops

            traffic_service = TrafficService()

            assert traffic_service._get_plate_tail_number("京A12345") == "5"
            assert traffic_service._get_plate_tail_number("京B67890") == "0"
            assert (
                traffic_service._get_plate_tail_number("京C1111A") == "0"
            )  # 字母按0处理
            assert traffic_service._get_plate_tail_number("") == "0"  # 空字符串

    def test_cache_service_initialization(self):
        """测试缓存服务初始化"""
        with patch(
            "jjz_alert.service.cache.cache_service.RedisOperations"
        ) as mock_ops_class:
            mock_ops = Mock()
            mock_ops_class.return_value = mock_ops

            cache_service = CacheService()

            assert cache_service.JJZ_PREFIX == "jjz:"
            assert cache_service.TRAFFIC_PREFIX == "traffic:"
            assert cache_service.PUSH_HISTORY_PREFIX == "push_history:"

    def test_jjz_service_initialization(self):
        """测试进京证服务初始化"""
        mock_cache = Mock()
        jjz_service = JJZService(mock_cache)

        assert jjz_service.cache_service == mock_cache
        assert jjz_service._accounts == []
        assert jjz_service._last_config_load is None

    def test_traffic_service_initialization(self):
        """测试限行服务初始化"""
        mock_cache = Mock()
        traffic_service = TrafficService(mock_cache)

        assert traffic_service.cache_service == mock_cache
        assert traffic_service._limit_rules_url.startswith("https://")
        assert traffic_service._max_retries == 3

    @pytest.mark.asyncio
    async def test_cache_service_mock_operations(self):
        """测试缓存服务模拟操作"""
        with patch(
            "jjz_alert.service.cache.cache_service.RedisOperations"
        ) as mock_ops_class:
            mock_ops = Mock()
            mock_ops.set = AsyncMock(return_value=True)
            mock_ops.get = AsyncMock(return_value={"test": "data"})
            mock_ops.delete = AsyncMock(return_value=1)
            mock_ops.hincrby = AsyncMock(return_value=1)
            mock_ops.expire = AsyncMock(return_value=True)
            mock_ops_class.return_value = mock_ops

            cache_service = CacheService()

            # 测试基础操作
            result = await cache_service.cache_jjz_data("京A12345", {"status": "valid"})
            assert result is True

            data = await cache_service.get_jjz_data("京A12345")
            assert data == {"test": "data"}

            deleted = await cache_service.delete_jjz_data("京A12345")
            assert deleted is True

    @pytest.mark.asyncio
    async def test_jjz_service_mock_operations(self):
        """测试进京证服务模拟操作"""
        with patch(
            "jjz_alert.service.cache.cache_service.RedisOperations"
        ) as mock_ops_class:
            mock_ops = Mock()
            mock_ops.get = AsyncMock(return_value=None)  # 缓存未命中
            mock_ops_class.return_value = mock_ops

            cache_service = CacheService()
            jjz_service = JJZService(cache_service)

            # Mock账户加载
            with patch.object(jjz_service, "_load_accounts") as mock_load:
                mock_load.return_value = []  # 无账户

                status = await jjz_service.get_jjz_status("京A12345")

                assert status.plate == "京A12345"
                assert status.status == "error"
                assert "未配置进京证账户" in status.error_message

    def test_configuration_validation(self):
        """测试配置验证"""
        # 测试导入配置相关模块
        try:
            from jjz_alert.config.config import JJZAccount, JJZConfig, AppConfig
            from jjz_alert.config.validation import ConfigValidator

            # 创建测试配置对象
            jjz_config = JJZConfig(token="test_token", url="https://test.com")
            jjz_account = JJZAccount(name="测试账户", jjz=jjz_config)

            assert jjz_account.name == "测试账户"
            assert jjz_account.jjz.token == "test_token"
            assert jjz_account.jjz.url == "https://test.com"

        except ImportError as e:
            pytest.fail(f"配置模块导入失败: {e}")

    def test_redis_operations_import(self):
        """测试Redis操作模块导入"""
        try:
            from jjz_alert.config.redis.connection import RedisConnectionManager
            from jjz_alert.config.redis.operations import RedisOperations

            # 测试基础创建（不连接）
            manager = RedisConnectionManager()
            operations = RedisOperations()

            assert manager is not None
            assert operations is not None

        except ImportError as e:
            pytest.fail(f"Redis模块导入失败: {e}")

    def test_utility_functions(self):
        """测试工具函数"""
        from jjz_alert.service.jjz.jjz_service import JJZService

        with patch("jjz_alert.service.cache.cache_service.RedisOperations"):
            service = JJZService()

            # 测试日期计算
            with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 8, 15)

                status = service._determine_status(
                    "1", "审核通过(生效中)", "2025-08-20", "2025-08-15"
                )
                assert status == JJZStatusEnum.VALID.value

                status = service._determine_status(
                    "1", "审核通过(生效中)", "2025-08-10", "2025-08-05"
                )
                assert status == JJZStatusEnum.EXPIRED.value
