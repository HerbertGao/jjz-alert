"""
Redis集成测试

测试与真实Redis实例的集成功能
"""

import asyncio
from datetime import date

import pytest
import pytest_asyncio

from config.redis.connection import RedisConnectionManager
from config.redis.operations import RedisOperations
from service.cache.cache_service import CacheService
from service.jjz.jjz_status import JJZStatusEnum


@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    """Redis集成测试类"""

    @pytest_asyncio.fixture
    async def real_redis_manager(self):
        """真实Redis连接管理器"""
        manager = RedisConnectionManager()
        success = await manager.initialize()
        if not success:
            pytest.skip("Redis连接失败，跳过集成测试")

        yield manager

        # 清理测试数据
        try:
            await manager.client.flushdb()
        except:
            pass
        await manager.close()

    @pytest_asyncio.fixture
    async def real_redis_ops(self, real_redis_manager):
        """真实Redis操作实例"""
        ops = RedisOperations(client=real_redis_manager.client)
        yield ops

    @pytest_asyncio.fixture
    async def real_cache_service(self, real_redis_ops):
        """真实缓存服务实例"""
        service = CacheService(real_redis_ops)
        yield service

    @pytest.mark.asyncio
    async def test_redis_connection_health(self, real_redis_manager):
        """测试Redis连接健康检查"""
        health = await real_redis_manager.health_check()

        assert health['status'] == 'healthy'
        assert 'ping_ms' in health
        assert 'redis_version' in health
        assert health['ping_ms'] < 100  # 延迟应该很低

    @pytest.mark.asyncio
    async def test_redis_basic_operations(self, real_redis_ops):
        """测试Redis基础操作"""
        key = "test:basic:key"
        value = {"test": "data", "number": 42}

        # 测试设置和获取
        success = await real_redis_ops.set(key, value, ttl=60)
        assert success is True

        retrieved = await real_redis_ops.get(key)
        assert retrieved == value

        # 测试删除
        deleted = await real_redis_ops.delete(key)
        assert deleted == 1

        # 验证删除成功
        retrieved = await real_redis_ops.get(key)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_redis_list_operations(self, real_redis_ops):
        """测试Redis列表操作"""
        key = "test:list:key"

        # 测试列表推入
        await real_redis_ops.lpush(key, {"item": 1})
        await real_redis_ops.lpush(key, {"item": 2})
        await real_redis_ops.lpush(key, {"item": 3})

        # 测试列表范围获取
        items = await real_redis_ops.lrange(key, 0, 2)
        assert len(items) == 3
        assert items[0]["item"] == 3  # 最新推入的在前面

        # 测试列表修剪
        await real_redis_ops.ltrim(key, 0, 1)
        items = await real_redis_ops.lrange(key, 0, -1)
        assert len(items) == 2

        # 清理
        await real_redis_ops.delete(key)

    @pytest.mark.asyncio
    async def test_redis_hash_operations(self, real_redis_ops):
        """测试Redis哈希操作"""
        key = "test:hash:key"

        # 测试哈希增量
        await real_redis_ops.hincrby(key, "counter1", 5)
        await real_redis_ops.hincrby(key, "counter2", 10)
        await real_redis_ops.hincrby(key, "counter1", 3)  # 再增加3

        # 测试获取所有哈希字段
        hash_data = await real_redis_ops.hgetall(key)
        assert hash_data["counter1"] == 8  # 5 + 3
        assert hash_data["counter2"] == 10

        # 清理
        await real_redis_ops.delete(key)

    @pytest.mark.asyncio
    async def test_redis_key_patterns(self, real_redis_ops):
        """测试Redis键模式查找"""
        # 创建测试键
        test_keys = [
            "test:pattern:jjz:京A12345",
            "test:pattern:jjz:京B67890",
            "test:pattern:traffic:2025-08-15",
            "test:pattern:other:data"
        ]

        for key in test_keys:
            await real_redis_ops.set(key, {"data": "test"})

        # 测试模式匹配
        jjz_keys = await real_redis_ops.keys("test:pattern:jjz:*")
        assert len(jjz_keys) == 2
        assert all("jjz" in key for key in jjz_keys)

        traffic_keys = await real_redis_ops.keys("test:pattern:traffic:*")
        assert len(traffic_keys) == 1
        assert "traffic" in traffic_keys[0]

        # 清理
        await real_redis_ops.delete(*test_keys)

    @pytest.mark.asyncio
    async def test_redis_expiration(self, real_redis_ops):
        """测试Redis键过期"""
        key = "test:expire:key"

        # 设置短期过期键
        await real_redis_ops.set(key, {"data": "test"}, ttl=1)

        # 立即检查存在
        value = await real_redis_ops.get(key)
        assert value is not None

        # 等待过期
        await asyncio.sleep(1.1)

        # 检查已过期
        value = await real_redis_ops.get(key)
        assert value is None

    @pytest.mark.asyncio
    async def test_cache_service_jjz_integration(self, real_cache_service):
        """测试缓存服务进京证数据集成"""
        plate = "京A12345"
        jjz_data = {
            "status": "valid",
            "apply_time": "2025-08-15 10:00:00",
            "valid_start": "2025-08-15 00:00:00",
            "valid_end": "2025-08-20 23:59:59",
            "days_remaining": 5
        }

        # 测试缓存数据
        success = await real_cache_service.cache_jjz_data(plate, jjz_data)
        assert success is True

        # 测试获取数据
        retrieved = await real_cache_service.get_jjz_data(plate)
        assert retrieved is not None
        assert retrieved["status"] == JJZStatusEnum.VALID.value
        assert "cached_at" in retrieved
        # 检查数据完整性
        assert retrieved["apply_time"] == jjz_data["apply_time"]
        assert retrieved["days_remaining"] == jjz_data["days_remaining"]

        # 测试获取所有车牌
        plates = await real_cache_service.get_all_jjz_plates()
        assert plate in plates

        # 测试删除数据
        deleted = await real_cache_service.delete_jjz_data(plate)
        assert deleted is True

        # 验证删除成功
        retrieved = await real_cache_service.get_jjz_data(plate)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cache_service_traffic_integration(self, real_cache_service):
        """测试缓存服务限行规则集成"""
        rules_data = [
            {
                "limited_time": "2025年08月15日",
                "limited_number": "4和9",
                "description": "周四限行"
            },
            {
                "limited_time": "2025年08月16日",
                "limited_number": "5和0",
                "description": "周五限行"
            }
        ]

        # 测试缓存规则
        success = await real_cache_service.cache_traffic_rules(rules_data)
        assert success is True

        # 测试获取特定日期规则
        target_date = date(2025, 8, 15)
        rule = await real_cache_service.get_traffic_rule(target_date)
        assert rule is not None
        assert rule["limited_number"] == "4和9"

        # 由于今日规则依赖当前日期，这里我们直接测试get_traffic_rule方法
        # 而不是依赖today()函数的mock
        rule_16 = await real_cache_service.get_traffic_rule(date(2025, 8, 16))
        assert rule_16 is not None
        assert rule_16["limited_number"] == "5和0"

    @pytest.mark.asyncio
    async def test_cache_service_push_history_integration(self, real_cache_service):
        """测试缓存服务推送历史集成"""
        plate = "京A12345"

        # 记录多条推送历史
        push_records = [
            {"message_type": "jjz_expiring", "success": True, "channel": "bark"},
            {"message_type": "traffic_reminder", "success": True, "channel": "apprise"},
            {"message_type": "jjz_expiring", "success": False, "error": "network timeout"}
        ]

        for record in push_records:
            success = await real_cache_service.record_push_history(plate, record)
            assert success is True

        # 获取推送历史
        history = await real_cache_service.get_push_history(plate, limit=5)
        assert len(history) == 3
        assert all("timestamp" in record for record in history)

        # 测试重复推送检查
        recent = await real_cache_service.check_recent_push(plate, "jjz_expiring", window_minutes=60)
        assert recent is True  # 刚刚推送过

        old = await real_cache_service.check_recent_push(plate, "nonexistent_type", window_minutes=60)
        assert old is False  # 没有这种类型的推送

    @pytest.mark.asyncio
    async def test_cache_service_stats_integration(self, real_cache_service):
        """测试缓存服务统计集成"""
        # 执行一些缓存操作产生统计数据
        plate = "京A12345"
        jjz_data = {"status": "valid"}

        # 缓存和获取操作
        await real_cache_service.cache_jjz_data(plate, jjz_data)
        await real_cache_service.get_jjz_data(plate)  # 命中
        await real_cache_service.get_jjz_data("京B67890")  # 未命中

        # 获取统计信息
        stats = await real_cache_service.get_cache_stats(days=1)
        assert 'jjz' in stats
        assert stats['jjz']['total_hits'] >= 1
        assert stats['jjz']['total_misses'] >= 1
        assert stats['jjz']['total_sets'] >= 1

        # 获取缓存信息
        info = await real_cache_service.get_cache_info()
        assert 'key_counts' in info
        assert info['key_counts']['total'] >= 1

    @pytest.mark.asyncio
    async def test_cache_service_clear_integration(self, real_cache_service):
        """测试缓存清理集成"""
        # 创建测试数据
        await real_cache_service.cache_jjz_data("京A12345", {"status": "valid"})
        await real_cache_service.cache_traffic_rules([{
            "limited_time": "2025年08月15日",
            "limited_number": "4和9"
        }])
        await real_cache_service.record_push_history("京A12345", {"type": "test"})

        # 获取清理前的数据
        info_before = await real_cache_service.get_cache_info()
        assert info_before['key_counts']['total'] > 0

        # 清理所有缓存
        result = await real_cache_service.clear_cache()
        assert result['deleted_keys'] > 0

        # 验证清理结果
        info_after = await real_cache_service.get_cache_info()
        assert info_after['key_counts']['total'] == 0

    @pytest.mark.asyncio
    async def test_redis_connection_resilience(self, real_redis_manager):
        """测试Redis连接弹性"""
        # 测试正常连接
        health = await real_redis_manager.health_check()
        assert health['status'] == 'healthy'

        # 测试获取客户端
        client = real_redis_manager.client
        await client.ping()  # 应该成功

        # 测试重复初始化
        success = await real_redis_manager.initialize()
        assert success is True  # 重复初始化应该成功
