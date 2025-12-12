"""
ApprisePusher 单元测试
"""

from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

import pytest

from jjz_alert.service.notification.apprise_pusher import ApprisePusher
from jjz_alert.service.notification.apprise_config import AppriseConfig


@pytest.mark.unit
class TestApprisePusher:
    """ApprisePusher测试类"""

    def test_init(self):
        """测试初始化"""
        pusher = ApprisePusher()
        assert pusher.apprise_instance is None

    def test_init_apprise_success(self):
        """测试初始化Apprise实例成功"""
        pusher = ApprisePusher()
        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            mock_instance = Mock()
            mock_apprise.Apprise.return_value = mock_instance

            result = pusher._init_apprise()

            assert result is True
            assert pusher.apprise_instance == mock_instance

    def test_init_apprise_failure(self):
        """测试初始化Apprise实例失败"""
        pusher = ApprisePusher()
        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            mock_apprise.Apprise.side_effect = Exception("初始化失败")

            result = pusher._init_apprise()

            assert result is False
            assert pusher.apprise_instance is None

    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """测试发送通知成功（全部成功）"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            # 验证实例和单独发送实例
            validation_instance = Mock()
            validation_instance.add.return_value = True
            single_instance = Mock()
            single_instance.add.return_value = True

            mock_apprise.Apprise.side_effect = [validation_instance, single_instance]

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop_instance = Mock()
                mock_loop_instance.run_in_executor = AsyncMock(return_value=True)
                mock_loop.return_value = mock_loop_instance

                result = await pusher.send_notification(urls, title, body)

                assert result["success"] is True
                assert result["partial_success"] is False  # 全部成功，不是部分成功
                assert result["title"] == title
                assert result["body"] == body
                assert result["valid_urls"] == 1
                assert result["invalid_urls"] == 0

    @pytest.mark.asyncio
    async def test_send_notification_invalid_urls(self):
        """测试发送通知 - 无效URL"""
        pusher = ApprisePusher()
        urls = ["invalid_url"]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            mock_instance = Mock()
            mock_instance.add.return_value = False
            mock_apprise.Apprise.return_value = mock_instance

            result = await pusher.send_notification(urls, title, body)

            assert result["success"] is False
            assert result["valid_urls"] == 0
            assert result["invalid_urls"] == 1
            assert "没有有效的推送URL" in result["error"]

    @pytest.mark.asyncio
    async def test_send_notification_mixed_urls(self):
        """测试发送通知 - 混合有效和无效URL"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app", "invalid_url"]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            # 验证实例
            validation_instance = Mock()
            validation_instance.add.side_effect = [True, False]  # 第1个有效，第2个无效
            # 只有1个有效URL，所以只需要1个单独发送实例
            single_instance = Mock()
            single_instance.add.return_value = True

            mock_apprise.Apprise.side_effect = [validation_instance, single_instance]

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop_instance = Mock()
                mock_loop_instance.run_in_executor = AsyncMock(return_value=True)
                mock_loop.return_value = mock_loop_instance

                result = await pusher.send_notification(urls, title, body)

                assert result["success"] is True
                assert result["valid_urls"] == 1
                assert result["invalid_urls"] == 1

    @pytest.mark.asyncio
    async def test_send_notification_partial_success(self):
        """测试发送通知部分成功（2/3成功）"""
        pusher = ApprisePusher()
        urls = [
            "bark://test_key1@api.day.app",
            "bark://test_key2@api.day.app",
            "dotpush://test_key3",
        ]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            # 第一个实例用于验证URLs
            validation_instance = Mock()
            validation_instance.add.return_value = True

            # 为每个URL创建单独的实例
            single_instances = [Mock(), Mock(), Mock()]
            single_instances[0].add.return_value = True
            single_instances[1].add.return_value = True
            single_instances[2].add.return_value = True

            # 模拟Apprise()被调用4次（1次验证 + 3次单独发送）
            mock_apprise.Apprise.side_effect = [
                validation_instance,
                single_instances[0],
                single_instances[1],
                single_instances[2],
            ]

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop_instance = Mock()
                # 模拟3次run_in_executor调用，返回True, True, False
                mock_loop_instance.run_in_executor = AsyncMock(
                    side_effect=[True, True, False]
                )
                mock_loop.return_value = mock_loop_instance

                result = await pusher.send_notification(urls, title, body)

                # 应该成功，因为至少有一个成功
                assert result["success"] is True
                # 应该标记为部分成功（不是全部成功）
                assert result["partial_success"] is True
                assert result["valid_urls"] == 3
                assert result["invalid_urls"] == 0
                # 检查URL结果
                assert len(result["url_results"]) == 3
                assert result["url_results"][0]["success"] is True
                assert result["url_results"][1]["success"] is True
                assert result["url_results"][2]["success"] is False

    @pytest.mark.asyncio
    async def test_send_notification_failure(self):
        """测试发送通知失败"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            # 验证实例和单独发送实例
            validation_instance = Mock()
            validation_instance.add.return_value = True
            single_instance = Mock()
            single_instance.add.return_value = True

            mock_apprise.Apprise.side_effect = [validation_instance, single_instance]

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop_instance = Mock()
                mock_loop_instance.run_in_executor = AsyncMock(
                    return_value=False
                )  # 推送失败
                mock_loop.return_value = mock_loop_instance

                result = await pusher.send_notification(urls, title, body)

                assert result["success"] is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_send_notification_exception(self):
        """测试发送通知异常"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]
        title = "测试标题"
        body = "测试内容"

        with patch(
            "jjz_alert.service.notification.apprise_pusher.apprise"
        ) as mock_apprise:
            mock_apprise.Apprise.side_effect = Exception("网络错误")

            result = await pusher.send_notification(urls, title, body)

            assert result["success"] is False
            assert "error" in result
            assert result["valid_urls"] == 0

    def test_mask_url_normal(self):
        """测试URL遮蔽 - 正常URL"""
        pusher = ApprisePusher()
        url = "bark://test_key@api.day.app/test_path"
        masked = pusher._mask_url(url)

        # 验证 scheme 保留
        assert "bark://" in masked
        # 验证所有部分被遮蔽（显示前3字符 + ****）
        assert "tes****" in masked  # test_key -> tes****
        assert "api****" in masked  # api.day.app -> api****
        # 验证分隔符保留
        assert "@" in masked
        assert "/" in masked
        # 验证敏感信息被遮蔽
        assert "test_key" not in masked
        assert "test_path" not in masked

    def test_mask_url_short_path(self):
        """测试URL遮蔽 - 短路径"""
        pusher = ApprisePusher()
        url = "bark://test_key@api.day.app/short"
        masked = pusher._mask_url(url)

        assert "bark://" in masked
        assert "****" in masked

    def test_mask_url_no_path(self):
        """测试URL遮蔽 - 无路径"""
        pusher = ApprisePusher()
        url = "bark://test_key@api.day.app"
        masked = pusher._mask_url(url)

        assert "bark://" in masked
        assert "****" in masked

    def test_mask_url_invalid(self):
        """测试URL遮蔽 - 无效URL"""
        pusher = ApprisePusher()
        url = "invalid_url"
        masked = pusher._mask_url(url)

        # 无 scheme 的 URL，整个作为一个部分遮蔽
        # "invalid_url" 长度 >= 3，显示前3字符 + ****
        assert masked == "inv****"

    def test_mask_url_exception(self):
        """测试URL遮蔽 - 异常情况"""
        pusher = ApprisePusher()
        url = None
        masked = pusher._mask_url(url)

        assert masked == "****"

    def test_mask_url_with_at_in_password(self):
        """测试URL遮蔽 - 密码包含@符号"""
        pusher = ApprisePusher()
        # 模拟 SMTP URL，密码中包含 @ 符号
        # 格式: smtp://username:p@ssword@smtp.example.com/
        url = "smtp://user:p@ssw0rd@smtp.example.com/path"
        masked = pusher._mask_url(url)

        # 验证 scheme 保留
        assert "smtp://" in masked
        # 验证所有部分被遮蔽（新的简化逻辑按 @ 和 / 分隔，每部分都遮蔽）
        assert "****" in masked
        # 验证 @ 分隔符保留
        assert masked.count("@") == 2  # 保留2个@符号
        # 验证密码不泄露
        assert "p@ssw0rd" not in masked
        assert "ssw0rd" not in masked
        # 预期结果类似: smtp://use****@ssw****@smt****/pat****
        assert "use****" in masked  # user:p -> use****（前3字符+****）
        assert "ssw****" in masked  # ssw0rd -> ssw****

    def test_mask_url_with_at_in_password_no_path(self):
        """测试URL遮蔽 - 密码包含@符号且无路径"""
        pusher = ApprisePusher()
        url = "smtp://user:p@ssw0rd@smtp.example.com"
        masked = pusher._mask_url(url)

        # 验证 scheme 保留
        assert "smtp://" in masked
        # 验证所有部分被遮蔽
        assert "****" in masked
        # 验证 @ 分隔符保留
        assert masked.count("@") == 2
        # 验证密码不泄露
        assert "p@ssw0rd" not in masked
        assert "ssw0rd" not in masked

    def test_sanitize_error_message_with_url(self):
        """测试错误消息清理 - 包含URL"""
        pusher = ApprisePusher()
        url = "bark://secret_token_12345@api.day.app/path"
        error_msg = f"Failed to send to {url}"
        sanitized = pusher._sanitize_error_message(error_msg, url)

        # URL应该被遮蔽
        assert "secret_token_12345" not in sanitized
        assert "****" in sanitized
        assert "Failed to send" in sanitized

    def test_sanitize_error_message_with_long_token(self):
        """测试错误消息清理 - 包含长token"""
        pusher = ApprisePusher()
        # 创建一个包含长token的错误消息（20+字符）
        error_msg = "Auth failed: token_abcdefghijklmnopqrstuvwxyz123456"
        sanitized = pusher._sanitize_error_message(error_msg, "bark://test")

        # 长字符串应该被遮蔽
        assert "abcdefghijklmnopqrstuvwxyz123456" not in sanitized
        assert "toke****" in sanitized
        assert "Auth failed" in sanitized

    def test_sanitize_error_message_exception_handling(self):
        """测试错误消息清理 - 异常处理"""
        pusher = ApprisePusher()
        # 测试None输入
        result = pusher._sanitize_error_message(None, "test")
        assert "错误详情已隐藏" in result

    def test_sanitize_error_message_empty_string(self):
        """测试错误消息清理 - 空字符串"""
        pusher = ApprisePusher()
        result = pusher._sanitize_error_message("", "bark://test")
        # 空字符串应该正常返回
        assert result == ""

    def test_validate_urls_success(self):
        """测试URL验证成功"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app", "tgram://bot_token/chat_id"]

        mock_instance = Mock()
        mock_instance.add.side_effect = [True, True]

        with patch.object(pusher, "_init_apprise", return_value=True):
            pusher.apprise_instance = mock_instance
            result = pusher.validate_urls(urls)

            assert len(result["valid"]) == 2
            assert len(result["invalid"]) == 0
            assert result["valid_count"] == 2

    def test_validate_urls_partial_invalid(self):
        """测试URL验证 - 部分无效"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app", "invalid_url"]

        mock_instance = Mock()
        mock_instance.add.side_effect = [True, False]

        with patch.object(pusher, "_init_apprise", return_value=True):
            pusher.apprise_instance = mock_instance
            result = pusher.validate_urls(urls)

            assert len(result["valid"]) == 1
            assert len(result["invalid"]) == 1
            assert result["valid_count"] == 1
            assert result["invalid_count"] == 1

    def test_validate_urls_init_failed(self):
        """测试URL验证 - 初始化失败"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]

        with patch.object(pusher, "_init_apprise", return_value=False):
            result = pusher.validate_urls(urls)

            assert len(result["valid"]) == 0
            assert len(result["invalid"]) == 1
            assert "error" in result

    def test_validate_urls_exception(self):
        """测试URL验证异常"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]

        with patch.object(pusher, "_init_apprise", side_effect=Exception("初始化失败")):
            result = pusher.validate_urls(urls)

            assert len(result["valid"]) == 0
            assert len(result["invalid"]) == 1
            assert "error" in result

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """测试连接测试成功"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]

        with patch.object(pusher, "send_notification") as mock_send:
            mock_send.return_value = {"success": True, "valid_urls": 1}

            result = await pusher.test_connection(urls)

            assert result["success"] is True
            assert result["test"] is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """测试连接测试失败"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]

        with patch.object(pusher, "send_notification") as mock_send:
            mock_send.return_value = {"success": False, "error": "连接失败"}

            result = await pusher.test_connection(urls)

            assert result["success"] is False
            assert result["test"] is True

    @pytest.mark.asyncio
    async def test_test_connection_exception(self):
        """测试连接测试异常"""
        pusher = ApprisePusher()
        urls = ["bark://test_key@api.day.app"]

        with patch.object(
            pusher, "send_notification", side_effect=Exception("测试异常")
        ):
            result = await pusher.test_connection(urls)

            assert result["success"] is False
            assert result["test"] is True
            assert "error" in result


@pytest.mark.unit
class TestAppriseConfig:
    """AppriseConfig测试类"""

    def test_bark_url_basic(self):
        """测试生成Bark URL - 基础"""
        url = AppriseConfig.bark_url("test_key")
        assert url == "bark://test_key@api.day.app"

    def test_bark_url_custom_server(self):
        """测试生成Bark URL - 自定义服务器"""
        url = AppriseConfig.bark_url("test_key", server="custom.server.com")
        assert url == "bark://test_key@custom.server.com"

    def test_bark_url_with_params(self):
        """测试生成Bark URL - 带参数"""
        url = AppriseConfig.bark_url("test_key", sound="alarm", level="critical")
        assert "sound=alarm" in url
        assert "level=critical" in url

    def test_telegram_url_basic(self):
        """测试生成Telegram URL - 基础"""
        url = AppriseConfig.telegram_url("bot_token", "chat_id")
        assert url == "tgram://bot_token/chat_id"

    def test_telegram_url_with_params(self):
        """测试生成Telegram URL - 带参数"""
        url = AppriseConfig.telegram_url("bot_token", "chat_id", format="html")
        assert "format=html" in url

    def test_email_url_basic(self):
        """测试生成Email URL - 基础"""
        url = AppriseConfig.email_url("user", "password")
        assert "mailto://" in url
        assert "user" in url
        assert "smtp.gmail.com" in url

    def test_email_url_with_to_email(self):
        """测试生成Email URL - 带收件人"""
        url = AppriseConfig.email_url("user", "password", to_email="test@example.com")
        assert "test@example.com" in url

    def test_email_url_custom_smtp(self):
        """测试生成Email URL - 自定义SMTP"""
        url = AppriseConfig.email_url(
            "user", "password", smtp_server="smtp.example.com", port=465
        )
        assert "smtp.example.com" in url
        assert "465" in url

    def test_email_url_with_params(self):
        """测试生成Email URL - 带参数"""
        url = AppriseConfig.email_url("user", "password", subject="Test")
        assert "subject=Test" in url

    def test_wxwork_url_basic(self):
        """测试生成企业微信URL - 基础"""
        url = AppriseConfig.wxwork_url("test_key")
        assert url == "wxwork://test_key"

    def test_wxwork_url_with_params(self):
        """测试生成企业微信URL - 带参数"""
        url = AppriseConfig.wxwork_url("test_key", format="markdown")
        assert "format=markdown" in url

    def test_dingding_url_basic(self):
        """测试生成钉钉URL - 基础"""
        url = AppriseConfig.dingding_url("test_token")
        assert url == "dingding://test_token"

    def test_dingding_url_with_secret(self):
        """测试生成钉钉URL - 带密钥"""
        url = AppriseConfig.dingding_url("test_token", secret="test_secret")
        assert url == "dingding://test_token/test_secret"

    def test_dingding_url_with_params(self):
        """测试生成钉钉URL - 带参数"""
        url = AppriseConfig.dingding_url("test_token", title="Test")
        assert "title=Test" in url

    def test_webhook_url_basic(self):
        """测试生成Webhook URL - 基础"""
        url = AppriseConfig.webhook_url("https://example.com/webhook")
        assert "json://https://example.com/webhook" in url

    def test_webhook_url_custom_method(self):
        """测试生成Webhook URL - 自定义方法"""
        url = AppriseConfig.webhook_url("https://example.com/webhook", method="GET")
        assert "method=GET" in url

    def test_webhook_url_with_params(self):
        """测试生成Webhook URL - 带参数"""
        url = AppriseConfig.webhook_url(
            "https://example.com/webhook", method="POST", timeout=30
        )
        assert "timeout=30" in url
