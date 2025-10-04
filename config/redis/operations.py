"""
Redis基础操作模块

提供常用的Redis操作封装
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from config.redis.connection import get_redis_client


class RedisOperations:
    """Redis基础操作类"""

    def __init__(self, client: Optional[aioredis.Redis] = None):
        self._client = client

    async def _get_client(self) -> aioredis.Redis:
        """获取Redis客户端"""
        if self._client is None:
            return await get_redis_client()
        return self._client

    # =============================================================================
    # 字符串操作
    # =============================================================================

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置键值对"""
        try:
            client = await self._get_client()

            # 序列化值
            serialized_value = self._serialize_value(value)

            # 设置值
            if ttl:
                result = await client.setex(key, ttl, serialized_value)
            else:
                result = await client.set(key, serialized_value)

            return bool(result)

        except Exception as e:
            logging.error(f"Redis SET操作失败: key={key}, error={e}")
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        """获取键值"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                client = await self._get_client()
                value = await client.get(key)

                if value is None:
                    return default

                return self._deserialize_value(value)

            except Exception as e:
                if attempt < max_retries:
                    logging.warning(f"Redis GET操作失败，重试 {attempt + 1}/{max_retries}: key={key}, error={e}")
                    # 重新获取客户端
                    self._client = None
                    await asyncio.sleep(0.1)  # 短暂等待
                else:
                    logging.error(f"Redis GET操作失败: key={key}, error={e}")
                    return default

    async def delete(self, *keys: str) -> int:
        """删除键"""
        try:
            client = await self._get_client()
            return await client.delete(*keys)
        except Exception as e:
            logging.error(f"Redis DELETE操作失败: keys={keys}, error={e}")
            return 0

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            client = await self._get_client()
            return bool(await client.exists(key))
        except Exception as e:
            logging.error(f"Redis EXISTS操作失败: key={key}, error={e}")
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """设置键过期时间"""
        try:
            client = await self._get_client()
            return bool(await client.expire(key, ttl))
        except Exception as e:
            logging.error(f"Redis EXPIRE操作失败: key={key}, ttl={ttl}, error={e}")
            return False

    async def ttl(self, key: str) -> int:
        """获取键剩余过期时间"""
        try:
            client = await self._get_client()
            return await client.ttl(key)
        except Exception as e:
            logging.error(f"Redis TTL操作失败: key={key}, error={e}")
            return -1

    # =============================================================================
    # 哈希操作
    # =============================================================================

    async def hset(self, key: str, field: str, value: Any) -> bool:
        """设置哈希字段"""
        try:
            client = await self._get_client()
            serialized_value = self._serialize_value(value)
            result = await client.hset(key, field, serialized_value)
            return bool(result)
        except Exception as e:
            logging.error(f"Redis HSET操作失败: key={key}, field={field}, error={e}")
            return False

    async def hget(self, key: str, field: str, default: Any = None) -> Any:
        """获取哈希字段"""
        try:
            client = await self._get_client()
            value = await client.hget(key, field)

            if value is None:
                return default

            return self._deserialize_value(value)
        except Exception as e:
            logging.error(f"Redis HGET操作失败: key={key}, field={field}, error={e}")
            return default

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """获取哈希所有字段"""
        try:
            client = await self._get_client()
            data = await client.hgetall(key)

            # 反序列化所有值
            result = {}
            for field, value in data.items():
                # 确保field是字符串类型
                field_str = field.decode('utf-8') if isinstance(field, bytes) else str(field)
                result[field_str] = self._deserialize_value(value)

            return result
        except Exception as e:
            logging.error(f"Redis HGETALL操作失败: key={key}, error={e}")
            return {}

    async def hmset(self, key: str, mapping: Dict[str, Any]) -> bool:
        """批量设置哈希字段"""
        try:
            client = await self._get_client()

            # 序列化所有值
            serialized_mapping = {}
            for field, value in mapping.items():
                serialized_mapping[field] = self._serialize_value(value)

            result = await client.hset(key, mapping=serialized_mapping)
            return True
        except Exception as e:
            logging.error(f"Redis HMSET操作失败: key={key}, error={e}")
            return False

    async def hdel(self, key: str, *fields: str) -> int:
        """删除哈希字段"""
        try:
            client = await self._get_client()
            return await client.hdel(key, *fields)
        except Exception as e:
            logging.error(f"Redis HDEL操作失败: key={key}, fields={fields}, error={e}")
            return 0

    async def hexists(self, key: str, field: str) -> bool:
        """检查哈希字段是否存在"""
        try:
            client = await self._get_client()
            return bool(await client.hexists(key, field))
        except Exception as e:
            logging.error(f"Redis HEXISTS操作失败: key={key}, field={field}, error={e}")
            return False

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """增加哈希字段的整数值"""
        try:
            client = await self._get_client()
            return await client.hincrby(key, field, amount)
        except Exception as e:
            logging.error(f"Redis HINCRBY操作失败: key={key}, field={field}, amount={amount}, error={e}")
            return 0

    # =============================================================================
    # 列表操作
    # =============================================================================

    async def lpush(self, key: str, *values: Any) -> int:
        """从左侧插入列表元素"""
        try:
            client = await self._get_client()
            serialized_values = [self._serialize_value(v) for v in values]
            return await client.lpush(key, *serialized_values)
        except Exception as e:
            logging.error(f"Redis LPUSH操作失败: key={key}, error={e}")
            return 0

    async def rpush(self, key: str, *values: Any) -> int:
        """从右侧插入列表元素"""
        try:
            client = await self._get_client()
            serialized_values = [self._serialize_value(v) for v in values]
            return await client.rpush(key, *serialized_values)
        except Exception as e:
            logging.error(f"Redis RPUSH操作失败: key={key}, error={e}")
            return 0

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围内的元素"""
        try:
            client = await self._get_client()
            values = await client.lrange(key, start, end)
            return [self._deserialize_value(v) for v in values]
        except Exception as e:
            logging.error(f"Redis LRANGE操作失败: key={key}, error={e}")
            return []

    async def llen(self, key: str) -> int:
        """获取列表长度"""
        try:
            client = await self._get_client()
            return await client.llen(key)
        except Exception as e:
            logging.error(f"Redis LLEN操作失败: key={key}, error={e}")
            return 0

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """修剪列表"""
        try:
            client = await self._get_client()
            result = await client.ltrim(key, start, end)
            return bool(result)
        except Exception as e:
            logging.error(f"Redis LTRIM操作失败: key={key}, error={e}")
            return False

    # =============================================================================
    # 工具方法
    # =============================================================================

    def _serialize_value(self, value: Any) -> str:
        """序列化值"""
        if isinstance(value, (str, int, float, bool)):
            return json.dumps(value, ensure_ascii=False)
        elif isinstance(value, datetime):
            return json.dumps(value.isoformat(), ensure_ascii=False)
        else:
            return json.dumps(value, ensure_ascii=False, default=str)

    def _deserialize_value(self, value: str) -> Any:
        """反序列化值"""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        try:
            client = await self._get_client()
            keys = await client.keys(pattern)

            # 确保返回的是字符串列表
            result = []
            for key in keys:
                if isinstance(key, bytes):
                    result.append(key.decode('utf-8'))
                else:
                    result.append(str(key))

            return result
        except Exception as e:
            logging.error(f"Redis KEYS操作失败: pattern={pattern}, error={e}")
            return []

    async def ping(self) -> bool:
        """测试Redis连接"""
        try:
            client = await self._get_client()
            result = await client.ping()
            return result == b'PONG' or result == 'PONG'
        except Exception as e:
            logging.error(f"Redis PING失败: {e}")
            return False


# 全局Redis操作实例
redis_ops = RedisOperations()
