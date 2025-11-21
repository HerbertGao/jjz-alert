"""
RedisOperations 单元测试
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from jjz_alert.config.redis.operations import RedisOperations


@pytest.fixture
def redis_client():
    client = AsyncMock()
    return client


@pytest.mark.unit
class TestRedisOperations:
    @pytest.mark.asyncio
    async def test_set_with_ttl_uses_setex(self, redis_client):
        redis_client.setex.return_value = True
        ops = RedisOperations(client=redis_client)

        payload = {"foo": "bar"}
        result = await ops.set("demo", payload, ttl=60)

        assert result is True
        redis_client.setex.assert_awaited_once_with(
            "demo", 60, json.dumps(payload, ensure_ascii=False)
        )

    @pytest.mark.asyncio
    async def test_get_retries_then_recovers(self, monkeypatch, redis_client):
        other_client = AsyncMock()

        redis_client.get.side_effect = RuntimeError("boom")
        other_client.get.return_value = json.dumps(
            {"hello": "world"}, ensure_ascii=False
        )

        mock_get_client = AsyncMock(return_value=other_client)
        monkeypatch.setattr(
            "jjz_alert.config.redis.operations.get_redis_client", mock_get_client
        )
        monkeypatch.setattr(
            "jjz_alert.config.redis.operations.asyncio.sleep", AsyncMock()
        )

        ops = RedisOperations(client=redis_client)
        value = await ops.get("key1")

        assert value == {"hello": "world"}
        assert redis_client.get.await_count == 1
        assert other_client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_keys_normalizes_bytes(self, redis_client):
        redis_client.keys.return_value = [b"foo", "bar"]
        ops = RedisOperations(client=redis_client)

        result = await ops.keys("pattern")

        assert result == ["foo", "bar"]

    def test_serialize_and_deserialize_datetime(self, redis_client):
        ops = RedisOperations(client=redis_client)

        now = datetime(2025, 8, 15, 12, 0, 0)
        serialized = ops._serialize_value(now)
        assert json.loads(serialized) == now.isoformat()

        assert ops._deserialize_value(serialized) == now.isoformat()
        assert ops._deserialize_value("not-json") == "not-json"

    @pytest.mark.asyncio
    async def test_set_without_ttl(self, redis_client):
        """测试设置键值对 - 无TTL"""
        redis_client.set.return_value = True
        ops = RedisOperations(client=redis_client)

        result = await ops.set("key", "value")

        assert result is True
        redis_client.set.assert_awaited_once_with(
            "key", json.dumps("value", ensure_ascii=False)
        )

    @pytest.mark.asyncio
    async def test_set_failure(self, redis_client):
        """测试设置键值对失败"""
        redis_client.setex.side_effect = Exception("Set failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.set("key", "value", ttl=60)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_success(self, redis_client):
        """测试获取键值 - 成功"""
        redis_client.get.return_value = json.dumps({"data": "test"}, ensure_ascii=False)
        ops = RedisOperations(client=redis_client)

        result = await ops.get("key")

        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_get_not_found(self, redis_client):
        """测试获取键值 - 不存在"""
        redis_client.get.return_value = None
        ops = RedisOperations(client=redis_client)

        result = await ops.get("key", default="default_value")

        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_get_failure_after_retries(self, redis_client, monkeypatch):
        """测试获取键值 - 重试后仍失败"""
        redis_client.get.side_effect = RuntimeError("boom")
        other_client = AsyncMock()
        other_client.get.side_effect = RuntimeError("still failing")

        mock_get_client = AsyncMock(return_value=other_client)
        monkeypatch.setattr(
            "jjz_alert.config.redis.operations.get_redis_client", mock_get_client
        )
        monkeypatch.setattr(
            "jjz_alert.config.redis.operations.asyncio.sleep", AsyncMock()
        )

        ops = RedisOperations(client=redis_client)
        value = await ops.get("key1", default="default")

        assert value == "default"

    @pytest.mark.asyncio
    async def test_delete_success(self, redis_client):
        """测试删除键 - 成功"""
        redis_client.delete.return_value = 2
        ops = RedisOperations(client=redis_client)

        result = await ops.delete("key1", "key2")

        assert result == 2
        redis_client.delete.assert_awaited_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_delete_failure(self, redis_client):
        """测试删除键 - 失败"""
        redis_client.delete.side_effect = Exception("Delete failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.delete("key1")

        assert result == 0

    @pytest.mark.asyncio
    async def test_exists_true(self, redis_client):
        """测试检查键是否存在 - 存在"""
        redis_client.exists.return_value = 1
        ops = RedisOperations(client=redis_client)

        result = await ops.exists("key")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, redis_client):
        """测试检查键是否存在 - 不存在"""
        redis_client.exists.return_value = 0
        ops = RedisOperations(client=redis_client)

        result = await ops.exists("key")

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_failure(self, redis_client):
        """测试检查键是否存在 - 失败"""
        redis_client.exists.side_effect = Exception("Exists failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.exists("key")

        assert result is False

    @pytest.mark.asyncio
    async def test_expire_success(self, redis_client):
        """测试设置过期时间 - 成功"""
        redis_client.expire.return_value = True
        ops = RedisOperations(client=redis_client)

        result = await ops.expire("key", 60)

        assert result is True
        redis_client.expire.assert_awaited_once_with("key", 60)

    @pytest.mark.asyncio
    async def test_expire_failure(self, redis_client):
        """测试设置过期时间 - 失败"""
        redis_client.expire.side_effect = Exception("Expire failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.expire("key", 60)

        assert result is False

    @pytest.mark.asyncio
    async def test_ttl_success(self, redis_client):
        """测试获取剩余过期时间 - 成功"""
        redis_client.ttl.return_value = 30
        ops = RedisOperations(client=redis_client)

        result = await ops.ttl("key")

        assert result == 30

    @pytest.mark.asyncio
    async def test_ttl_failure(self, redis_client):
        """测试获取剩余过期时间 - 失败"""
        redis_client.ttl.side_effect = Exception("TTL failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.ttl("key")

        assert result == -1

    @pytest.mark.asyncio
    async def test_hset_success(self, redis_client):
        """测试设置哈希字段 - 成功"""
        redis_client.hset.return_value = 1
        ops = RedisOperations(client=redis_client)

        result = await ops.hset("hash_key", "field", "value")

        assert result is True
        redis_client.hset.assert_awaited_once_with(
            "hash_key", "field", json.dumps("value", ensure_ascii=False)
        )

    @pytest.mark.asyncio
    async def test_hset_failure(self, redis_client):
        """测试设置哈希字段 - 失败"""
        redis_client.hset.side_effect = Exception("HSET failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hset("hash_key", "field", "value")

        assert result is False

    @pytest.mark.asyncio
    async def test_hget_success(self, redis_client):
        """测试获取哈希字段 - 成功"""
        redis_client.hget.return_value = json.dumps(
            {"data": "test"}, ensure_ascii=False
        )
        ops = RedisOperations(client=redis_client)

        result = await ops.hget("hash_key", "field")

        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_hget_not_found(self, redis_client):
        """测试获取哈希字段 - 不存在"""
        redis_client.hget.return_value = None
        ops = RedisOperations(client=redis_client)

        result = await ops.hget("hash_key", "field", default="default")

        assert result == "default"

    @pytest.mark.asyncio
    async def test_hget_failure(self, redis_client):
        """测试获取哈希字段 - 失败"""
        redis_client.hget.side_effect = Exception("HGET failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hget("hash_key", "field", default="default")

        assert result == "default"

    @pytest.mark.asyncio
    async def test_hgetall_success(self, redis_client):
        """测试获取所有哈希字段 - 成功"""
        redis_client.hgetall.return_value = {
            "field1": json.dumps("value1", ensure_ascii=False),
            "field2": json.dumps("value2", ensure_ascii=False),
        }
        ops = RedisOperations(client=redis_client)

        result = await ops.hgetall("hash_key")

        assert result == {"field1": "value1", "field2": "value2"}

    @pytest.mark.asyncio
    async def test_hgetall_with_bytes_keys(self, redis_client):
        """测试获取所有哈希字段 - 字节键"""
        redis_client.hgetall.return_value = {
            b"field1": json.dumps("value1", ensure_ascii=False),
            "field2": json.dumps("value2", ensure_ascii=False),
        }
        ops = RedisOperations(client=redis_client)

        result = await ops.hgetall("hash_key")

        assert result == {"field1": "value1", "field2": "value2"}

    @pytest.mark.asyncio
    async def test_hgetall_failure(self, redis_client):
        """测试获取所有哈希字段 - 失败"""
        redis_client.hgetall.side_effect = Exception("HGETALL failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hgetall("hash_key")

        assert result == {}

    @pytest.mark.asyncio
    async def test_hmset_success(self, redis_client):
        """测试批量设置哈希字段 - 成功"""
        redis_client.hset.return_value = True
        ops = RedisOperations(client=redis_client)

        mapping = {"field1": "value1", "field2": "value2"}
        result = await ops.hmset("hash_key", mapping)

        assert result is True
        redis_client.hset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hmset_failure(self, redis_client):
        """测试批量设置哈希字段 - 失败"""
        redis_client.hset.side_effect = Exception("HMSET failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hmset("hash_key", {"field": "value"})

        assert result is False

    @pytest.mark.asyncio
    async def test_hdel_success(self, redis_client):
        """测试删除哈希字段 - 成功"""
        redis_client.hdel.return_value = 2
        ops = RedisOperations(client=redis_client)

        result = await ops.hdel("hash_key", "field1", "field2")

        assert result == 2

    @pytest.mark.asyncio
    async def test_hdel_failure(self, redis_client):
        """测试删除哈希字段 - 失败"""
        redis_client.hdel.side_effect = Exception("HDEL failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hdel("hash_key", "field1")

        assert result == 0

    @pytest.mark.asyncio
    async def test_hexists_true(self, redis_client):
        """测试检查哈希字段是否存在 - 存在"""
        redis_client.hexists.return_value = True
        ops = RedisOperations(client=redis_client)

        result = await ops.hexists("hash_key", "field")

        assert result is True

    @pytest.mark.asyncio
    async def test_hexists_false(self, redis_client):
        """测试检查哈希字段是否存在 - 不存在"""
        redis_client.hexists.return_value = False
        ops = RedisOperations(client=redis_client)

        result = await ops.hexists("hash_key", "field")

        assert result is False

    @pytest.mark.asyncio
    async def test_hexists_failure(self, redis_client):
        """测试检查哈希字段是否存在 - 失败"""
        redis_client.hexists.side_effect = Exception("HEXISTS failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hexists("hash_key", "field")

        assert result is False

    @pytest.mark.asyncio
    async def test_hincrby_success(self, redis_client):
        """测试增加哈希字段值 - 成功"""
        redis_client.hincrby.return_value = 5
        ops = RedisOperations(client=redis_client)

        result = await ops.hincrby("hash_key", "field", 3)

        assert result == 5
        redis_client.hincrby.assert_awaited_once_with("hash_key", "field", 3)

    @pytest.mark.asyncio
    async def test_hincrby_failure(self, redis_client):
        """测试增加哈希字段值 - 失败"""
        redis_client.hincrby.side_effect = Exception("HINCRBY failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.hincrby("hash_key", "field", 1)

        assert result == 0

    @pytest.mark.asyncio
    async def test_lpush_success(self, redis_client):
        """测试从左侧插入列表元素 - 成功"""
        redis_client.lpush.return_value = 3
        ops = RedisOperations(client=redis_client)

        result = await ops.lpush("list_key", "value1", "value2", "value3")

        assert result == 3
        redis_client.lpush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lpush_failure(self, redis_client):
        """测试从左侧插入列表元素 - 失败"""
        redis_client.lpush.side_effect = Exception("LPUSH failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.lpush("list_key", "value")

        assert result == 0

    @pytest.mark.asyncio
    async def test_rpush_success(self, redis_client):
        """测试从右侧插入列表元素 - 成功"""
        redis_client.rpush.return_value = 3
        ops = RedisOperations(client=redis_client)

        result = await ops.rpush("list_key", "value1", "value2", "value3")

        assert result == 3
        redis_client.rpush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rpush_failure(self, redis_client):
        """测试从右侧插入列表元素 - 失败"""
        redis_client.rpush.side_effect = Exception("RPUSH failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.rpush("list_key", "value")

        assert result == 0

    @pytest.mark.asyncio
    async def test_lrange_success(self, redis_client):
        """测试获取列表范围内的元素 - 成功"""
        redis_client.lrange.return_value = [
            json.dumps("value1", ensure_ascii=False),
            json.dumps("value2", ensure_ascii=False),
        ]
        ops = RedisOperations(client=redis_client)

        result = await ops.lrange("list_key", 0, 1)

        assert result == ["value1", "value2"]

    @pytest.mark.asyncio
    async def test_lrange_failure(self, redis_client):
        """测试获取列表范围内的元素 - 失败"""
        redis_client.lrange.side_effect = Exception("LRANGE failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.lrange("list_key", 0, -1)

        assert result == []

    @pytest.mark.asyncio
    async def test_llen_success(self, redis_client):
        """测试获取列表长度 - 成功"""
        redis_client.llen.return_value = 5
        ops = RedisOperations(client=redis_client)

        result = await ops.llen("list_key")

        assert result == 5

    @pytest.mark.asyncio
    async def test_llen_failure(self, redis_client):
        """测试获取列表长度 - 失败"""
        redis_client.llen.side_effect = Exception("LLEN failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.llen("list_key")

        assert result == 0

    @pytest.mark.asyncio
    async def test_ltrim_success(self, redis_client):
        """测试修剪列表 - 成功"""
        redis_client.ltrim.return_value = True
        ops = RedisOperations(client=redis_client)

        result = await ops.ltrim("list_key", 0, 9)

        assert result is True
        redis_client.ltrim.assert_awaited_once_with("list_key", 0, 9)

    @pytest.mark.asyncio
    async def test_ltrim_failure(self, redis_client):
        """测试修剪列表 - 失败"""
        redis_client.ltrim.side_effect = Exception("LTRIM failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.ltrim("list_key", 0, 9)

        assert result is False

    @pytest.mark.asyncio
    async def test_keys_failure(self, redis_client):
        """测试获取匹配模式的键列表 - 失败"""
        redis_client.keys.side_effect = Exception("KEYS failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.keys("pattern")

        assert result == []

    @pytest.mark.asyncio
    async def test_ping_success_pong_string(self, redis_client):
        """测试Redis连接 - 成功（字符串PONG）"""
        redis_client.ping.return_value = "PONG"
        ops = RedisOperations(client=redis_client)

        result = await ops.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_success_pong_bytes(self, redis_client):
        """测试Redis连接 - 成功（字节PONG）"""
        redis_client.ping.return_value = b"PONG"
        ops = RedisOperations(client=redis_client)

        result = await ops.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_failure(self, redis_client):
        """测试Redis连接 - 失败"""
        redis_client.ping.side_effect = Exception("PING failed")
        ops = RedisOperations(client=redis_client)

        result = await ops.ping()

        assert result is False

    def test_serialize_primitive_types(self, redis_client):
        """测试序列化基本类型"""
        ops = RedisOperations(client=redis_client)

        assert ops._serialize_value("string") == json.dumps(
            "string", ensure_ascii=False
        )
        assert ops._serialize_value(123) == json.dumps(123, ensure_ascii=False)
        assert ops._serialize_value(45.6) == json.dumps(45.6, ensure_ascii=False)
        assert ops._serialize_value(True) == json.dumps(True, ensure_ascii=False)

    def test_serialize_complex_types(self, redis_client):
        """测试序列化复杂类型"""
        ops = RedisOperations(client=redis_client)

        complex_obj = {"key": "value", "list": [1, 2, 3]}
        serialized = ops._serialize_value(complex_obj)
        assert json.loads(serialized) == complex_obj

    def test_deserialize_json(self, redis_client):
        """测试反序列化JSON"""
        ops = RedisOperations(client=redis_client)

        json_str = json.dumps({"key": "value"}, ensure_ascii=False)
        result = ops._deserialize_value(json_str)
        assert result == {"key": "value"}

    def test_deserialize_invalid_json(self, redis_client):
        """测试反序列化无效JSON"""
        ops = RedisOperations(client=redis_client)

        result = ops._deserialize_value("not a json string")
        assert result == "not a json string"

    @pytest.mark.asyncio
    async def test_get_client_from_global(self, monkeypatch):
        """测试从全局获取客户端"""
        mock_client = AsyncMock()
        mock_get_client = AsyncMock(return_value=mock_client)
        monkeypatch.setattr(
            "jjz_alert.config.redis.operations.get_redis_client", mock_get_client
        )

        ops = RedisOperations(client=None)
        client = await ops._get_client()

        assert client == mock_client
        mock_get_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_client_from_instance(self, redis_client):
        """测试从实例获取客户端"""
        ops = RedisOperations(client=redis_client)
        client = await ops._get_client()

        assert client == redis_client
