"""
Redis连接管理单元测试
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from redis.exceptions import ConnectionError, TimeoutError

from jjz_alert.config import RedisConfig
from jjz_alert.config.redis.connection import (
    RedisConnectionManager,
    get_redis_client,
    init_redis,
    close_redis,
    redis_client,
    redis_manager,
)
from jjz_alert.config.redis.redis_errors import (
    RedisConnectionError,
    RedisTimeoutError,
)


@pytest.mark.unit
class TestRedisConnectionManager:
    """Redis连接管理器测试"""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """测试成功初始化连接"""
        config = RedisConfig(host="localhost", port=6379, db=0)
        manager = RedisConnectionManager(config=config)

        with patch.object(
            manager, "_test_connection", new_callable=AsyncMock
        ) as mock_test:
            mock_test.return_value = None
            with patch(
                "jjz_alert.config.redis.connection.aioredis.ConnectionPool"
            ) as mock_pool_class:
                with patch(
                    "jjz_alert.config.redis.connection.aioredis.Redis"
                ) as mock_redis_class:
                    with patch(
                        "jjz_alert.config.redis.connection.redis.Redis"
                    ) as mock_sync_redis_class:
                        mock_pool = AsyncMock()
                        mock_pool_class.return_value = mock_pool
                        mock_client = AsyncMock()
                        mock_redis_class.return_value = mock_client
                        mock_sync_client = Mock()
                        mock_sync_redis_class.return_value = mock_sync_client

                        result = await manager.initialize()

                        assert result is True
                        assert manager._pool is not None
                        assert manager._client is not None
                        assert manager._sync_client is not None
                        mock_test.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        """测试初始化失败"""
        config = RedisConfig(host="invalid", port=6379, db=0)
        manager = RedisConnectionManager(config=config)

        with patch(
            "jjz_alert.config.redis.connection.aioredis.ConnectionPool"
        ) as mock_pool_class:
            mock_pool_class.side_effect = Exception("Connection failed")
            with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
                result = await manager.initialize()

                assert result is False
                mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_with_existing_pool(self):
        """测试已有连接池时的初始化"""
        config = RedisConfig(host="localhost", port=6379, db=0)
        manager = RedisConnectionManager(config=config)

        # 先创建一个连接池
        mock_pool = AsyncMock()
        manager._pool = mock_pool
        manager._loop = asyncio.get_running_loop()

        result = await manager.initialize()
        assert result is True  # 应该直接返回True，不重新创建

    @pytest.mark.asyncio
    async def test_initialize_with_different_event_loop(self):
        """测试事件循环变化时重新初始化"""
        config = RedisConfig(host="localhost", port=6379, db=0)
        manager = RedisConnectionManager(config=config)

        # 创建旧的事件循环
        old_loop = asyncio.new_event_loop()
        manager._pool = AsyncMock()
        manager._loop = old_loop

        with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
            with patch.object(manager, "_test_connection", new_callable=AsyncMock):
                with patch("jjz_alert.config.redis.connection.aioredis.ConnectionPool"):
                    with patch("jjz_alert.config.redis.connection.aioredis.Redis"):
                        with patch("jjz_alert.config.redis.connection.redis.Redis"):
                            result = await manager.initialize()
                            assert result is True
                            mock_close.assert_awaited_once()

        old_loop.close()

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """测试连接测试成功"""
        manager = RedisConnectionManager()
        manager._client = AsyncMock()
        manager._client.ping = AsyncMock(return_value=True)

        await manager._test_connection()
        manager._client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """测试连接测试失败"""
        manager = RedisConnectionManager()
        manager._client = AsyncMock()
        manager._client.ping = AsyncMock(side_effect=Exception("Connection failed"))

        with pytest.raises(ConnectionError):
            await manager._test_connection()

    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        manager = RedisConnectionManager()
        manager._client = AsyncMock()
        manager._pool = AsyncMock()
        manager._sync_client = Mock()

        await manager.close()

        assert manager._client is None
        assert manager._pool is None
        assert manager._sync_client is None

    @pytest.mark.asyncio
    async def test_close_with_exception(self):
        """测试关闭连接时发生异常"""
        manager = RedisConnectionManager()
        manager._client = AsyncMock()
        manager._client.aclose = AsyncMock(side_effect=Exception("Close error"))
        manager._pool = AsyncMock()
        manager._sync_client = Mock()

        # 应该不抛出异常
        await manager.close()

    @pytest.mark.asyncio
    async def test_client_property_success(self):
        """测试获取客户端属性成功"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client

        assert manager.client == mock_client

    def test_client_property_failure(self):
        """测试获取客户端属性失败"""
        manager = RedisConnectionManager()
        manager._client = None

        with pytest.raises(RuntimeError, match="Redis连接未初始化"):
            _ = manager.client

    @pytest.mark.asyncio
    async def test_sync_client_property_success(self):
        """测试获取同步客户端属性成功"""
        manager = RedisConnectionManager()
        mock_client = Mock()
        manager._sync_client = mock_client

        assert manager.sync_client == mock_client

    def test_sync_client_property_failure(self):
        """测试获取同步客户端属性失败"""
        manager = RedisConnectionManager()
        manager._sync_client = None

        with pytest.raises(RuntimeError, match="Redis连接未初始化"):
            _ = manager.sync_client

    @pytest.mark.asyncio
    async def test_get_client_context_manager_success(self):
        """测试获取客户端上下文管理器成功"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client

        async with manager.get_client() as client:
            assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_client_context_manager_auto_init(self):
        """测试上下文管理器自动初始化"""
        manager = RedisConnectionManager()
        manager._client = None

        mock_client = AsyncMock()
        with patch.object(manager, "initialize", new_callable=AsyncMock) as mock_init:

            async def init_side_effect():
                manager._client = mock_client
                return True

            mock_init.side_effect = init_side_effect

            async with manager.get_client() as client:
                assert client == mock_client
            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_client_context_manager_connection_error(self):
        """测试上下文管理器处理连接错误"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client

        with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
            with patch.object(
                manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = True

                # 模拟在使用客户端时抛出异常
                # 异常会在yield之后被捕获
                try:
                    async with manager.get_client() as client:
                        # 在上下文内部抛出异常来模拟连接错误
                        raise ConnectionError("Connection failed")
                except ConnectionError:
                    # 异常应该被重新抛出
                    pass

                # 应该尝试重新连接
                mock_close.assert_awaited()
                mock_init.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_client_context_manager_timeout_error(self):
        """测试上下文管理器处理超时错误"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client

        with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
            with patch.object(
                manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = True

                # 模拟在使用客户端时抛出异常
                # 异常会在yield之后被捕获
                try:
                    async with manager.get_client() as client:
                        # 在上下文内部抛出异常来模拟超时错误
                        raise TimeoutError("Timeout")
                except TimeoutError:
                    # 异常应该被重新抛出
                    pass

                mock_close.assert_awaited()
                mock_init.assert_awaited()

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """测试健康检查 - 健康状态"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client
        manager.config = RedisConfig(host="localhost", port=6379, db=0)

        mock_client.ping = AsyncMock(return_value=True)
        mock_client.info = AsyncMock(
            return_value={
                "redis_version": "7.0.0",
                "used_memory_human": "1M",
                "connected_clients": 1,
                "total_commands_processed": 100,
                "keyspace_hits": 50,
                "keyspace_misses": 10,
            }
        )

        # Mock event loop time
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop_instance = Mock()
            mock_loop_instance.time.side_effect = [0.0, 0.001]  # 1ms
            mock_loop.return_value = mock_loop_instance

            health = await manager.health_check()

            assert health["status"] == "healthy"
            assert "ping_ms" in health
            assert health["redis_version"] == "7.0.0"

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self):
        """测试健康检查 - 未连接状态"""
        manager = RedisConnectionManager()
        manager._client = None

        health = await manager.health_check()

        assert health["status"] == "disconnected"
        assert "error" in health

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """测试健康检查 - 不健康状态"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client
        manager.config = RedisConfig(host="localhost", port=6379, db=0)

        mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))

        health = await manager.health_check()

        assert health["status"] == "unhealthy"
        assert "error" in health

    @pytest.mark.asyncio
    async def test_flush_db_without_confirm(self):
        """测试清空数据库 - 未确认"""
        manager = RedisConnectionManager()
        manager._client = AsyncMock()

        with pytest.raises(ValueError, match="必须明确确认才能清空数据库"):
            await manager.flush_db(confirm=False)

    @pytest.mark.asyncio
    async def test_flush_db_with_confirm(self):
        """测试清空数据库 - 已确认"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client
        manager.config = RedisConfig(host="localhost", port=6379, db=0)

        mock_client.flushdb = AsyncMock(return_value=True)

        await manager.flush_db(confirm=True)

        mock_client.flushdb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_db_with_exception(self):
        """测试清空数据库 - 发生异常"""
        manager = RedisConnectionManager()
        mock_client = AsyncMock()
        manager._client = mock_client
        manager.config = RedisConfig(host="localhost", port=6379, db=0)

        mock_client.flushdb = AsyncMock(side_effect=Exception("Flush failed"))

        with pytest.raises(Exception):
            await manager.flush_db(confirm=True)


@pytest.mark.unit
class TestRedisErrorClasses:
    """Redis错误类测试"""

    def test_redis_connection_error(self):
        """测试Redis连接错误类"""
        error = RedisConnectionError("Connection failed", {"host": "localhost"})
        assert str(error) == "Connection failed"
        assert error.details == {"host": "localhost"}

    def test_redis_timeout_error(self):
        """测试Redis超时错误类"""
        error = RedisTimeoutError("Timeout", {"timeout": 5})
        assert str(error) == "Timeout"
        assert error.details == {"timeout": 5}


@pytest.mark.unit
class TestRedisHelperFunctions:
    """Redis辅助函数测试"""

    @pytest.mark.asyncio
    async def test_get_redis_client_new_connection(self):
        """测试获取Redis客户端 - 新连接"""
        with patch.object(redis_manager, "_client", None):
            with patch.object(
                redis_manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = True
                mock_client = AsyncMock()
                redis_manager._client = mock_client

                client = await get_redis_client()

                assert client == mock_client
                mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_redis_client_existing_connection(self):
        """测试获取Redis客户端 - 已有连接"""
        mock_client = AsyncMock()
        redis_manager._client = mock_client
        redis_manager._loop = asyncio.get_running_loop()

        client = await get_redis_client()

        assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_redis_client_different_loop(self):
        """测试获取Redis客户端 - 不同事件循环"""
        old_loop = asyncio.new_event_loop()
        redis_manager._client = AsyncMock()
        redis_manager._loop = old_loop

        with patch.object(
            redis_manager, "initialize", new_callable=AsyncMock
        ) as mock_init:
            mock_init.return_value = True

            client = await get_redis_client()

            assert client is not None
            mock_init.assert_awaited_once()

        old_loop.close()

    @pytest.mark.asyncio
    async def test_init_redis(self):
        """测试初始化Redis快捷函数"""
        with patch.object(
            redis_manager, "initialize", new_callable=AsyncMock
        ) as mock_init:
            mock_init.return_value = True

            result = await init_redis()

            assert result is True
            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_redis(self):
        """测试关闭Redis快捷函数"""
        with patch.object(redis_manager, "close", new_callable=AsyncMock) as mock_close:
            await close_redis()

            mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_client_context_manager(self):
        """测试Redis客户端上下文管理器"""
        with patch.object(redis_manager, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

            async with redis_client() as client:
                assert client == mock_client
