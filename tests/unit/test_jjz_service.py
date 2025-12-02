"""
JJZService 单元测试
"""

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest

from jjz_alert.service.jjz.jjz_parse import (
    parse_all_jjz_records,
    parse_jjz_response,
)
from jjz_alert.service.jjz.jjz_service import JJZService, JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


@pytest.mark.unit
class TestJJZService:
    """JJZService测试类"""

    @pytest.fixture
    def jjz_service(self):
        """创建JJZService实例"""
        # 创建Mock缓存服务
        mock_cache = Mock()
        mock_cache.get_jjz_data = AsyncMock()
        mock_cache.cache_jjz_data = AsyncMock()
        mock_cache.delete_jjz_data = AsyncMock()
        mock_cache.get_all_jjz_plates = AsyncMock()
        mock_cache.get_cache_stats = AsyncMock()

        return JJZService(mock_cache)

    def test_determine_status_valid(self, jjz_service):
        """测试新版状态判断 - 生效中"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)
            status = jjz_service._determine_status(
                "1", "审核通过(生效中)", "2025-08-20", "2025-08-15"
            )
        assert status == JJZStatusEnum.VALID.value

    def test_determine_status_pending(self, jjz_service):
        """测试新版状态判断 - 待生效"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 10)
            status = jjz_service._determine_status(
                "6", "审核通过(待生效)", "2025-08-20", "2025-08-15"
            )
            assert status == JJZStatusEnum.PENDING.value

    def test_determine_status_expired(self, jjz_service):
        """测试新版状态判断 - 已过期"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 25)
            status = jjz_service._determine_status(
                "1", "审核通过(生效中)", "2025-08-20", "2025-08-15"
            )
        assert status == JJZStatusEnum.EXPIRED.value

    def test_parse_jjz_response_success(self, jjz_service):
        """测试解析进京证API响应 - 成功"""
        plate = "京A12345"
        response_data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "bzxx": [
                            {
                                "jjzzlmc": "进京证(六环内)",
                                "blztmc": "审核通过(生效中)",
                                "blzt": "1",
                                "sqsj": "2025-08-15 10:00:00",
                                "yxqs": "2025-08-15 00:00:00",
                                "yxqz": "2025-08-20",
                                "sxsyts": "5",
                                "sycs": "8",
                            }
                        ],
                    }
                ]
            }
        }

        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)

            status = parse_jjz_response(
                plate, response_data, jjz_service._determine_status, JJZStatus
            )

            assert status.plate == plate
            assert status.status == JJZStatusEnum.VALID.value
            assert status.apply_time == "2025-08-15 10:00:00"
            assert status.data_source == "api"

    def test_parse_jjz_response_error(self, jjz_service):
        """测试解析进京证API响应 - 错误"""
        plate = "京A12345"
        response_data = {"error": "网络连接失败"}

        status = parse_jjz_response(
            plate, response_data, jjz_service._determine_status, JJZStatus
        )

        assert status.plate == plate
        assert status.status == "error"
        assert status.error_message == "网络连接失败"
        assert status.data_source == "api"

    def test_parse_jjz_response_no_records(self, jjz_service):
        """测试解析进京证API响应 - 无记录"""
        plate = "京A12345"
        response_data = {"data": {"bzclxx": []}}

        status = parse_jjz_response(
            plate, response_data, jjz_service._determine_status, JJZStatus
        )
        assert status.plate == plate
        assert status.status == "invalid"
        assert "未找到车辆信息" in status.error_message

    def test_parse_all_jjz_records(self, jjz_service):
        """测试批量解析所有车牌记录"""
        response_data = {
            "data": {
                "bzclxx": [
                    {
                        "hphm": "京A12345",
                        "sycs": "5",
                        "bzxx": [
                            {
                                "jjzzlmc": "进京证(六环内)",
                                "blztmc": "审核通过(生效中)",
                                "blzt": "1",
                                "sqsj": "2025-08-15 10:00:00",
                                "yxqs": "2025-08-15",
                                "yxqz": "2025-08-20",
                                "sxsyts": "5",
                            }
                        ],
                        "ecbzxx": [
                            {
                                "jjzzlmc": "进京证(六环内)",
                                "blztmc": "审核通过(待生效)",
                                "blzt": "6",
                                "sqsj": "2025-08-25 10:00:00",
                                "yxqs": "2025-08-26",
                                "yxqz": "2025-08-30",
                                "sxsyts": "0",
                            }
                        ],
                    }
                ]
            }
        }

        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)
            records = parse_all_jjz_records(
                response_data, jjz_service._determine_status, JJZStatus
            )

        assert len(records) == 2
        assert records[0].status == JJZStatusEnum.VALID.value
        assert records[1].status == JJZStatusEnum.PENDING.value

    @pytest.mark.asyncio
    async def test_get_jjz_status_always_fetch_from_api(
        self, jjz_service, sample_jjz_account
    ):
        """测试获取进京证状态 - 每次都从API获取"""
        plate = "京A12345"

        # Mock配置加载
        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [sample_jjz_account]

            # Mock API调用
            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                mock_check.return_value = {
                    "data": {
                        "bzclxx": [
                            {
                                "hphm": plate,
                                "bzxx": [
                                    {
                                        "jjzzlmc": "进京证(六环内)",
                                        "blztmc": "审核通过(生效中)",
                                        "blzt": "1",
                                        "sqsj": "2025-08-15 10:00:00",
                                        "yxqs": "2025-08-15 00:00:00",
                                        "yxqz": "2025-08-20",
                                        "sxsyts": "5",
                                        "sycs": "8",
                                    }
                                ],
                            }
                        ]
                    }
                }

                # Mock缓存操作
                jjz_service.cache_service.cache_jjz_data.return_value = True

                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date(2025, 8, 15)

                    status = await jjz_service.get_jjz_status(plate)

                assert status.plate == plate
                assert status.status == JJZStatusEnum.VALID.value
                assert status.data_source == "api"

                # 验证API被调用
                mock_check.assert_called_once()
                # 验证结果被缓存
                jjz_service.cache_service.cache_jjz_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_jjz_status_api_error(self, jjz_service, sample_jjz_account):
        """测试获取进京证状态 - API错误"""
        plate = "京A12345"

        # Mock配置加载
        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [sample_jjz_account]

            # Mock API调用返回错误
            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                mock_check.return_value = {"error": "API连接失败"}

                status = await jjz_service.get_jjz_status(plate)

                assert status.plate == plate
                assert status.status == "error"
                assert "API连接失败" in status.error_message
                assert status.data_source == "api"

    @pytest.mark.asyncio
    async def test_get_jjz_status_no_accounts(self, jjz_service):
        """测试获取进京证状态 - 无配置账户"""
        plate = "京A12345"

        jjz_service.cache_service.get_jjz_data.return_value = None

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = []

            status = await jjz_service.get_jjz_status(plate)

            assert status.plate == plate
            assert status.status == "error"
            assert "未配置进京证账户" in status.error_message

    @pytest.mark.asyncio
    async def test_get_multiple_status(self, jjz_service):
        """测试批量获取多个车牌状态"""
        plates = ["京A12345", "京B67890"]

        # Mock get_jjz_status方法
        async def mock_get_status(plate):
            return JJZStatus(
                plate=plate,
                status=(
                    JJZStatusEnum.VALID.value
                    if plate == "京A12345"
                    else JJZStatusEnum.EXPIRED.value
                ),
                data_source="api",
            )

        with patch.object(jjz_service, "get_jjz_status", side_effect=mock_get_status):
            results = await jjz_service.get_multiple_status(plates)

            assert len(results) == 2
            assert results["京A12345"].status == JJZStatusEnum.VALID.value
            assert results["京B67890"].status == "expired"

    @pytest.mark.asyncio
    async def test_refresh_cache(self, jjz_service, sample_jjz_account):
        """测试强制刷新缓存"""
        plate = "京A12345"

        # Mock删除缓存
        jjz_service.cache_service.delete_jjz_data.return_value = True

        # Mock重新获取
        with patch.object(jjz_service, "get_jjz_status") as mock_get:
            mock_status = JJZStatus(
                plate=plate, status=JJZStatusEnum.VALID.value, data_source="api"
            )
            mock_get.return_value = mock_status

            result = await jjz_service.refresh_cache(plate)

            assert result == mock_status
            jjz_service.cache_service.delete_jjz_data.assert_called_once_with(plate)
            mock_get.assert_called_once_with(plate)

    @pytest.mark.asyncio
    async def test_get_cached_plates(self, jjz_service):
        """测试获取缓存车牌列表"""
        cached_plates = ["京A12345", "京B67890"]
        jjz_service.cache_service.get_all_jjz_plates.return_value = cached_plates

        result = await jjz_service.get_cached_plates()

        assert result == cached_plates
        jjz_service.cache_service.get_all_jjz_plates.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_expiring_permits(self, jjz_service):
        """测试检查即将过期的进京证"""
        cached_plates = ["京A12345", "京B67890"]

        jjz_service.cache_service.get_all_jjz_plates.return_value = cached_plates

        # Mock get_jjz_status返回不同状态
        async def mock_get_status(plate):
            if plate == "京A12345":
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.VALID.value,
                    days_remaining=2,
                    data_source="cache",
                )
            else:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.VALID.value,
                    days_remaining=10,
                    data_source="cache",
                )

        with patch.object(jjz_service, "get_jjz_status", side_effect=mock_get_status):
            expiring = await jjz_service.check_expiring_permits(days_threshold=3)

            assert len(expiring) == 1
            assert expiring[0].plate == "京A12345"
            assert expiring[0].days_remaining == 2

    @pytest.mark.asyncio
    async def test_get_service_status(self, jjz_service):
        """测试获取服务状态"""
        # Mock依赖方法
        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [Mock(), Mock()]  # 2个账户

            jjz_service.cache_service.get_all_jjz_plates.return_value = ["京A12345"]
            jjz_service.cache_service.get_cache_stats.return_value = {
                "jjz": {"total_hits": 10, "total_misses": 2, "hit_rate": 83.33}
            }

            status = await jjz_service.get_service_status()

            assert status["service"] == "JJZService"
            assert status["status"] == "healthy"
            assert status["accounts_count"] == 2
            assert status["cached_plates_count"] == 1
            assert status["cache_stats"]["hits"] == 10
            assert status["cache_stats"]["hit_rate"] == 83.33

    def test_check_jjz_status_success(self, jjz_service, mock_http_response):
        """测试进京证状态查询成功"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.return_value = mock_http_response

            result = jjz_service._check_jjz_status(url, token)

            assert result == mock_http_response.json.return_value
            mock_post.assert_called_once_with(
                url,
                headers={"Authorization": token, "Content-Type": "application/json"},
                json_data={},
            )

    def test_check_jjz_status_error(self, jjz_service):
        """测试进京证状态查询异常"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.side_effect = Exception("网络连接失败")

            result = jjz_service._check_jjz_status(url, token)

            assert "error" in result
            assert result["error"] == "网络连接失败"
