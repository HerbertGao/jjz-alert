"""
TrafficService 单元测试
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from service.traffic.traffic_service import TrafficService, TrafficRule


@pytest.mark.unit
class TestTrafficService:
    """TrafficService测试类"""

    @pytest.fixture
    def traffic_service(self):
        """创建TrafficService实例"""
        # 创建Mock缓存服务
        mock_cache = Mock()
        mock_cache.get_traffic_rule = AsyncMock()
        mock_cache.get_traffic_rules_batch = AsyncMock()
        mock_cache.cache_traffic_rules = AsyncMock()
        mock_cache.get_cache_stats = AsyncMock()
        mock_cache.clear_cache = AsyncMock()
        mock_cache.get_cache_info = AsyncMock()

        return TrafficService(mock_cache)

    def test_get_plate_tail_number(self, traffic_service):
        """测试获取车牌尾号"""
        assert traffic_service._get_plate_tail_number("京A12345") == "5"
        assert traffic_service._get_plate_tail_number("京B67890") == "0"
        assert traffic_service._get_plate_tail_number("京C1111A") == "0"  # 字母按0处理
        assert traffic_service._get_plate_tail_number("") == "0"  # 空字符串
        assert traffic_service._get_plate_tail_number("京D123@") == "0"  # 特殊字符

    def test_is_same_day(self, traffic_service):
        """测试日期比较"""
        date1 = date(2025, 8, 15)
        date2 = date(2025, 8, 15)
        date3 = date(2025, 8, 16)

        assert traffic_service._is_same_day(date1, date2) is True
        assert traffic_service._is_same_day(date1, date3) is False

    def test_parse_traffic_response_success(self, traffic_service):
        """测试解析限行规则响应成功"""
        # API格式的数据 (使用limitedTime和limitedNumber)
        api_data = [
            {
                "limitedTime": "2025年08月15日",
                "limitedNumber": "4和9",
                "description": "周四限行4和9"
            },
            {
                "limitedTime": "2025年08月16日",
                "limitedNumber": "5和0",
                "description": "周五限行5和0"
            },
            {
                "limitedTime": "2025年08月17日",
                "limitedNumber": "不限行",
                "description": "周六不限行"
            }
        ]
        response_data = {
            "state": "success",
            "result": api_data
        }

        rules = traffic_service._parse_traffic_response(response_data)

        assert len(rules) == 3
        assert rules[0].date == date(2025, 8, 15)
        assert rules[0].limited_numbers == "4和9"
        assert rules[0].is_limited is True
        assert rules[2].limited_numbers == "不限行"
        assert rules[2].is_limited is False

    def test_parse_traffic_response_error(self, traffic_service):
        """测试解析限行规则响应错误"""
        response_data = {
            "state": "error",
            "resultMsg": "服务暂不可用"
        }

        rules = traffic_service._parse_traffic_response(response_data)

        assert rules == []

    def test_is_plate_limited_by_rule_limited(self, traffic_service):
        """测试车牌限行判断 - 限行"""
        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="4和9",
            limited_time="2025年08月15日",
            is_limited=True
        )

        assert traffic_service._is_plate_limited_by_rule("4", rule) is True
        assert traffic_service._is_plate_limited_by_rule("9", rule) is True
        assert traffic_service._is_plate_limited_by_rule("5", rule) is False

    def test_is_plate_limited_by_rule_not_limited(self, traffic_service):
        """测试车牌限行判断 - 不限行"""
        rule = TrafficRule(
            date=date(2025, 8, 17),
            limited_numbers="不限行",
            limited_time="2025年08月17日",
            is_limited=False
        )

        assert traffic_service._is_plate_limited_by_rule("4", rule) is False
        assert traffic_service._is_plate_limited_by_rule("9", rule) is False

    @pytest.mark.asyncio
    async def test_get_traffic_rule_cache_hit(self, traffic_service):
        """测试获取限行规则 - 缓存命中"""
        target_date = date(2025, 8, 15)
        cached_data = {
            "date": "2025-08-15",
            "limited_numbers": "4和9",
            "limited_time": "2025年08月15日",
            "is_limited": True,
            "data_source": "cache"
        }

        traffic_service.cache_service.get_traffic_rule.return_value = cached_data

        rule = await traffic_service.get_traffic_rule(target_date, use_cache=True)

        assert rule is not None
        assert rule.date == target_date
        assert rule.limited_numbers == "4和9"
        assert rule.data_source == "cache"

    @pytest.mark.asyncio
    async def test_get_traffic_rule_cache_miss(self, traffic_service, mock_traffic_response):
        """测试获取限行规则 - 缓存未命中"""
        target_date = date(2025, 8, 15)

        traffic_service.cache_service.get_traffic_rule.return_value = None

        with patch('service.traffic.traffic_service.http_get') as mock_get:
            mock_get.return_value = mock_traffic_response

            # Mock缓存方法
            with patch.object(traffic_service, '_cache_rules') as mock_cache:
                mock_cache.return_value = True

                rule = await traffic_service.get_traffic_rule(target_date, use_cache=True)

                assert rule is not None
                assert rule.date == target_date
                assert rule.limited_numbers == "4和9"
                mock_get.assert_called_once()
                mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_today_traffic_rule(self, traffic_service):
        """测试获取今日限行规则"""
        with patch.object(traffic_service, 'get_traffic_rule') as mock_get:
            mock_rule = TrafficRule(
                date=date.today(),
                limited_numbers="4和9",
                limited_time="",
                is_limited=True
            )
            mock_get.return_value = mock_rule

            rule = await traffic_service.get_today_traffic_rule()

            assert rule == mock_rule
            mock_get.assert_called_once_with(date.today())

    @pytest.mark.asyncio
    async def test_check_plate_limited_async_success(self, traffic_service):
        """测试检查车牌限行状态 - 异步方法成功"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        mock_rule = TrafficRule(
            date=target_date,
            limited_numbers="5和0",
            limited_time="2025年08月15日",
            is_limited=True
        )

        with patch.object(traffic_service, 'get_traffic_rule') as mock_get:
            mock_get.return_value = mock_rule

            status = await traffic_service.check_plate_limited(plate, target_date)

            assert status.plate == plate
            assert status.date == target_date
            assert status.is_limited is True  # 尾号5限行
            assert status.tail_number == "5"
            assert status.rule == mock_rule

    @pytest.mark.asyncio
    async def test_check_plate_limited_no_rule(self, traffic_service):
        """测试检查车牌限行状态 - 无规则"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        with patch.object(traffic_service, 'get_traffic_rule') as mock_get:
            mock_get.return_value = None

            status = await traffic_service.check_plate_limited(plate, target_date)

            assert status.plate == plate
            assert status.is_limited is False
            assert "未找到日期" in status.error_message

    @pytest.mark.asyncio
    async def test_check_multiple_plates(self, traffic_service):
        """测试批量检查多个车牌"""
        plates = ["京A12345", "京B67890"]
        target_date = date(2025, 8, 15)

        mock_rule = TrafficRule(
            date=target_date,
            limited_numbers="5和0",
            limited_time="2025年08月15日",
            is_limited=True
        )

        with patch.object(traffic_service, 'get_traffic_rule') as mock_get:
            mock_get.return_value = mock_rule

            results = await traffic_service.check_multiple_plates(plates, target_date)

            assert len(results) == 2
            assert results["京A12345"].is_limited is True  # 尾号5限行
            assert results["京B67890"].is_limited is True  # 尾号0限行

    @pytest.mark.asyncio
    async def test_get_week_rules(self, traffic_service):
        """测试获取一周限行规则"""
        start_date = date(2025, 8, 15)

        # 生成一周的日期列表并模拟所有缓存未命中
        dates = [start_date + timedelta(days=i) for i in range(7)]
        cache_result = {date: None for date in dates}  # 所有日期都是缓存未命中
        traffic_service.cache_service.get_traffic_rules_batch.return_value = cache_result

        # Mock API返回规则
        mock_rules = []
        for i, target_date in enumerate(dates):
            mock_rules.append(TrafficRule(
                date=target_date,
                limited_numbers="4和9",
                limited_time="",
                is_limited=True
            ))

        with patch.object(traffic_service, '_fetch_rules_from_api', return_value=mock_rules):
            rules = await traffic_service.get_week_rules(start_date)

            assert len(rules) == 7
            assert all(isinstance(rule, TrafficRule) for rule in rules)

    @pytest.mark.asyncio
    async def test_refresh_rules_cache(self, traffic_service, mock_traffic_response):
        """测试刷新限行规则缓存"""
        with patch.object(traffic_service.cache_service, 'clear_cache') as mock_clear:
            mock_clear.return_value = {"deleted_keys": 5}

            with patch('service.traffic.traffic_service.http_get') as mock_get:
                mock_get.return_value = mock_traffic_response

                with patch.object(traffic_service, '_cache_rules') as mock_cache:
                    mock_cache.return_value = True

                    rules = await traffic_service.refresh_rules_cache()

                    assert len(rules) == 3
                    mock_clear.assert_called_once_with('traffic')
                    mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_service_status(self, traffic_service):
        """测试获取服务状态"""
        mock_rule = TrafficRule(
            date=date.today(),
            limited_numbers="4和9",
            limited_time="",
            is_limited=True
        )

        with patch.object(traffic_service, 'get_today_traffic_rule') as mock_today:
            mock_today.return_value = mock_rule

            traffic_service.cache_service.get_cache_stats.return_value = {
                'traffic': {
                    'total_hits': 15,
                    'total_misses': 3,
                    'hit_rate': 83.33
                }
            }

            traffic_service.cache_service.get_cache_info.return_value = {
                'key_counts': {'traffic': 7}
            }

            status = await traffic_service.get_service_status()

            assert status['service'] == 'TrafficService'
            assert status['status'] == 'healthy'
            assert status['today_rule']['limited_numbers'] == "4和9"
            assert status['cached_rules_count'] == 7
            assert status['cache_stats']['hits'] == 15

    # 兼容原TrafficLimiter接口的测试
    def test_check_plate_limited_sync(self, traffic_service):
        """测试同步检查车牌限行（兼容接口）"""
        plate = "京A12345"

        # Mock内存缓存数据
        test_date = date(2025, 8, 15)
        traffic_service._memory_cache = [
            {
                "limitedTime": "2025年08月15日",
                "limitedNumber": "5和0"
            }
        ]
        traffic_service._memory_cache_date = test_date

        with patch('service.traffic.traffic_service.date') as mock_date:
            mock_date.today.return_value = test_date

            result = traffic_service.check_plate_limited_sync(plate)

            assert result is True  # 尾号5限行

    def test_check_plate_limited_on(self, traffic_service):
        """测试指定日期检查车牌限行（兼容接口）"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        # Mock内存缓存数据
        traffic_service._memory_cache = [
            {
                "limitedTime": "2025年08月15日",
                "limitedNumber": "5和0"
            }
        ]
        traffic_service._memory_cache_date = date.today()

        result = traffic_service.check_plate_limited_on(plate, target_date)

        assert result is True  # 尾号5限行

    def test_get_today_limit_info_sync(self, traffic_service):
        """测试获取今日限行信息（兼容接口）"""
        # Mock内存缓存数据
        test_date = date(2025, 8, 15)
        today_rule = {
            "limitedTime": "2025年08月15日",
            "limitedNumber": "4和9"
        }
        traffic_service._memory_cache = [today_rule]
        traffic_service._memory_cache_date = test_date

        with patch('service.traffic.traffic_service.date') as mock_date:
            mock_date.today.return_value = test_date

            result = traffic_service.get_today_limit_info()

            assert result == today_rule

    def test_get_cache_status_sync(self, traffic_service):
        """测试获取缓存状态（兼容接口）"""
        traffic_service._cache_status = "ready"
        traffic_service._memory_cache_date = date(2025, 8, 15)
        traffic_service._memory_cache = [{"limitedTime": "2025年08月15日"}]
        traffic_service._last_update_time = 1692096000.0
        traffic_service._retry_count = 0

        status = traffic_service.get_cache_status()

        assert status['status'] == "ready"
        assert status['cache_date'] == "2025-08-15"
        assert status['cache_count'] == 1
        assert status['retry_count'] == 0
