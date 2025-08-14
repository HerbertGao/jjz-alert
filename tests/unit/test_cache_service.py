"""
CacheService 单元测试
"""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from service.jjz.jjz_status import JJZStatusEnum


@pytest.mark.unit
class TestCacheService:
    """CacheService测试类"""

    @pytest.mark.asyncio
    async def test_cache_jjz_data_success(self, cache_service):
        """测试缓存进京证数据成功"""
        plate = "京A12345"
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "valid_start": "2025-08-15 00:00:00",
            "valid_end": "2025-08-20 23:59:59"
        }

        # Mock redis operations
        cache_service.redis_ops.set.return_value = True
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.cache_jjz_data(plate, jjz_data)

        assert result is True
        cache_service.redis_ops.set.assert_called_once()
        # 验证缓存的数据包含时间戳
        call_args = cache_service.redis_ops.set.call_args
        cached_data = call_args[0][1]
        assert "cached_at" in cached_data
        assert cached_data["status"] == JJZStatusEnum.VALID.value
        # 验证原始数据也被包含
        assert cached_data["valid_start"] == jjz_data["valid_start"]
        assert cached_data["valid_end"] == jjz_data["valid_end"]

    @pytest.mark.asyncio
    async def test_get_jjz_data_hit(self, cache_service):
        """测试进京证缓存命中"""
        plate = "京A12345"
        cached_data = {
            "status": JJZStatusEnum.VALID.value,
            "cached_at": "2025-08-15T10:00:00"
        }

        cache_service.redis_ops.get.return_value = cached_data
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.get_jjz_data(plate)

        assert result == cached_data
        cache_service.redis_ops.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_jjz_data_miss(self, cache_service):
        """测试进京证缓存未命中"""
        plate = "京A12345"

        cache_service.redis_ops.get.return_value = None
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.get_jjz_data(plate)

        assert result is None
        cache_service.redis_ops.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_jjz_data(self, cache_service):
        """测试删除进京证缓存"""
        plate = "京A12345"

        cache_service.redis_ops.delete.return_value = 1
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.delete_jjz_data(plate)

        assert result is True
        cache_service.redis_ops.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_traffic_rules_success(self, cache_service, sample_traffic_rules):
        """测试缓存限行规则成功"""
        cache_service.redis_ops.set.return_value = True
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.cache_traffic_rules(sample_traffic_rules)

        assert result is True
        # 验证每个规则都被缓存
        assert cache_service.redis_ops.set.call_count == len(sample_traffic_rules)

    @pytest.mark.asyncio
    async def test_get_traffic_rule_hit(self, cache_service):
        """测试限行规则缓存命中"""
        target_date = date(2025, 8, 15)
        cached_rule = {
            "date": "2025-08-15",
            "limited_numbers": "4和9",
            "is_limited": True
        }

        cache_service.redis_ops.get.return_value = cached_rule
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.get_traffic_rule(target_date)

        assert result == cached_rule
        cache_service.redis_ops.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_traffic_rule_miss(self, cache_service):
        """测试限行规则缓存未命中"""
        target_date = date(2025, 8, 15)

        cache_service.redis_ops.get.return_value = None
        cache_service.redis_ops.hincrby.return_value = 1
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.get_traffic_rule(target_date)

        assert result is None

    @pytest.mark.asyncio
    async def test_record_push_history(self, cache_service):
        """测试记录推送历史"""
        plate = "京A12345"
        push_record = {
            "message_type": "jjz_expiring",
            "success": True,
            "channel": "bark"
        }

        cache_service.redis_ops.lpush.return_value = 1
        cache_service.redis_ops.ltrim.return_value = True
        cache_service.redis_ops.expire.return_value = True

        result = await cache_service.record_push_history(plate, push_record)

        assert result is True
        cache_service.redis_ops.lpush.assert_called_once()
        cache_service.redis_ops.ltrim.assert_called_once()
        cache_service.redis_ops.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_push_history(self, cache_service):
        """测试获取推送历史"""
        plate = "京A12345"
        history_data = [
            {"timestamp": "2025-08-15T10:00:00", "message_type": "jjz_expiring"},
            {"timestamp": "2025-08-15T08:00:00", "message_type": "traffic_reminder"}
        ]

        cache_service.redis_ops.lrange.return_value = history_data

        result = await cache_service.get_push_history(plate, limit=10)

        assert result == history_data
        cache_service.redis_ops.lrange.assert_called_once_with(
            f"{cache_service.PUSH_HISTORY_PREFIX}{plate}", 0, 9
        )

    @pytest.mark.asyncio
    async def test_check_recent_push_found(self, cache_service):
        """测试检查重复推送 - 找到重复"""
        plate = "京A12345"
        recent_history = [
            {
                "timestamp": "2025-08-15T10:30:00",
                "message_type": "jjz_expiring"
            }
        ]

        cache_service.redis_ops.lrange.return_value = recent_history

        # Mock datetime.now() 返回稍晚的时间
        with patch('service.cache.cache_service.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 8, 15, 10, 45)
            mock_dt.fromisoformat = datetime.fromisoformat

            result = await cache_service.check_recent_push(plate, "jjz_expiring", window_minutes=60)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_recent_push_not_found(self, cache_service):
        """测试检查重复推送 - 未找到重复"""
        plate = "京A12345"
        old_history = [
            {
                "timestamp": "2025-08-15T08:00:00",
                "message_type": "jjz_expiring"
            }
        ]

        cache_service.redis_ops.lrange.return_value = old_history

        # Mock datetime.now() 返回2小时后的时间
        with patch('service.cache.cache_service.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 8, 15, 10, 30)
            mock_dt.fromisoformat = datetime.fromisoformat

            result = await cache_service.check_recent_push(plate, "jjz_expiring", window_minutes=60)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_jjz_plates(self, cache_service):
        """测试获取所有缓存车牌"""
        cached_keys = [
            f"{cache_service.JJZ_PREFIX}京A12345",
            f"{cache_service.JJZ_PREFIX}京B67890"
        ]

        cache_service.redis_ops.keys.return_value = cached_keys

        result = await cache_service.get_all_jjz_plates()

        expected_plates = ["京A12345", "京B67890"]
        assert result == expected_plates

    @pytest.mark.asyncio
    async def test_clear_cache_all(self, cache_service):
        """测试清空所有缓存"""
        # Mock keys() calls for jjz, traffic, and push_history
        cache_service.redis_ops.keys.side_effect = [
            ["jjz:京A12345"],  # jjz keys
            ["traffic:rules:2025-08-15"],  # traffic keys  
            ["push_history:京A12345"]  # push_history keys
        ]
        cache_service.redis_ops.delete.return_value = 2

        result = await cache_service.clear_cache()

        assert result['deleted_keys'] == 6  # 2 + 2 + 2 from three delete calls
        assert cache_service.redis_ops.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_clear_cache_specific_type(self, cache_service):
        """测试清空指定类型缓存"""
        cache_service.redis_ops.keys.return_value = ["jjz:京A12345", "jjz:京B67890"]
        cache_service.redis_ops.delete.return_value = 2

        result = await cache_service.clear_cache(cache_type="jjz")

        assert result['jjz_deleted'] == 2
        assert result['deleted_keys'] == 2
        cache_service.redis_ops.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_info(self, cache_service):
        """测试获取缓存信息"""
        jjz_keys = ["jjz:京A12345"]
        traffic_keys = ["traffic:rules:2025-08-15", "traffic:rules:2025-08-16"]
        push_keys = ["push_history:京A12345"]

        cache_service.redis_ops.keys.side_effect = [jjz_keys, traffic_keys, push_keys, jjz_keys]

        result = await cache_service.get_cache_info()

        assert result['key_counts']['jjz'] == 1
        assert result['key_counts']['traffic'] == 2
        assert result['key_counts']['push_history'] == 1
        assert result['key_counts']['total'] == 4
        assert result['cached_plates'] == ["京A12345"]
