"""
TrafficService 单元测试
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from jjz_alert.service.traffic.traffic_service import TrafficService, TrafficRule


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
        ]
        response_data = {"state": "success", "result": api_data}

        rules = traffic_service._parse_traffic_response(response_data)

        assert len(rules) == 3
        assert rules[0].date == date(2025, 8, 15)
        assert rules[0].limited_numbers == "4和9"
        assert rules[0].is_limited is True
        assert rules[2].limited_numbers == "不限行"
        assert rules[2].is_limited is False

    def test_parse_traffic_response_error(self, traffic_service):
        """测试解析限行规则响应错误"""
        response_data = {"state": "error", "resultMsg": "服务暂不可用"}

        rules = traffic_service._parse_traffic_response(response_data)

        assert rules == []

    def test_is_plate_limited_by_rule_limited(self, traffic_service):
        """测试车牌限行判断 - 限行"""
        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="4和9",
            limited_time="2025年08月15日",
            is_limited=True,
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
            is_limited=False,
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
            "data_source": "cache",
        }

        traffic_service.cache_service.get_traffic_rule.return_value = cached_data

        rule = await traffic_service.get_traffic_rule(target_date, use_cache=True)

        assert rule is not None
        assert rule.date == target_date
        assert rule.limited_numbers == "4和9"
        assert rule.data_source == "cache"

    @pytest.mark.asyncio
    async def test_get_traffic_rule_cache_miss(
        self, traffic_service, mock_traffic_response
    ):
        """测试获取限行规则 - 缓存未命中"""
        target_date = date(2025, 8, 15)

        traffic_service.cache_service.get_traffic_rule.return_value = None

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.return_value = mock_traffic_response

            # Mock缓存方法
            with patch.object(traffic_service, "_cache_rules") as mock_cache:
                mock_cache.return_value = True

                rule = await traffic_service.get_traffic_rule(
                    target_date, use_cache=True
                )

                assert rule is not None
                assert rule.date == target_date
                assert rule.limited_numbers == "4和9"
                mock_get.assert_called_once()
                mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_today_traffic_rule(self, traffic_service):
        """测试获取今日限行规则"""
        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
            mock_rule = TrafficRule(
                date=date.today(),
                limited_numbers="4和9",
                limited_time="",
                is_limited=True,
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
            is_limited=True,
        )

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
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

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
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
            is_limited=True,
        )

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
            mock_get.return_value = mock_rule

            results = await traffic_service.check_multiple_plates(plates, target_date)

            assert len(results) == 2
            assert results["京A12345"].is_limited is True  # 尾号5限行
            assert results["京B67890"].is_limited is True  # 尾号0限行

    @pytest.mark.asyncio
    async def test_check_multiple_plates_no_rule(self, traffic_service):
        """测试批量检查多个车牌 - 无规则"""
        plates = ["京A12345", "京B67890"]
        target_date = date(2025, 8, 15)

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
            mock_get.return_value = None

            results = await traffic_service.check_multiple_plates(plates, target_date)

            assert len(results) == 2
            for status in results.values():
                assert status.is_limited is False
                assert status.error_message == f"未找到日期 {target_date} 的限行规则"

    @pytest.mark.asyncio
    async def test_check_multiple_plates_exception(self, traffic_service):
        """测试批量检查多个车牌 - 单个车牌处理异常"""
        plates = ["京A12345"]
        target_date = date(2025, 8, 15)

        mock_rule = TrafficRule(
            date=target_date,
            limited_numbers="5和0",
            limited_time="2025年08月15日",
            is_limited=True,
        )

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
            mock_get.return_value = mock_rule

            with patch.object(
                traffic_service,
                "_is_plate_limited_by_rule",
                side_effect=ValueError("boom"),
            ):
                results = await traffic_service.check_multiple_plates(
                    plates, target_date
                )

                status = results["京A12345"]
                assert status.is_limited is False
                assert status.error_message == "boom"
                assert status.tail_number == traffic_service._get_plate_tail_number(
                    "京A12345"
                )

    @pytest.mark.asyncio
    async def test_get_week_rules(self, traffic_service):
        """测试获取一周限行规则"""
        start_date = date(2025, 8, 15)

        # 生成一周的日期列表并模拟所有缓存未命中
        dates = [start_date + timedelta(days=i) for i in range(7)]
        cache_result = {date: None for date in dates}  # 所有日期都是缓存未命中
        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cache_result
        )

        # Mock API返回规则
        mock_rules = []
        for i, target_date in enumerate(dates):
            mock_rules.append(
                TrafficRule(
                    date=target_date,
                    limited_numbers="4和9",
                    limited_time="",
                    is_limited=True,
                )
            )

        with patch.object(
            traffic_service, "_fetch_rules_from_api", return_value=mock_rules
        ):
            rules = await traffic_service.get_week_rules(start_date)

            assert len(rules) == 7
            assert all(isinstance(rule, TrafficRule) for rule in rules)

    @pytest.mark.asyncio
    async def test_refresh_rules_cache(self, traffic_service, mock_traffic_response):
        """测试刷新限行规则缓存"""
        with patch.object(traffic_service.cache_service, "clear_cache") as mock_clear:
            mock_clear.return_value = {"deleted_keys": 5}

            with patch(
                "jjz_alert.service.traffic.traffic_service.http_get"
            ) as mock_get:
                mock_get.return_value = mock_traffic_response

                with patch.object(traffic_service, "_cache_rules") as mock_cache:
                    mock_cache.return_value = True

                    rules = await traffic_service.refresh_rules_cache()

                    assert len(rules) == 3
                    mock_clear.assert_called_once_with("traffic")
                    mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_service_status(self, traffic_service):
        """测试获取服务状态"""
        mock_rule = TrafficRule(
            date=date.today(), limited_numbers="4和9", limited_time="", is_limited=True
        )

        with patch.object(traffic_service, "get_today_traffic_rule") as mock_today:
            mock_today.return_value = mock_rule

            traffic_service.cache_service.get_cache_stats.return_value = {
                "traffic": {"total_hits": 15, "total_misses": 3, "hit_rate": 83.33}
            }

            traffic_service.cache_service.get_cache_info.return_value = {
                "key_counts": {"traffic": 7}
            }

            status = await traffic_service.get_service_status()

            assert status["service"] == "TrafficService"
            assert status["status"] == "healthy"
            assert status["today_rule"]["limited_numbers"] == "4和9"
            assert status["cached_rules_count"] == 7
            assert status["cache_stats"]["hits"] == 15

    # 兼容原TrafficLimiter接口的测试
    def test_check_plate_limited_sync(self, traffic_service):
        """测试同步检查车牌限行（兼容接口）"""
        plate = "京A12345"

        # Mock内存缓存数据
        test_date = date(2025, 8, 15)
        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月15日", "limitedNumber": "5和0"}
        ]
        traffic_service._memory_cache_date = test_date

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = test_date

            result = traffic_service.check_plate_limited_sync(plate)

            assert result is True  # 尾号5限行

    def test_check_plate_limited_on(self, traffic_service):
        """测试指定日期检查车牌限行（兼容接口）"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        # Mock内存缓存数据
        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月15日", "limitedNumber": "5和0"}
        ]
        traffic_service._memory_cache_date = date.today()

        result = traffic_service.check_plate_limited_on(plate, target_date)

        assert result is True  # 尾号5限行

    def test_get_today_limit_info_sync(self, traffic_service):
        """测试获取今日限行信息（兼容接口）"""
        # Mock内存缓存数据
        test_date = date(2025, 8, 15)
        today_rule = {"limitedTime": "2025年08月15日", "limitedNumber": "4和9"}
        traffic_service._memory_cache = [today_rule]
        traffic_service._memory_cache_date = test_date

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
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

        assert status["status"] == "ready"
        assert status["cache_date"] == "2025-08-15"
        assert status["cache_count"] == 1
        assert status["retry_count"] == 0

    def test_plate_traffic_status_to_dict_with_rule(self, traffic_service):
        """测试PlateTrafficStatus转换为字典 - 有规则"""
        from jjz_alert.service.traffic.traffic_service import PlateTrafficStatus

        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="4和9",
            limited_time="2025年08月15日",
            is_limited=True,
        )

        status = PlateTrafficStatus(
            plate="京A12345",
            date=date(2025, 8, 15),
            is_limited=True,
            tail_number="5",
            rule=rule,
        )

        result = status.to_dict()

        assert result["plate"] == "京A12345"
        assert result["is_limited"] is True
        assert result["rule"] is not None
        assert result["rule"]["limited_numbers"] == "4和9"

    def test_plate_traffic_status_to_dict_without_rule(self, traffic_service):
        """测试PlateTrafficStatus转换为字典 - 无规则"""
        from jjz_alert.service.traffic.traffic_service import PlateTrafficStatus

        status = PlateTrafficStatus(
            plate="京A12345",
            date=date(2025, 8, 15),
            is_limited=False,
            tail_number="5",
            rule=None,
            error_message="未找到规则",
        )

        result = status.to_dict()

        assert result["plate"] == "京A12345"
        assert result["is_limited"] is False
        assert result["rule"] is None
        assert result["error_message"] == "未找到规则"

    def test_parse_traffic_response_empty_limited_time(self, traffic_service):
        """测试解析限行规则响应 - 空limitedTime"""
        response_data = {
            "state": "success",
            "result": [
                {
                    "limitedTime": "",  # 空时间
                    "limitedNumber": "4和9",
                },
                {
                    "limitedTime": "2025年08月15日",
                    "limitedNumber": "5和0",
                },
            ],
        }

        rules = traffic_service._parse_traffic_response(response_data)

        # 应该只解析一条规则（空时间的被跳过）
        assert len(rules) == 1
        assert rules[0].limited_numbers == "5和0"

    def test_parse_traffic_response_parse_exception(self, traffic_service):
        """测试解析限行规则响应 - 解析单条规则异常"""
        response_data = {
            "state": "success",
            "result": [
                {
                    "limitedTime": "invalid-date",  # 无效日期格式
                    "limitedNumber": "4和9",
                },
                {
                    "limitedTime": "2025年08月15日",
                    "limitedNumber": "5和0",
                },
            ],
        }

        rules = traffic_service._parse_traffic_response(response_data)

        # 应该只解析一条规则（无效日期的被跳过）
        assert len(rules) == 1
        assert rules[0].limited_numbers == "5和0"

    def test_parse_traffic_response_outer_exception(self, traffic_service):
        """测试解析限行规则响应 - 外层异常"""
        # 传入非字典类型，触发外层异常
        response_data = "invalid"

        rules = traffic_service._parse_traffic_response(response_data)

        assert rules == []

    @pytest.mark.asyncio
    async def test_fetch_rules_from_api_empty_rules(self, traffic_service):
        """测试从API获取限行规则 - 返回空规则列表"""
        mock_response = Mock()
        mock_response.json.return_value = {"state": "success", "result": []}
        mock_response.raise_for_status = Mock()

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.return_value = mock_response
            with patch(
                "jjz_alert.service.traffic.traffic_service.asyncio.sleep"
            ) as mock_sleep:
                # 由于有错误处理装饰器，异常被捕获并返回默认值[]
                # 装饰器会重试，所以实际调用次数会更多
                result = await traffic_service._fetch_rules_from_api()

                # 应该返回空列表（默认返回值）
                assert result == []
                # 由于错误处理装饰器的重试机制，调用次数会更多
                assert mock_get.call_count >= 3

    @pytest.mark.asyncio
    async def test_fetch_rules_from_api_max_retries(self, traffic_service):
        """测试从API获取限行规则 - 达到最大重试次数"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("Network error")

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.return_value = mock_response
            with patch(
                "jjz_alert.service.traffic.traffic_service.asyncio.sleep"
            ) as mock_sleep:
                # 由于有错误处理装饰器，异常被捕获并返回默认值[]
                # 装饰器会重试，所以实际调用次数会更多
                result = await traffic_service._fetch_rules_from_api()

                # 应该返回空列表（默认返回值）
                assert result == []
                # 由于错误处理装饰器的重试机制，调用次数会更多
                assert mock_get.call_count >= 3

    @pytest.mark.asyncio
    async def test_fetch_rules_from_api_success_with_retry(self, traffic_service):
        """测试从API获取限行规则 - 重试后成功"""
        mock_response_fail = Mock()
        mock_response_fail.raise_for_status.side_effect = Exception("Network error")

        mock_response_success = Mock()
        mock_response_success.json.return_value = {
            "state": "success",
            "result": [
                {
                    "limitedTime": "2025年08月15日",
                    "limitedNumber": "4和9",
                }
            ],
        }
        mock_response_success.raise_for_status = Mock()

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.side_effect = [mock_response_fail, mock_response_success]
            with patch(
                "jjz_alert.service.traffic.traffic_service.asyncio.sleep"
            ) as mock_sleep:
                with patch.object(traffic_service, "_cache_rules") as mock_cache:
                    mock_cache.return_value = True

                    rules = await traffic_service._fetch_rules_from_api()

                    assert len(rules) == 1
                    assert mock_get.call_count == 2
                    assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_rules_success(self, traffic_service):
        """测试缓存限行规则 - 成功"""
        rules = [
            TrafficRule(
                date=date(2025, 8, 15),
                limited_numbers="4和9",
                limited_time="2025年08月15日",
                is_limited=True,
            )
        ]

        traffic_service.cache_service.cache_traffic_rules.return_value = True

        result = await traffic_service._cache_rules(rules)

        assert result is True
        traffic_service.cache_service.cache_traffic_rules.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_rules_failure(self, traffic_service):
        """测试缓存限行规则 - 失败"""
        rules = [
            TrafficRule(
                date=date(2025, 8, 15),
                limited_numbers="4和9",
                limited_time="2025年08月15日",
                is_limited=True,
            )
        ]

        traffic_service.cache_service.cache_traffic_rules.side_effect = Exception(
            "Cache error"
        )

        result = await traffic_service._cache_rules(rules)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_traffic_rule_not_found(self, traffic_service):
        """测试获取限行规则 - 未找到规则"""
        target_date = date(2025, 8, 15)

        traffic_service.cache_service.get_traffic_rule.return_value = None

        with patch.object(traffic_service, "_fetch_rules_from_api") as mock_fetch:
            # API返回的规则不包含目标日期
            mock_fetch.return_value = [
                TrafficRule(
                    date=date(2025, 8, 16),
                    limited_numbers="5和0",
                    limited_time="2025年08月16日",
                    is_limited=True,
                )
            ]

            rule = await traffic_service.get_traffic_rule(target_date)

            assert rule is None

    @pytest.mark.asyncio
    async def test_get_traffic_rule_exception(self, traffic_service):
        """测试获取限行规则 - 异常处理"""
        target_date = date(2025, 8, 15)

        traffic_service.cache_service.get_traffic_rule.side_effect = Exception(
            "Cache error"
        )

        # 由于有错误处理装饰器，异常被捕获并返回默认值None
        result = await traffic_service.get_traffic_rule(target_date, use_cache=False)

        assert result is None

    @pytest.mark.asyncio
    async def test_check_plate_limited_exception(self, traffic_service):
        """测试检查车牌限行状态 - 异常处理"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        with patch.object(traffic_service, "get_traffic_rule") as mock_get:
            mock_get.side_effect = Exception("API error")

            status = await traffic_service.check_plate_limited(plate, target_date)

            assert status.is_limited is False
            assert status.error_message == "API error"
            assert status.tail_number == "5"

    def test_is_plate_limited_by_rule_other_format(self, traffic_service):
        """测试车牌限行判断 - 其他格式（不含'和'）"""
        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="12345",  # 不含'和'的格式
            limited_time="2025年08月15日",
            is_limited=True,
        )

        assert traffic_service._is_plate_limited_by_rule("1", rule) is True
        assert traffic_service._is_plate_limited_by_rule("6", rule) is False

    def test_is_plate_limited_by_rule_exception(self, traffic_service):
        """测试车牌限行判断 - 异常处理"""
        rule = TrafficRule(
            date=date(2025, 8, 15),
            limited_numbers="4和9",
            limited_time="2025年08月15日",
            is_limited=True,
        )

        # 模拟规则对象属性访问异常
        with patch.object(
            rule, "limited_numbers", side_effect=Exception("Attribute error")
        ):
            result = traffic_service._is_plate_limited_by_rule("4", rule)

            assert result is False

    @pytest.mark.asyncio
    async def test_get_week_rules_with_cache_hit(self, traffic_service):
        """测试获取一周限行规则 - 部分缓存命中"""
        start_date = date(2025, 8, 15)
        dates = [start_date + timedelta(days=i) for i in range(7)]

        # 模拟部分缓存命中
        cache_result = {}
        for i, target_date in enumerate(dates):
            if i < 3:  # 前3天缓存命中
                cache_result[target_date] = {
                    "date": target_date.isoformat(),
                    "limited_numbers": "4和9",
                    "limited_time": "2025年08月15日",
                    "is_limited": True,
                }
            else:  # 后4天缓存未命中
                cache_result[target_date] = None

        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cache_result
        )

        # Mock API返回规则
        mock_rules = []
        for target_date in dates[3:]:  # 只为未命中的日期返回规则
            mock_rules.append(
                TrafficRule(
                    date=target_date,
                    limited_numbers="5和0",
                    limited_time="",
                    is_limited=True,
                )
            )

        with patch.object(
            traffic_service, "_fetch_rules_from_api", return_value=mock_rules
        ):
            rules = await traffic_service.get_week_rules(start_date)

            assert len(rules) == 7
            assert all(isinstance(rule, TrafficRule) for rule in rules)

    @pytest.mark.asyncio
    async def test_refresh_rules_cache_exception(self, traffic_service):
        """测试刷新限行规则缓存 - 异常处理"""
        traffic_service.cache_service.clear_cache.side_effect = Exception("Clear error")

        result = await traffic_service.refresh_rules_cache()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_service_status_exception(self, traffic_service):
        """测试获取服务状态 - 异常处理"""
        traffic_service.cache_service.get_cache_stats.side_effect = Exception(
            "Stats error"
        )

        status = await traffic_service.get_service_status()

        assert status["service"] == "TrafficService"
        assert status["status"] == "error"
        assert "error" in status

    @pytest.mark.asyncio
    async def test_get_service_status_with_today_rule(self, traffic_service):
        """测试获取服务状态 - 传入today_rule"""
        mock_rule = TrafficRule(
            date=date.today(), limited_numbers="4和9", limited_time="", is_limited=True
        )

        traffic_service.cache_service.get_cache_stats.return_value = {
            "traffic": {"total_hits": 15, "total_misses": 3, "hit_rate": 83.33}
        }

        traffic_service.cache_service.get_cache_info.return_value = {
            "key_counts": {"traffic": 7}
        }

        status = await traffic_service.get_service_status(today_rule=mock_rule)

        assert status["service"] == "TrafficService"
        assert status["status"] == "healthy"
        assert status["today_rule"]["limited_numbers"] == "4和9"

    def test_fetch_limit_rules_sync_success(self, traffic_service):
        """测试同步获取限行规则 - 成功"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "state": "success",
            "result": [{"limitedTime": "2025年08月15日", "limitedNumber": "4和9"}],
        }
        mock_response.raise_for_status = Mock()

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.return_value = mock_response

            result = traffic_service._fetch_limit_rules_sync()

            assert result is not None
            assert len(result) == 1

    def test_fetch_limit_rules_sync_failure(self, traffic_service):
        """测试同步获取限行规则 - 失败"""
        mock_response = Mock()
        mock_response.json.return_value = {"state": "error", "resultMsg": "服务错误"}
        mock_response.raise_for_status = Mock()

        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.return_value = mock_response

            result = traffic_service._fetch_limit_rules_sync()

            assert result is None

    def test_fetch_limit_rules_sync_exception(self, traffic_service):
        """测试同步获取限行规则 - 异常"""
        with patch("jjz_alert.service.traffic.traffic_service.http_get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = traffic_service._fetch_limit_rules_sync()

            assert result is None

    def test_update_memory_cache_if_needed_no_cache(self, traffic_service):
        """测试更新内存缓存 - 无缓存"""
        with patch.object(traffic_service, "_update_memory_cache") as mock_update:
            traffic_service._update_memory_cache_if_needed()

            mock_update.assert_called_once()

    def test_update_memory_cache_if_needed_different_date(self, traffic_service):
        """测试更新内存缓存 - 不同日期"""
        traffic_service._memory_cache = [{"limitedTime": "2025年08月14日"}]
        traffic_service._memory_cache_date = date(2025, 8, 14)

        with patch.object(traffic_service, "_update_memory_cache") as mock_update:
            with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 8, 15)

                traffic_service._update_memory_cache_if_needed()

                mock_update.assert_called_once()

    def test_update_memory_cache_success(self, traffic_service):
        """测试更新内存缓存 - 成功"""
        import time as time_module

        with patch.object(traffic_service, "_fetch_limit_rules_sync") as mock_fetch:
            mock_fetch.return_value = [
                {"limitedTime": "2025年08月15日", "limitedNumber": "4和9"}
            ]
            with patch.object(time_module, "time") as mock_time:
                mock_time.return_value = 1692096000.0
                with patch.object(
                    time_module, "sleep"
                ):  # Mock sleep to avoid actual delay

                    traffic_service._update_memory_cache()

                    assert traffic_service._cache_status == "ready"
                    assert traffic_service._memory_cache is not None
                    assert traffic_service._memory_cache_date == date.today()
                    assert len(traffic_service._memory_cache) == 1

    def test_update_memory_cache_failure_retry(self, traffic_service):
        """测试更新内存缓存 - 失败重试"""
        import time as time_module

        with patch.object(traffic_service, "_fetch_limit_rules_sync") as mock_fetch:
            mock_fetch.return_value = None  # 返回None表示失败
            with patch.object(time_module, "sleep") as mock_sleep:
                with patch.object(time_module, "time") as mock_time:
                    mock_time.return_value = 1692096000.0

                    traffic_service._update_memory_cache()

                    # 应该重试3次
                    assert mock_fetch.call_count == 3
                    assert traffic_service._cache_status == "error"
                    assert mock_sleep.call_count == 2  # 重试2次，所以sleep 2次

    def test_update_memory_cache_exception_retry(self, traffic_service):
        """测试更新内存缓存 - 异常重试"""
        import time as time_module

        with patch.object(traffic_service, "_fetch_limit_rules_sync") as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")
            with patch.object(time_module, "sleep") as mock_sleep:
                with patch.object(time_module, "time") as mock_time:
                    mock_time.return_value = 1692096000.0

                    traffic_service._update_memory_cache()

                    # 应该重试3次
                    assert mock_fetch.call_count == 3
                    assert traffic_service._cache_status == "error"
                    assert mock_sleep.call_count == 2  # 重试2次，所以sleep 2次

    def test_preload_cache(self, traffic_service):
        """测试预加载缓存"""
        with patch.object(traffic_service, "_update_memory_cache") as mock_update:
            traffic_service._cache_status = "ready"

            traffic_service.preload_cache()

            mock_update.assert_called_once()

    def test_is_limited_today_memory_no_cache(self, traffic_service):
        """测试使用内存缓存检查限行 - 无缓存"""
        result = traffic_service._is_limited_today_memory("京A12345")

        assert result is False

    def test_is_limited_today_memory_different_date(self, traffic_service):
        """测试使用内存缓存检查限行 - 不同日期"""
        traffic_service._memory_cache = [{"limitedTime": "2025年08月14日"}]
        traffic_service._memory_cache_date = date(2025, 8, 14)

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)

            result = traffic_service._is_limited_today_memory("京A12345")

            assert result is False

    def test_is_limited_today_memory_no_rule(self, traffic_service):
        """测试使用内存缓存检查限行 - 无今日规则"""
        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月16日", "limitedNumber": "4和9"}
        ]
        traffic_service._memory_cache_date = date(2025, 8, 15)

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)

            result = traffic_service._is_limited_today_memory("京A12345")

            assert result is False

    def test_is_limited_today_memory_not_limited(self, traffic_service):
        """测试使用内存缓存检查限行 - 不限行"""
        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月15日", "limitedNumber": "不限行"}
        ]
        traffic_service._memory_cache_date = date(2025, 8, 15)

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)

            result = traffic_service._is_limited_today_memory("京A12345")

            assert result is False

    def test_is_limited_today_memory_limited(self, traffic_service):
        """测试使用内存缓存检查限行 - 限行"""
        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月15日", "limitedNumber": "5和0"}
        ]
        traffic_service._memory_cache_date = date(2025, 8, 15)

        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)

            result = traffic_service._is_limited_today_memory("京A12345")

            assert result is True  # 尾号5限行

    def test_check_plate_limited_on_no_cache(self, traffic_service):
        """测试指定日期检查限行 - 无缓存"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        result = traffic_service.check_plate_limited_on(plate, target_date)

        assert result is False

    def test_check_plate_limited_on_parse_exception(self, traffic_service):
        """测试指定日期检查限行 - 解析日期异常"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        traffic_service._memory_cache = [
            {"limitedTime": "invalid-date", "limitedNumber": "4和9"}
        ]

        result = traffic_service.check_plate_limited_on(plate, target_date)

        assert result is False

    def test_check_plate_limited_on_not_limited(self, traffic_service):
        """测试指定日期检查限行 - 不限行"""
        plate = "京A12345"
        target_date = date(2025, 8, 15)

        traffic_service._memory_cache = [
            {"limitedTime": "2025年08月15日", "limitedNumber": "不限行"}
        ]

        result = traffic_service.check_plate_limited_on(plate, target_date)

        assert result is False

    def test_get_today_limit_info_no_cache(self, traffic_service):
        """测试获取今日限行信息 - 无缓存"""
        with patch.object(traffic_service, "_update_memory_cache_if_needed"):
            result = traffic_service.get_today_limit_info()

            assert result is None

    @pytest.mark.asyncio
    async def test_get_smart_traffic_rules_before_2030(self, traffic_service):
        """测试智能获取限行规则 - 20:30前查询今天"""
        from datetime import datetime

        today = date(2025, 8, 15)
        cached_rules = {
            today: {
                "date": today.isoformat(),
                "limited_numbers": "4和9",
                "limited_time": "2025年08月15日",
                "is_limited": True,
            }
        }

        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cached_rules
        )

        with patch(
            "jjz_alert.service.traffic.traffic_service.datetime"
        ) as mock_datetime:
            with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
                mock_datetime.now.return_value = datetime(
                    2025, 8, 15, 20, 0, 0
                )  # 20:00
                mock_date.today.return_value = today
                # 保留真实的fromisoformat方法
                import datetime as dt_module

                mock_datetime.fromisoformat = dt_module.datetime.fromisoformat

                result = await traffic_service.get_smart_traffic_rules()

                assert result["query_type"] == "today"
                assert result["target_date"] == today
                assert result["target_rule"] is not None

    @pytest.mark.asyncio
    async def test_get_smart_traffic_rules_after_2030(self, traffic_service):
        """测试智能获取限行规则 - 20:30后查询明天"""
        from datetime import datetime

        today = date(2025, 8, 15)
        tomorrow = date(2025, 8, 16)
        cached_rules = {
            tomorrow: {
                "date": tomorrow.isoformat(),
                "limited_numbers": "5和0",
                "limited_time": "2025年08月16日",
                "is_limited": True,
            }
        }

        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cached_rules
        )

        # 需要mock方法内部的datetime.now()，因为方法内部有 from datetime import datetime
        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = today
            # 直接patch datetime模块的now方法
            with patch("datetime.datetime") as mock_datetime_class:
                mock_datetime_class.now.return_value = datetime(
                    2025, 8, 15, 21, 0, 0
                )  # 21:00
                mock_datetime_class.fromisoformat = datetime.fromisoformat
                import datetime as dt_module

                mock_datetime_class.timedelta = dt_module.timedelta

                result = await traffic_service.get_smart_traffic_rules()

                assert result["query_type"] == "tomorrow"
                assert result["target_date"] == tomorrow
                assert result["target_rule"] is not None

    @pytest.mark.asyncio
    async def test_get_smart_traffic_rules_at_2030(self, traffic_service):
        """测试智能获取限行规则 - 20:30查询明天"""
        from datetime import datetime

        today = date(2025, 8, 15)
        tomorrow = date(2025, 8, 16)
        cached_rules = {
            tomorrow: {
                "date": tomorrow.isoformat(),
                "limited_numbers": "5和0",
                "limited_time": "2025年08月16日",
                "is_limited": True,
            }
        }

        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cached_rules
        )

        # 需要mock方法内部的datetime.now()，因为方法内部有 from datetime import datetime
        with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
            mock_date.today.return_value = today
            # 直接patch datetime模块的now方法
            with patch("datetime.datetime") as mock_datetime_class:
                mock_datetime_class.now.return_value = datetime(
                    2025, 8, 15, 20, 30, 0
                )  # 20:30
                mock_datetime_class.fromisoformat = datetime.fromisoformat
                import datetime as dt_module

                mock_datetime_class.timedelta = dt_module.timedelta

                result = await traffic_service.get_smart_traffic_rules()

                assert result["query_type"] == "tomorrow"
                assert result["target_date"] == tomorrow

    @pytest.mark.asyncio
    async def test_get_smart_traffic_rules_cache_miss(self, traffic_service):
        """测试智能获取限行规则 - 缓存未命中"""
        from datetime import datetime

        today = date(2025, 8, 15)
        cached_rules = {today: None}  # 缓存未命中

        traffic_service.cache_service.get_traffic_rules_batch.return_value = (
            cached_rules
        )

        mock_rule = TrafficRule(
            date=today,
            limited_numbers="4和9",
            limited_time="",
            is_limited=True,
        )

        with patch(
            "jjz_alert.service.traffic.traffic_service.datetime"
        ) as mock_datetime:
            with patch("jjz_alert.service.traffic.traffic_service.date") as mock_date:
                mock_datetime.now.return_value = datetime(2025, 8, 15, 20, 0, 0)
                mock_date.today.return_value = today
                import datetime as dt_module

                mock_datetime.fromisoformat = dt_module.datetime.fromisoformat

                with patch.object(traffic_service, "get_traffic_rule") as mock_get:
                    mock_get.return_value = mock_rule

                    result = await traffic_service.get_smart_traffic_rules()

                    assert result["target_rule"] == mock_rule
                    mock_get.assert_called_once_with(today)

    @pytest.mark.asyncio
    async def test_check_plate_limited_with_exception_logging(self):
        """测试判断车牌限行 - 异常导致日志记录"""
        traffic_service = TrafficService()

        # Mock get_traffic_rule 抛出异常来触发异常处理
        with patch.object(
            traffic_service, "get_traffic_rule", side_effect=Exception("Test error")
        ):
            result = await traffic_service.check_plate_limited("京A12341", date.today())
            # 异常应该被捕获，返回False
            assert result.is_limited is False
            assert "Test error" in result.error_message

    def test_preload_cache_with_update_failure(self):
        """测试缓存预加载时更新失败情况"""
        traffic_service = TrafficService()

        # Mock _fetch_limit_rules_sync 返回 None
        with patch.object(
            traffic_service, "_fetch_limit_rules_sync", return_value=None
        ):
            traffic_service.preload_cache()
            # 预加载失败，状态应该是 error
            assert traffic_service._cache_status == "error"

    def test_check_plate_limited_on_no_memory_cache(self):
        """测试检查车牌限行 - 内存缓存为空"""
        traffic_service = TrafficService()
        traffic_service._memory_cache = None

        result = traffic_service.check_plate_limited_on("京A12345", date.today())
        assert result is False

    def test_check_plate_limited_on_with_single_number(self):
        """测试检查车牌限行 - 单个数字限行（不含'和'字符）"""
        traffic_service = TrafficService()
        target_date = date(2025, 12, 25)  # 使用未来日期避免与真实缓存冲突
        target_str = target_date.strftime("%Y年%m月%d日")

        traffic_service._memory_cache = [
            {"limitedTime": target_str, "limitedNumber": "13579"}  # 包含多个数字但不含'和'
        ]
        traffic_service._memory_cache_date = date.today()

        # 尾号1的车牌应该限行
        result = traffic_service.check_plate_limited_on("京A12341", target_date)
        assert result is True

        # 尾号2的车牌不应该限行
        result = traffic_service.check_plate_limited_on("京A12342", target_date)
        assert result is False

    def test_check_plate_limited_on_with_invalid_date(self):
        """测试检查车牌限行 - 包含无效日期格式"""
        traffic_service = TrafficService()
        target_date = date(2025, 12, 25)  # 使用未来日期避免与真实缓存冲突

        traffic_service._memory_cache = [
            {"limitedTime": "invalid_date_format", "limitedNumber": "1和6"},
            {"limitedTime": target_date.strftime("%Y年%m月%d日"), "limitedNumber": "2和7"},
        ]
        traffic_service._memory_cache_date = date.today()

        # 应该跳过无效日期，使用有效的规则
        result = traffic_service.check_plate_limited_on("京A12342", target_date)
        assert result is True

    def test_get_today_limit_info_no_rule(self):
        """测试获取今天限行信息 - 没有对应规则"""
        traffic_service = TrafficService()
        # 使用一个肯定不是今天的日期
        far_past = date(2020, 1, 1)
        far_past_str = far_past.strftime("%Y年%m月%d日")

        traffic_service._memory_cache = [
            {"limitedTime": far_past_str, "limitedNumber": "1和6"}
        ]
        traffic_service._memory_cache_date = date.today()

        # 今天没有规则，应该返回None
        result = traffic_service.get_today_limit_info()
        assert result is None
