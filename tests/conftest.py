"""
pytest 配置和夹具(fixtures)

提供测试所需的通用夹具和配置
"""

import asyncio
import os
from unittest.mock import Mock, AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio

from jjz_alert.config.config import AppConfig, JJZAccount, JJZConfig
from jjz_alert.config.redis.connection import RedisConnectionManager
from jjz_alert.service.cache.cache_service import CacheService


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环供整个测试会话使用"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def fake_redis():
    """提供假Redis实例用于测试"""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.aclose()


@pytest_asyncio.fixture
async def mock_redis_manager(fake_redis):
    """Mock Redis连接管理器"""
    manager = Mock(spec=RedisConnectionManager)
    manager.client = fake_redis
    manager.initialize = AsyncMock(return_value=True)
    manager.close = AsyncMock()
    manager.health_check = AsyncMock(return_value={"status": "healthy"})

    with patch("jjz_alert.config.redis.connection.redis_manager", manager):
        yield manager


@pytest_asyncio.fixture
async def cache_service(fake_redis):
    """提供测试用的缓存服务"""
    # Mock Redis operations to use fake redis
    with patch(
        "jjz_alert.service.cache.cache_service.RedisOperations"
    ) as mock_ops_class:
        mock_ops = Mock()
        mock_ops.set = AsyncMock(return_value=True)
        mock_ops.get = AsyncMock(return_value=None)
        mock_ops.delete = AsyncMock(return_value=1)
        mock_ops.keys = AsyncMock(return_value=[])
        mock_ops.lpush = AsyncMock(return_value=1)
        mock_ops.ltrim = AsyncMock(return_value=True)
        mock_ops.expire = AsyncMock(return_value=True)
        mock_ops.lrange = AsyncMock(return_value=[])
        mock_ops.hincrby = AsyncMock(return_value=1)
        mock_ops.hgetall = AsyncMock(return_value={})

        mock_ops_class.return_value = mock_ops

        service = CacheService()
        yield service


@pytest.fixture
def sample_jjz_account():
    """提供测试用的进京证账户配置"""
    return JJZAccount(
        name="测试账户",
        jjz=JJZConfig(token="test_token_123", url="https://test.example.com/api"),
    )


@pytest.fixture
def sample_app_config(sample_jjz_account):
    """提供测试用的应用配置"""
    config = AppConfig()
    config.jjz_accounts = [sample_jjz_account]
    return config


@pytest.fixture
def mock_http_response():
    """Mock HTTP响应"""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {
        "state": "success",
        "result": {
            "applyRecords": [
                {
                    "plateNumber": "京A12345",
                    "status": "1",
                    "applyTime": "2025-08-15 10:00:00",
                    "validStartTime": "2025-08-15 00:00:00",
                    "validEndTime": "2025-08-20 23:59:59",
                }
            ]
        },
    }
    return mock_response


@pytest.fixture
def sample_traffic_rules():
    """提供测试用的限行规则数据"""
    return [
        {
            "limited_time": "2025年08月15日",
            "limited_number": "4和9",
            "description": "周四限行4和9",
        },
        {
            "limited_time": "2025年08月16日",
            "limited_number": "5和0",
            "description": "周五限行5和0",
        },
        {
            "limited_time": "2025年08月17日",
            "limited_number": "不限行",
            "description": "周六不限行",
        },
    ]


@pytest.fixture
def mock_traffic_response():
    """Mock限行规则API响应"""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {
        "state": "success",
        "result": [
            {
                "limitedTime": "2025年08月15日",
                "limitedNumber": "4和9",
                "description": "周四限行4和9",
            },
            {
                "limitedTime": "2025年08月16日",
                "limitedNumber": "5和0",
                "description": "周五限行5和0",
            },
            {
                "limitedTime": "2025年08月17日",
                "limitedNumber": "不限行",
                "description": "周六不限行",
            },
        ],
    }
    return mock_response


@pytest.fixture(autouse=True)
def mock_config_loading():
    """自动Mock配置加载，避免读取真实配置文件"""
    with patch("jjz_alert.config.config.config_manager.load_config") as mock_load:
        mock_config = AppConfig()
        mock_load.return_value = mock_config
        yield mock_load


@pytest.fixture
def temp_config_file(tmp_path):
    """创建临时配置文件"""
    config_content = """
global:
  log:
    level: DEBUG
  redis:
    host: localhost
    port: 6379
    db: 1
  cache:
    push_history_ttl: 86400

jjz_accounts:
  - name: 测试账户
    jjz:
      token: test_token
      url: https://test.example.com

plates:
  - plate: 京A12345
    display_name: 测试车辆
    notifications:

"""

    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content, encoding="utf-8")
    return str(config_file)


# 测试环境变量设置
@pytest.fixture(autouse=True)
def test_env():
    """设置测试环境变量"""
    original_env = os.environ.copy()

    # 设置测试环境标识
    os.environ["TESTING"] = "1"
    os.environ["LOG_LEVEL"] = "DEBUG"

    yield

    # 恢复原始环境变量
    os.environ.clear()
    os.environ.update(original_env)


# 异步测试辅助函数
@pytest.fixture
def async_mock():
    """创建异步Mock对象的工厂函数"""

    def _create_async_mock(*args, **kwargs):
        mock = AsyncMock(*args, **kwargs)
        return mock

    return _create_async_mock
