"""
JJZService 单元测试
"""

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest

from jjz_alert.service.jjz.jjz_service import JJZService, JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.jjz.jjz_parse import (
    parse_all_jjz_records,
    parse_jjz_response,
)


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

    @pytest.mark.asyncio
    async def test_fetch_from_api_without_accounts(self, jjz_service):
        """测试 _fetch_from_api 在无账户配置时的行为"""
        with patch.object(jjz_service, "_load_accounts", return_value=[]):
            with patch(
                "jjz_alert.service.jjz.jjz_service.handle_critical_error",
                new_callable=AsyncMock,
            ) as mock_handle:
                status = await jjz_service._fetch_from_api("京Z00001")

        assert status.status == "error"
        assert status.error_message == "未配置进京证账户"
        mock_handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_from_api_handles_token_error_and_returns_latest(
        self, jjz_service
    ):
        """测试 _fetch_from_api 在Token错误后仍能返回最新记录"""
        plate = "京A12345"

        def build_account(name: str):
            account = Mock()
            account.name = name
            account.jjz = Mock(url=f"https://{name}.example.com", token=f"{name}_token")
            return account

        token_error_account = build_account("token_error")
        valid_account = build_account("valid_account")

        with patch.object(
            jjz_service,
            "_load_accounts",
            return_value=[token_error_account, valid_account],
        ):
            with patch.object(
                jjz_service,
                "_check_jjz_status",
                side_effect=[{"error": "Token可能已失效"}, {"data": {"bzclxx": []}}],
            ) as mock_check, patch(
                "jjz_alert.service.jjz.jjz_service.parse_all_jjz_records",
                return_value=[
                    JJZStatus(
                        plate=plate,
                        status=JJZStatusEnum.PENDING.value,
                        apply_time="2025-08-14 09:00:00",
                    ),
                    JJZStatus(
                        plate=plate,
                        status=JJZStatusEnum.VALID.value,
                        apply_time="2025-08-15 10:00:00",
                    ),
                    JJZStatus(
                        plate="京B00001",
                        status=JJZStatusEnum.EXPIRED.value,
                        apply_time="2025-08-13 08:00:00",
                    ),
                ],
            ) as mock_parse, patch(
                "jjz_alert.service.jjz.jjz_service.handle_critical_error",
                new_callable=AsyncMock,
            ) as mock_handle:
                status = await jjz_service._fetch_from_api(plate)

        assert status.status == JJZStatusEnum.VALID.value
        assert status.apply_time == "2025-08-15 10:00:00"
        mock_check.assert_called_with(valid_account.jjz.url, valid_account.jjz.token)
        mock_parse.assert_called_once()
        mock_handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_from_api_all_accounts_failed(self, jjz_service):
        """测试 _fetch_from_api 所有账户均失败时返回错误"""
        account = Mock()
        account.name = "account_a"
        account.jjz = Mock(url="https://api.example.com", token="bad_token")

        with patch.object(jjz_service, "_load_accounts", return_value=[account]):
            with patch.object(
                jjz_service, "_check_jjz_status", return_value={"error": "网络错误"}
            ), patch(
                "jjz_alert.service.jjz.jjz_service.handle_critical_error",
                new_callable=AsyncMock,
            ) as mock_handle:
                status = await jjz_service._fetch_from_api("京C00001")

        assert status.status == "error"
        assert status.error_message == "网络错误"
        mock_handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_from_api_no_matching_records(self, jjz_service):
        """测试 _fetch_from_api 成功查询但无匹配车牌"""
        plate = "京D00001"
        account = Mock()
        account.name = "account_b"
        account.jjz = Mock(url="https://api.example.com", token="valid_token")

        with patch.object(jjz_service, "_load_accounts", return_value=[account]):
            with patch.object(
                jjz_service, "_check_jjz_status", return_value={"data": {"bzclxx": []}}
            ), patch(
                "jjz_alert.service.jjz.jjz_service.parse_all_jjz_records",
                return_value=[
                    JJZStatus(
                        plate="京X99999",
                        status=JJZStatusEnum.VALID.value,
                        apply_time="2025-08-15 08:00:00",
                    )
                ],
            ):
                status = await jjz_service._fetch_from_api(plate)

        assert status.status == JJZStatusEnum.INVALID.value
        assert "未找到匹配车牌的记录" in status.error_message

    def test_check_jjz_status_tls_error(self, jjz_service):
        """测试进京证状态查询 - TLS错误"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.side_effect = Exception("TLS connect error")
            with patch(
                "jjz_alert.service.jjz.jjz_service.asyncio.create_task"
            ) as mock_task:
                result = jjz_service._check_jjz_status(url, token)

                assert "error" in result
                assert "TLS/SSL连接错误" in result["error"]
                # 验证异步任务被创建
                mock_task.assert_called_once()

    def test_check_jjz_status_connection_error(self, jjz_service):
        """测试进京证状态查询 - 连接错误"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.side_effect = Exception("Connection timeout")
            with patch(
                "jjz_alert.service.jjz.jjz_service.asyncio.create_task"
            ) as mock_task:
                result = jjz_service._check_jjz_status(url, token)

                assert "error" in result
                assert "网络连接错误" in result["error"]
                mock_task.assert_called_once()

    def test_check_jjz_status_http_error(self, jjz_service):
        """测试进京证状态查询 - HTTP错误"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.side_effect = Exception("HTTP POST请求失败")
            with patch(
                "jjz_alert.service.jjz.jjz_service.asyncio.create_task"
            ) as mock_task:
                result = jjz_service._check_jjz_status(url, token)

                assert "error" in result
                assert "HTTP请求失败" in result["error"]
                mock_task.assert_called_once()

    def test_check_jjz_status_session_request_error(self, jjz_service):
        """测试进京证状态查询 - Session.request()错误"""
        url = "https://test.example.com"
        token = "test_token"

        with patch("jjz_alert.service.jjz.jjz_service.http_post") as mock_post:
            mock_post.side_effect = Exception(
                "Session.request() got an unexpected keyword argument"
            )
            with patch(
                "jjz_alert.service.jjz.jjz_service.asyncio.create_task"
            ) as mock_task:
                result = jjz_service._check_jjz_status(url, token)

                assert "error" in result
                assert "HTTP请求参数错误" in result["error"]
                mock_task.assert_called_once()

    def test_load_accounts_success(self, jjz_service):
        """测试加载账户配置 - 成功"""
        from jjz_alert.config.config import config_manager

        with patch.object(config_manager, "load_config") as mock_load:
            from jjz_alert.config.config import AppConfig, JJZAccount, JJZConfig

            mock_config = AppConfig()
            mock_config.jjz_accounts = [
                JJZAccount(
                    name="测试账户",
                    jjz=JJZConfig(token="test_token", url="https://test.example.com"),
                )
            ]
            mock_load.return_value = mock_config

            accounts = jjz_service._load_accounts()

            assert len(accounts) == 1
            assert accounts[0].name == "测试账户"

    def test_load_accounts_cached(self, jjz_service):
        """测试加载账户配置 - 使用缓存"""
        from jjz_alert.config.config import config_manager

        with patch.object(config_manager, "load_config") as mock_load:
            from jjz_alert.config.config import AppConfig, JJZAccount, JJZConfig

            mock_config = AppConfig()
            mock_config.jjz_accounts = [
                JJZAccount(
                    name="测试账户",
                    jjz=JJZConfig(token="test_token", url="https://test.example.com"),
                )
            ]
            mock_load.return_value = mock_config

            # 第一次加载
            accounts1 = jjz_service._load_accounts()
            # 第二次加载（应该使用缓存）
            accounts2 = jjz_service._load_accounts()

            assert len(accounts1) == 1
            assert len(accounts2) == 1
            # 验证只调用了一次（缓存生效）
            assert mock_load.call_count == 1

    def test_load_accounts_exception(self, jjz_service):
        """测试加载账户配置 - 异常处理"""
        from jjz_alert.config.config import config_manager

        with patch.object(config_manager, "load_config") as mock_load:
            mock_load.side_effect = Exception("配置加载失败")

            accounts = jjz_service._load_accounts()

            assert accounts == []

    def test_determine_status_no_yxqz(self, jjz_service):
        """测试状态判断 - 无有效期结束日期"""
        status = jjz_service._determine_status("1", "审核通过(生效中)", "", None)
        assert status == JJZStatusEnum.INVALID.value

    def test_determine_status_pending_in_range(self, jjz_service):
        """测试状态判断 - 待生效但在有效期内"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 16)
            status = jjz_service._determine_status(
                "6", "审核通过(待生效)", "2025-08-20", "2025-08-15"
            )
            assert status == JJZStatusEnum.VALID.value

    def test_determine_status_pending_not_started(self, jjz_service):
        """测试状态判断 - 待生效但未到生效时间"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 10)
            status = jjz_service._determine_status(
                "6", "审核通过(待生效)", "2025-08-20", "2025-08-15"
            )
            assert status == JJZStatusEnum.PENDING.value

    def test_determine_status_pending_no_yxqs(self, jjz_service):
        """测试状态判断 - 待生效但无开始日期"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 16)
            status = jjz_service._determine_status(
                "6", "审核通过(待生效)", "2025-08-20", None
            )
            assert status == JJZStatusEnum.PENDING.value

    def test_determine_status_auditing(self, jjz_service):
        """测试状态判断 - 审核中"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)
            status = jjz_service._determine_status(
                "0", "审核中", "2025-08-20", "2025-08-15"
            )
            assert status == JJZStatusEnum.PENDING.value

    def test_determine_status_exception(self, jjz_service):
        """测试状态判断 - 异常处理"""
        status = jjz_service._determine_status(
            "invalid", "invalid", "invalid-date", None
        )
        assert status == JJZStatusEnum.INVALID.value

    def test_determine_status_pending_invalid_yxqs(self, jjz_service):
        """测试状态判断 - 待生效但yxqs日期格式无效"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 16)
            # 使用无效的日期格式触发异常
            status = jjz_service._determine_status(
                "6", "审核通过(待生效)", "2025-08-20", "invalid-date"
            )
            assert status == JJZStatusEnum.PENDING.value

    def test_determine_status_unknown_blzt(self, jjz_service):
        """测试状态判断 - 未知的blzt值"""
        with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
            mock_date.today.return_value = date(2025, 8, 15)
            # 使用未知的blzt值，不匹配任何条件
            status = jjz_service._determine_status(
                "99", "未知状态", "2025-08-20", "2025-08-15"
            )
            assert status == JJZStatusEnum.INVALID.value

    @pytest.mark.asyncio
    async def test_get_jjz_status_exception(self, jjz_service):
        """测试获取进京证状态 - 异常处理"""
        plate = "京A12345"

        with patch.object(jjz_service, "_fetch_from_api") as mock_fetch:
            mock_fetch.side_effect = Exception("测试异常")

            status = await jjz_service.get_jjz_status(plate)

            assert status.plate == plate
            assert status.status == "error"
            assert "测试异常" in status.error_message

    @pytest.mark.asyncio
    async def test_get_multiple_status_optimized(self, jjz_service, sample_jjz_account):
        """测试优化的批量获取状态"""
        plates = ["京A12345", "京B67890"]

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [sample_jjz_account]

            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                mock_check.return_value = {
                    "data": {
                        "bzclxx": [
                            {
                                "hphm": "京A12345",
                                "sycs": "8",
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
                            },
                            {
                                "hphm": "京B67890",
                                "sycs": "5",
                                "bzxx": [
                                    {
                                        "jjzzlmc": "进京证(六环外)",
                                        "blztmc": "审核通过(生效中)",
                                        "blzt": "1",
                                        "sqsj": "2025-08-16 10:00:00",
                                        "yxqs": "2025-08-16",
                                        "yxqz": "2025-08-21",
                                        "sxsyts": "3",
                                    }
                                ],
                            },
                        ]
                    }
                }

                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date(2025, 8, 15)

                    results = await jjz_service.get_multiple_status_optimized(plates)

                    assert len(results) == 2
                    assert results["京A12345"].status == JJZStatusEnum.VALID.value
                    assert results["京B67890"].status == JJZStatusEnum.VALID.value

    @pytest.mark.asyncio
    async def test_get_multiple_status_optimized_no_accounts(self, jjz_service):
        """测试优化的批量获取状态 - 无账户"""
        plates = ["京A12345", "京B67890"]

        with patch.object(jjz_service, "_load_accounts", return_value=[]):
            results = await jjz_service.get_multiple_status_optimized(plates)

            assert len(results) == 2
            assert results["京A12345"].status == "error"
            assert results["京B67890"].status == "error"

    @pytest.mark.asyncio
    async def test_get_multiple_status_optimized_no_match(
        self, jjz_service, sample_jjz_account
    ):
        """测试优化的批量获取状态 - 无匹配记录"""
        plates = ["京C99999"]

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [sample_jjz_account]

            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                mock_check.return_value = {
                    "data": {
                        "bzclxx": [
                            {
                                "hphm": "京A12345",
                                "bzxx": [
                                    {
                                        "blzt": "1",
                                        "blztmc": "审核通过(生效中)",
                                        "sqsj": "2025-08-15 10:00:00",
                                        "yxqs": "2025-08-15",
                                        "yxqz": "2025-08-20",
                                        "sxsyts": "5",
                                    }
                                ],
                            }
                        ]
                    }
                }

                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date(2025, 8, 15)

                    results = await jjz_service.get_multiple_status_optimized(plates)

                    assert len(results) == 1
                    assert results["京C99999"].status == "invalid"
                    assert "未找到匹配车牌的记录" in results["京C99999"].error_message

    @pytest.mark.asyncio
    async def test_get_multiple_status_optimized_account_error(
        self, jjz_service, sample_jjz_account
    ):
        """测试优化的批量获取状态 - 账户返回错误"""
        plates = ["京A12345"]

        account1 = sample_jjz_account
        account2 = Mock()
        account2.name = "账户2"
        account2.jjz = Mock(url="https://account2.example.com", token="token2")

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [account1, account2]

            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                # 第一个账户返回错误，第二个账户成功
                mock_check.side_effect = [
                    {"error": "账户1查询失败"},
                    {
                        "data": {
                            "bzclxx": [
                                {
                                    "hphm": "京A12345",
                                    "sycs": "8",
                                    "bzxx": [
                                        {
                                            "blzt": "1",
                                            "blztmc": "审核通过(生效中)",
                                            "sqsj": "2025-08-15 10:00:00",
                                            "yxqs": "2025-08-15",
                                            "yxqz": "2025-08-20",
                                            "sxsyts": "5",
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                ]

                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date(2025, 8, 15)

                    results = await jjz_service.get_multiple_status_optimized(plates)

                    assert len(results) == 1
                    assert results["京A12345"].status == JJZStatusEnum.VALID.value

    @pytest.mark.asyncio
    async def test_get_multiple_status_optimized_account_exception(
        self, jjz_service, sample_jjz_account
    ):
        """测试优化的批量获取状态 - 账户查询抛出异常"""
        plates = ["京A12345"]

        account1 = sample_jjz_account
        account2 = Mock()
        account2.name = "账户2"
        account2.jjz = Mock(url="https://account2.example.com", token="token2")

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [account1, account2]

            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                # 第一个账户抛出异常，第二个账户成功
                mock_check.side_effect = [
                    Exception("账户1异常"),
                    {
                        "data": {
                            "bzclxx": [
                                {
                                    "hphm": "京A12345",
                                    "sycs": "8",
                                    "bzxx": [
                                        {
                                            "blzt": "1",
                                            "blztmc": "审核通过(生效中)",
                                            "sqsj": "2025-08-15 10:00:00",
                                            "yxqs": "2025-08-15",
                                            "yxqz": "2025-08-20",
                                            "sxsyts": "5",
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                ]

                with patch("jjz_alert.service.jjz.jjz_service.date") as mock_date:
                    mock_date.today.return_value = date(2025, 8, 15)

                    results = await jjz_service.get_multiple_status_optimized(plates)

                    assert len(results) == 1
                    assert results["京A12345"].status == JJZStatusEnum.VALID.value

    @pytest.mark.asyncio
    async def test_fetch_from_api_exception(self, jjz_service, sample_jjz_account):
        """测试 _fetch_from_api - 异常处理"""
        plate = "京A12345"

        with patch.object(jjz_service, "_load_accounts") as mock_load:
            mock_load.return_value = [sample_jjz_account]

            with patch.object(jjz_service, "_check_jjz_status") as mock_check:
                mock_check.side_effect = Exception("网络异常")

                status = await jjz_service._fetch_from_api(plate)

                # 当异常发生时，会记录错误但继续处理，最终返回 invalid 状态
                assert status.status in ("invalid", "error")
                if status.status == "invalid":
                    assert "未找到匹配车牌的记录" in status.error_message
                else:
                    assert "网络异常" in status.error_message

    @pytest.mark.asyncio
    async def test_cache_status_exception(self, jjz_service):
        """测试缓存状态 - 异常处理"""
        status = JJZStatus(
            plate="京A12345", status=JJZStatusEnum.VALID.value, data_source="api"
        )

        jjz_service.cache_service.cache_jjz_data.side_effect = Exception("缓存失败")

        result = await jjz_service._cache_status(status)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_multiple_status_exception(self, jjz_service):
        """测试批量获取状态 - 异常处理"""
        plates = ["京A12345"]

        with patch.object(jjz_service, "get_jjz_status") as mock_get:
            mock_get.side_effect = Exception("查询失败")

            results = await jjz_service.get_multiple_status(plates)

            assert len(results) == 1
            assert results["京A12345"].status == "error"
            assert "查询失败" in results["京A12345"].error_message

    @pytest.mark.asyncio
    async def test_refresh_cache_exception(self, jjz_service):
        """测试刷新缓存 - 异常处理"""
        plate = "京A12345"

        jjz_service.cache_service.delete_jjz_data.side_effect = Exception("删除失败")

        result = await jjz_service.refresh_cache(plate)

        assert result.status == "error"
        assert "删除失败" in result.error_message

    @pytest.mark.asyncio
    async def test_get_cached_plates_exception(self, jjz_service):
        """测试获取缓存车牌 - 异常处理"""
        jjz_service.cache_service.get_all_jjz_plates.side_effect = Exception("获取失败")

        result = await jjz_service.get_cached_plates()

        assert result == []

    @pytest.mark.asyncio
    async def test_check_expiring_permits_exception(self, jjz_service):
        """测试检查即将过期的进京证 - 异常处理"""
        jjz_service.cache_service.get_all_jjz_plates.side_effect = Exception("获取失败")

        result = await jjz_service.check_expiring_permits()

        assert result == []

    @pytest.mark.asyncio
    async def test_check_expiring_permits_exception_in_loop(self, jjz_service):
        """测试检查即将过期的进京证 - 循环中异常处理"""
        cached_plates = ["京A12345", "京B67890"]
        jjz_service.cache_service.get_all_jjz_plates.return_value = cached_plates

        # Mock get_jjz_status 在第二次调用时抛出异常
        call_count = 0

        async def mock_get_status(plate):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.VALID.value,
                    days_remaining=2,
                    data_source="cache",
                )
            else:
                raise Exception("查询失败")

        with patch.object(jjz_service, "get_jjz_status", side_effect=mock_get_status):
            result = await jjz_service.check_expiring_permits()

            # 即使有异常，也应该返回已处理的结果
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_service_status_exception(self, jjz_service):
        """测试获取服务状态 - 异常处理"""
        jjz_service.cache_service.get_cache_stats = AsyncMock(
            side_effect=Exception("获取失败")
        )

        result = await jjz_service.get_service_status()

        assert result["service"] == "JJZService"
        assert result["status"] == "error"
        assert "获取失败" in result["error"]

    @pytest.mark.asyncio
    async def test_notify_admin_system_error(self, jjz_service):
        """测试通知管理员系统错误"""
        with patch(
            "jjz_alert.service.notification.push_helpers.push_admin_notification",
            new_callable=AsyncMock,
        ) as mock_push:
            await jjz_service._notify_admin_system_error("测试错误", "错误详情")

            mock_push.assert_awaited_once()
            call_args = mock_push.call_args
            assert "进京证查询系统错误" in call_args[1]["title"]
            assert "测试错误" in call_args[1]["message"]

    @pytest.mark.asyncio
    async def test_notify_admin_system_error_exception(self, jjz_service):
        """测试通知管理员系统错误 - 异常处理"""
        with patch(
            "jjz_alert.service.notification.push_helpers.push_admin_notification",
            new_callable=AsyncMock,
        ) as mock_push:
            mock_push.side_effect = Exception("通知失败")

            # 应该不会抛出异常
            await jjz_service._notify_admin_system_error("测试错误", "错误详情")

    @pytest.mark.asyncio
    async def test_notify_admin_network_error(self, jjz_service):
        """测试通知管理员网络错误"""
        with patch.object(
            jjz_service, "_notify_admin_system_error", new_callable=AsyncMock
        ) as mock_notify:
            await jjz_service._notify_admin_network_error("网络错误", "连接超时")

            mock_notify.assert_awaited_once_with("网络错误", "连接超时")
