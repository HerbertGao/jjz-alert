"""
Redis连接管理模块

提供Redis连接池和基础操作支持
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

import redis
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, TimeoutError

from config import get_redis_config, RedisConfig


class RedisConnectionManager:
    """Redis连接管理器"""

    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or get_redis_config()
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None
        self._sync_client: Optional[redis.Redis] = None
        self._connection_lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """初始化Redis连接"""
        try:
            async with self._connection_lock:
                if self._pool is not None:
                    return True

                # 创建连接池
                self._pool = aioredis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    max_connections=self.config.connection_pool_size,
                    retry_on_timeout=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    health_check_interval=30
                )

                # 创建异步客户端
                self._client = aioredis.Redis(
                    connection_pool=self._pool,
                    decode_responses=True
                )

                # 创建同步客户端（用于某些同步操作）
                self._sync_client = redis.Redis(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )

                # 测试连接
                await self._test_connection()

                logging.info(f"Redis连接初始化成功: {self.config.host}:{self.config.port}/{self.config.db}")
                return True

        except Exception as e:
            logging.error(f"Redis连接初始化失败: {e}")
            await self.close()
            return False

    async def _test_connection(self):
        """测试Redis连接"""
        try:
            await self._client.ping()
            logging.debug("Redis连接测试成功")
        except Exception as e:
            raise ConnectionError(f"Redis连接测试失败: {e}")

    async def close(self):
        """关闭Redis连接"""
        try:
            if self._client:
                await self._client.aclose()
                self._client = None

            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            if self._sync_client:
                self._sync_client.close()
                self._sync_client = None

            logging.info("Redis连接已关闭")

        except Exception as e:
            logging.error(f"关闭Redis连接时发生错误: {e}")

    @property
    def client(self) -> aioredis.Redis:
        """获取异步Redis客户端"""
        if self._client is None:
            raise RuntimeError("Redis连接未初始化")
        return self._client

    @property
    def sync_client(self) -> redis.Redis:
        """获取同步Redis客户端"""
        if self._sync_client is None:
            raise RuntimeError("Redis连接未初始化")
        return self._sync_client

    @asynccontextmanager
    async def get_client(self):
        """获取Redis客户端的上下文管理器"""
        if self._client is None:
            await self.initialize()

        try:
            yield self._client
        except (ConnectionError, TimeoutError) as e:
            logging.error(f"Redis操作失败: {e}")
            # 尝试重新连接
            await self.close()
            await self.initialize()
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Redis健康检查"""
        try:
            if self._client is None:
                return {
                    'status': 'disconnected',
                    'error': 'Redis客户端未初始化'
                }

            # 测试连接
            start_time = asyncio.get_event_loop().time()
            await self._client.ping()
            ping_time = (asyncio.get_event_loop().time() - start_time) * 1000

            # 获取Redis信息
            info = await self._client.info()

            return {
                'status': 'healthy',
                'ping_ms': round(ping_time, 2),
                'redis_version': info.get('redis_version'),
                'used_memory_human': info.get('used_memory_human'),
                'connected_clients': info.get('connected_clients'),
                'total_commands_processed': info.get('total_commands_processed'),
                'keyspace_hits': info.get('keyspace_hits'),
                'keyspace_misses': info.get('keyspace_misses'),
                'config': {
                    'host': self.config.host,
                    'port': self.config.port,
                    'db': self.config.db
                }
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

    async def flush_db(self, confirm: bool = False):
        """清空当前数据库（谨慎使用）"""
        if not confirm:
            raise ValueError("必须明确确认才能清空数据库")

        try:
            await self._client.flushdb()
            logging.warning(f"已清空Redis数据库 {self.config.db}")
        except Exception as e:
            logging.error(f"清空Redis数据库失败: {e}")
            raise


class RedisError(Exception):
    """Redis操作错误"""
    pass


class RedisConnectionError(RedisError):
    """Redis连接错误"""
    pass


class RedisTimeoutError(RedisError):
    """Redis超时错误"""
    pass


# 全局Redis连接管理器实例
redis_manager = RedisConnectionManager()


async def get_redis_client() -> aioredis.Redis:
    """获取Redis客户端的快捷函数"""
    if redis_manager._client is None:
        await redis_manager.initialize()
    return redis_manager.client


async def init_redis() -> bool:
    """初始化Redis连接的快捷函数"""
    return await redis_manager.initialize()


async def close_redis():
    """关闭Redis连接的快捷函数"""
    await redis_manager.close()


@asynccontextmanager
async def redis_client():
    """Redis客户端上下文管理器"""
    async with redis_manager.get_client() as client:
        yield client
