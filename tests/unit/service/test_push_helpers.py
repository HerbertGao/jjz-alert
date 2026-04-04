"""
push_helpers 单元测试
"""

from unittest.mock import patch

import pytest

from jjz_alert.config.config import PlateConfig, NotificationConfig
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum
from jjz_alert.service.notification.push_helpers import (
    push_jjz_status,
    push_jjz_reminder,
    push_admin_notification,
    _is_system_error,
    _notify_admin_system_error,
    _notify_admin_network_error,
)
from jjz_alert.service.notification.push_priority import PushPriority


@pytest.mark.unit
class TestPushJJZStatus:
    """push_jjz_status 测试类"""

    @pytest.fixture
    def plate_config(self):
        """提供测试用的车牌配置"""
        return PlateConfig(
            plate="京A12345",
            display_name="测试车辆",
            icon="https://example.com/icon.png",
            notifications=[
                NotificationConfig(type="apprise", urls=["bark://test_key@api.day.app"])
            ],
        )

    @pytest.mark.asyncio
    async def test_push_jjz_status_valid(self, plate_config):
        """测试推送进京证状态 - 有效状态"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.NORMAL
            assert call_args.kwargs["title"] == "测试车辆"
            assert call_args.kwargs["icon"] == "https://example.com/icon.png"

    @pytest.mark.asyncio
    async def test_push_jjz_status_expired(self, plate_config):
        """测试推送进京证状态 - 过期状态"""
        jjz_data = {
            "status": JJZStatusEnum.EXPIRED.value,
            "sycs": "3",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.HIGH

    @pytest.mark.asyncio
    async def test_push_jjz_status_pending(self, plate_config):
        """测试推送进京证状态 - 审核中状态"""
        jjz_data = {
            "status": JJZStatusEnum.PENDING.value,
            "jjzzlmc": "进京证（六环内）",
            "apply_time": "2025-01-15 10:00:00",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.HIGH

    @pytest.mark.asyncio
    async def test_push_jjz_status_approved_pending(self, plate_config):
        """测试推送进京证状态 - 审核通过(待生效)状态"""
        jjz_data = {
            "status": JJZStatusEnum.APPROVED_PENDING.value,
            "jjzzlmc": "进京证（六环外）",
            "valid_start": "2026-04-05",
            "valid_end": "2026-04-11",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.NORMAL

    @pytest.mark.asyncio
    async def test_push_jjz_status_system_error(self, plate_config):
        """测试推送进京证状态 - 系统级错误"""
        jjz_data = {
            "status": "error",
            "error_message": "TLS connect error",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers._notify_admin_system_error"
        ) as mock_notify:
            result = await push_jjz_status(plate_config, jjz_data)

            assert result["skipped"] is True
            assert result["skip_reason"] == "系统级错误"
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_jjz_status_other_error(self, plate_config):
        """测试推送进京证状态 - 其他错误"""
        jjz_data = {
            "status": "error",
            "error_message": "用户输入错误",
            "jjzzlmc": "进京证（六环内）",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.NORMAL

    @pytest.mark.asyncio
    async def test_push_jjz_status_with_traffic_reminder_today(self, plate_config):
        """测试推送进京证状态 - 带今日限行提醒"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push, patch(
            "jjz_alert.base.message_templates.template_manager.format_traffic_reminder"
        ) as mock_format:
            mock_format.return_value = "🚗 今日限行\n"
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(
                plate_config, jjz_data, traffic_reminder="今日限行"
            )

            assert result["success_count"] == 1
            mock_format.assert_called_once_with("今日限行")

    @pytest.mark.asyncio
    async def test_push_jjz_status_with_traffic_reminder_tomorrow(self, plate_config):
        """测试推送进京证状态 - 带明日限行提醒"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push, patch(
            "jjz_alert.base.message_templates.template_manager.format_traffic_reminder"
        ) as mock_format:
            mock_format.return_value = "🚗 明日限行\n"
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(
                plate_config, jjz_data, traffic_reminder="明日限行"
            )

            assert result["success_count"] == 1
            mock_format.assert_called_once_with("明日限行")

    @pytest.mark.asyncio
    async def test_push_jjz_status_with_invalid_traffic_reminder(self, plate_config):
        """测试推送进京证状态 - 无效的限行提醒"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(
                plate_config, jjz_data, traffic_reminder="其他提醒"
            )

            assert result["success_count"] == 1
            # 不应该调用 format_traffic_reminder

    @pytest.mark.asyncio
    async def test_push_jjz_status_traffic_reminder_exception(self, plate_config):
        """测试推送进京证状态 - 限行提醒处理异常"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push, patch(
            "jjz_alert.base.message_templates.template_manager.format_traffic_reminder",
            side_effect=Exception("模板错误"),
        ):
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            # 应该不抛出异常，继续执行
            result = await push_jjz_status(
                plate_config, jjz_data, traffic_reminder="今日限行"
            )

            assert result["success_count"] == 1

    @pytest.mark.asyncio
    async def test_push_jjz_status_exception(self, plate_config):
        """测试推送进京证状态 - 异常处理"""
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push",
            side_effect=Exception("推送失败"),
        ):
            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 0
            assert result["total_count"] == 0
            assert len(result["errors"]) > 0
            assert "plate" in result

    @pytest.mark.asyncio
    async def test_push_jjz_status_no_display_name(self):
        """测试推送进京证状态 - 无显示名称"""
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(type="apprise", urls=["bark://test_key@api.day.app"])
            ],
        )
        jjz_data = {
            "status": JJZStatusEnum.VALID.value,
            "jjzzlmc": "进京证（六环内）",
            "blztmc": "审核通过(生效中)",
            "valid_start": "2025-01-01",
            "valid_end": "2025-01-31",
            "days_remaining": 10,
            "sycs": "5",
        }

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_status(plate_config, jjz_data)

            assert result["success_count"] == 1
            call_args = mock_push.call_args
            assert call_args.kwargs["title"] == "京A12345"  # 应该使用车牌号


@pytest.mark.unit
class TestPushJJZReminder:
    """push_jjz_reminder 测试类"""

    @pytest.fixture
    def plate_config(self):
        """提供测试用的车牌配置"""
        return PlateConfig(
            plate="京A12345",
            display_name="测试车辆",
            icon="https://example.com/icon.png",
            notifications=[
                NotificationConfig(type="apprise", urls=["bark://test_key@api.day.app"])
            ],
        )

    @pytest.mark.asyncio
    async def test_push_jjz_reminder_success(self, plate_config):
        """测试推送进京证提醒 - 成功"""
        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_reminder(
                plate_config, "测试提醒消息", PushPriority.HIGH
            )

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["title"] == "测试车辆"
            assert call_args.kwargs["body"] == "测试提醒消息"
            assert call_args.kwargs["priority"] == PushPriority.HIGH
            assert call_args.kwargs["icon"] == "https://example.com/icon.png"

    @pytest.mark.asyncio
    async def test_push_jjz_reminder_default_priority(self, plate_config):
        """测试推送进京证提醒 - 默认优先级"""
        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_reminder(plate_config, "测试提醒消息")

            assert result["success_count"] == 1
            call_args = mock_push.call_args
            assert call_args.kwargs["priority"] == PushPriority.HIGH

    @pytest.mark.asyncio
    async def test_push_jjz_reminder_exception(self, plate_config):
        """测试推送进京证提醒 - 异常处理"""
        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push",
            side_effect=Exception("推送失败"),
        ):
            result = await push_jjz_reminder(plate_config, "测试提醒消息")

            assert result["success_count"] == 0
            assert result["total_count"] == 0
            assert len(result["errors"]) > 0
            assert "plate" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_push_jjz_reminder_no_display_name(self):
        """测试推送进京证提醒 - 无显示名称"""
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(type="apprise", urls=["bark://test_key@api.day.app"])
            ],
        )

        with patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            mock_push.return_value = {
                "plate": "京A12345",
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_jjz_reminder(plate_config, "测试提醒消息")

            assert result["success_count"] == 1
            call_args = mock_push.call_args
            assert call_args.kwargs["title"] == "京A12345"


@pytest.mark.unit
class TestPushAdminNotification:
    """push_admin_notification 测试类"""

    @pytest.mark.asyncio
    async def test_push_admin_notification_success(self):
        """测试推送管理员通知 - 成功"""
        with patch(
            "jjz_alert.config.config.config_manager.load_config"
        ) as mock_load, patch(
            "jjz_alert.service.notification.push_helpers.unified_pusher.push"
        ) as mock_push:
            from jjz_alert.config.config_models import (
                AppConfig,
                GlobalConfig,
                AdminConfig,
            )

            mock_config = AppConfig()
            mock_config.global_config = GlobalConfig()
            mock_config.global_config.admin = AdminConfig()
            mock_config.global_config.admin.notifications = [
                NotificationConfig(type="apprise", urls=["bark://admin@api.day.app"])
            ]
            mock_load.return_value = mock_config

            mock_push.return_value = {
                "success_count": 1,
                "total_count": 1,
            }

            result = await push_admin_notification(
                title="测试标题", message="测试消息", priority=PushPriority.HIGH
            )

            assert result["success_count"] == 1
            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert call_args.kwargs["title"] == "测试标题"
            assert call_args.kwargs["body"] == "测试消息"
            assert call_args.kwargs["priority"] == PushPriority.HIGH

    @pytest.mark.asyncio
    async def test_push_admin_notification_no_config(self):
        """测试推送管理员通知 - 无配置"""
        with patch("jjz_alert.config.config.config_manager.load_config") as mock_load:
            from jjz_alert.config.config_models import (
                AppConfig,
                GlobalConfig,
                AdminConfig,
            )

            mock_config = AppConfig()
            mock_config.global_config = GlobalConfig()
            mock_config.global_config.admin = AdminConfig()
            mock_config.global_config.admin.notifications = []
            mock_load.return_value = mock_config

            result = await push_admin_notification(title="测试标题", message="测试消息")

            assert result["success_count"] == 0
            assert result["total_count"] == 0
            assert "未配置管理员通知" in result["errors"]

    @pytest.mark.asyncio
    async def test_push_admin_notification_exception(self):
        """测试推送管理员通知 - 异常处理"""
        with patch(
            "jjz_alert.config.config.config_manager.load_config",
            side_effect=Exception("配置加载失败"),
        ):
            result = await push_admin_notification(title="测试标题", message="测试消息")

            assert result["success_count"] == 0
            assert result["total_count"] == 0
            assert len(result["errors"]) > 0
            assert "timestamp" in result


@pytest.mark.unit
class TestIsSystemError:
    """_is_system_error 测试类"""

    def test_is_system_error_tls_error(self):
        """测试系统错误检测 - TLS错误"""
        assert _is_system_error("TLS connect error") is True
        assert _is_system_error("OPENSSL_internal error") is True
        assert _is_system_error("curl: (35) SSL error") is True

    def test_is_system_error_network_error(self):
        """测试系统错误检测 - 网络错误"""
        assert _is_system_error("网络连接失败") is True
        assert _is_system_error("网络TLS错误") is True
        assert _is_system_error("TLS连接失败") is True
        assert _is_system_error("Connection timeout") is True
        assert _is_system_error("连接超时") is True

    def test_is_system_error_ssl_error(self):
        """测试系统错误检测 - SSL错误"""
        assert _is_system_error("SSL certificate error") is True
        assert _is_system_error("TLS handshake failed") is True

    def test_is_system_error_api_error(self):
        """测试系统错误检测 - API错误"""
        assert (
            _is_system_error("Session.request() got an unexpected keyword argument")
            is True
        )
        assert _is_system_error("HTTP POST请求失败") is True
        assert _is_system_error("HTTP GET请求失败") is True
        assert _is_system_error("进京证查询失败") is True

    def test_is_system_error_system_error(self):
        """测试系统错误检测 - 系统级错误"""
        assert _is_system_error("系统错误") is True
        assert _is_system_error("服务不可用") is True
        assert _is_system_error("服务器错误") is True
        assert _is_system_error("API错误") is True
        assert _is_system_error("配置错误") is True
        assert _is_system_error("未配置") is True
        assert _is_system_error("初始化失败") is True

    def test_is_system_error_case_insensitive(self):
        """测试系统错误检测 - 大小写不敏感"""
        assert _is_system_error("TLS CONNECT ERROR") is True
        assert _is_system_error("tls connect error") is True
        assert _is_system_error("Tls Connect Error") is True

    def test_is_system_error_not_system_error(self):
        """测试系统错误检测 - 非系统错误"""
        assert _is_system_error("用户输入错误") is False
        assert _is_system_error("车牌号格式错误") is False
        assert _is_system_error("") is False
        assert _is_system_error(None) is False


@pytest.mark.unit
class TestNotifyAdminSystemError:
    """_notify_admin_system_error 测试类"""

    @pytest.mark.asyncio
    async def test_notify_admin_system_error_success(self):
        """测试通知管理员系统错误 - 成功"""
        with patch(
            "jjz_alert.service.notification.push_helpers.push_admin_notification"
        ) as mock_push:
            await _notify_admin_system_error(
                "京A12345", "测试车辆", "TLS connect error"
            )

            mock_push.assert_called_once()
            call_args = mock_push.call_args
            assert "进京证查询系统错误" in call_args.kwargs["title"]
            assert "京A12345" in call_args.kwargs["message"]
            assert "测试车辆" in call_args.kwargs["message"]
            assert "TLS connect error" in call_args.kwargs["message"]
            assert call_args.kwargs["priority"] == PushPriority.HIGH
            assert call_args.kwargs["category"] == "system_error"

    @pytest.mark.asyncio
    async def test_notify_admin_system_error_exception(self):
        """测试通知管理员系统错误 - 异常处理"""
        with patch(
            "jjz_alert.service.notification.push_helpers.push_admin_notification",
            side_effect=Exception("推送失败"),
        ):
            # 应该不抛出异常，只记录日志
            await _notify_admin_system_error(
                "京A12345", "测试车辆", "TLS connect error"
            )


@pytest.mark.unit
class TestNotifyAdminNetworkError:
    """_notify_admin_network_error 测试类"""

    @pytest.mark.asyncio
    async def test_notify_admin_network_error(self):
        """测试通知管理员网络错误"""
        with patch(
            "jjz_alert.service.notification.push_helpers._notify_admin_system_error"
        ) as mock_notify:
            await _notify_admin_network_error("京A12345", "测试车辆", "网络连接失败")

            mock_notify.assert_called_once_with("京A12345", "测试车辆", "网络连接失败")
