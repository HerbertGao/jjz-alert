from types import SimpleNamespace
from unittest.mock import patch, Mock

import pytest

from jjz_alert.base import message_templates as mt


class TestMessageTemplateManager:
    """测试消息模板管理器"""

    def test_init_with_default_templates(self):
        """测试使用默认模板初始化"""
        manager = mt.MessageTemplateManager()
        assert "valid_status" in manager.templates
        assert "expired_status" in manager.templates
        assert "pending_status" in manager.templates
        assert "error_status" in manager.templates

    def test_init_with_custom_templates(self):
        """测试使用自定义模板初始化"""
        custom_templates = {"valid_status": "自定义模板 ${display_name}"}
        manager = mt.MessageTemplateManager(template_config=custom_templates)
        assert manager.templates["valid_status"] == "自定义模板 ${display_name}"

    def test_format_valid_status_with_sycs(self):
        """测试格式化有效状态（带剩余次数）"""
        manager = mt.MessageTemplateManager()

        result = manager.format_valid_status(
            display_name="京A12345",
            jjz_type="六环内",
            status_text="有效",
            valid_start="2025-01-01",
            valid_end="2025-01-05",
            days_remaining=4,
            sycs="2",
        )

        assert "剩余 2 次" in result
        assert "剩余 4 天" in result
        assert "京A12345" in result
        assert "六环内" in result

    def test_format_valid_status_without_sycs(self):
        """测试格式化有效状态（无剩余次数）"""
        manager = mt.MessageTemplateManager()

        result = manager.format_valid_status(
            display_name="京B67890",
            jjz_type="六环外",
            status_text="有效",
            valid_start="2025-02-01",
            valid_end="2025-02-05",
            days_remaining=None,
            sycs="",
        )

        assert "六环内进京证剩余" not in result
        assert "京B67890" in result

    def test_format_valid_status_with_none_days_remaining(self):
        """测试格式化有效状态（剩余天数为None）"""
        manager = mt.MessageTemplateManager()

        result = manager.format_valid_status(
            display_name="京C11111",
            jjz_type="六环内",
            status_text="有效",
            valid_start="2025-01-01",
            valid_end="2025-01-05",
            days_remaining=None,
            sycs="3",
        )

        assert "剩余 0 天" in result or "0 天" in result

    def test_format_valid_status_exception_handling(self):
        """测试格式化有效状态时的异常处理"""
        manager = mt.MessageTemplateManager()
        # 通过mock Template来触发异常
        with patch("jjz_alert.base.message_templates.Template") as mock_template:
            mock_template.side_effect = Exception("模板错误")

            result = manager.format_valid_status(
                display_name="京D22222",
                jjz_type="六环内",
                status_text="有效",
                valid_start="2025-01-01",
                valid_end="2025-01-05",
                days_remaining=4,
                sycs="2",
            )

            # 应该返回备用格式
            assert "京D22222" in result
            assert "有效" in result

    def test_format_expired_status_with_sycs(self):
        """测试格式化过期状态（带剩余次数）"""
        manager = mt.MessageTemplateManager()

        result = manager.format_expired_status(
            display_name="京E33333",
            sycs="1",
        )

        assert "京E33333" in result
        assert "已过期" in result
        assert "剩余 1 次" in result

    def test_format_expired_status_without_sycs(self):
        """测试格式化过期状态（无剩余次数）"""
        manager = mt.MessageTemplateManager()

        result = manager.format_expired_status(
            display_name="京F44444",
            sycs="",
        )

        assert "京F44444" in result
        assert "已过期" in result
        assert "六环内进京证剩余" not in result

    def test_format_expired_status_exception_handling(self):
        """测试格式化过期状态时的异常处理"""
        manager = mt.MessageTemplateManager()
        # 通过mock Template来触发异常
        with patch("jjz_alert.base.message_templates.Template") as mock_template:
            mock_template.side_effect = Exception("模板错误")

            result = manager.format_expired_status(
                display_name="京G55555",
                sycs="2",
            )

            # 应该返回备用格式
            assert "京G55555" in result
            assert "已过期" in result

    def test_format_pending_status(self):
        """测试格式化审核中状态"""
        manager = mt.MessageTemplateManager()

        result = manager.format_pending_status(
            display_name="京H66666",
            jjz_type="六环内",
            apply_time="2025-01-01 10:00:00",
        )

        assert "京H66666" in result
        assert "审核中" in result
        assert "2025-01-01 10:00:00" in result

    def test_format_pending_status_exception_handling(self):
        """测试格式化审核中状态时的异常处理"""
        manager = mt.MessageTemplateManager()
        # 通过mock Template来触发异常
        with patch("jjz_alert.base.message_templates.Template") as mock_template:
            mock_template.side_effect = Exception("模板错误")

            result = manager.format_pending_status(
                display_name="京I77777",
                jjz_type="六环外",
                apply_time="2025-01-01 10:00:00",
            )

            # 应该返回备用格式
            assert "京I77777" in result
            assert "审核中" in result

    def test_format_error_status(self):
        """测试格式化错误状态"""
        manager = mt.MessageTemplateManager()

        result = manager.format_error_status(
            display_name="京J88888",
            jjz_type="六环内",
            status="error",
            error_msg="查询失败",
        )

        assert "京J88888" in result
        assert "error" in result
        assert "查询失败" in result

    def test_format_error_status_exception_handling(self):
        """测试格式化错误状态时的异常处理"""
        manager = mt.MessageTemplateManager()
        # 通过mock Template来触发异常
        with patch("jjz_alert.base.message_templates.Template") as mock_template:
            mock_template.side_effect = Exception("模板错误")

            result = manager.format_error_status(
                display_name="京K99999",
                jjz_type="六环外",
                status="error",
                error_msg="网络错误",
            )

            # 应该返回备用格式
            assert "京K99999" in result
            assert "error" in result
            assert "网络错误" in result

    def test_format_traffic_reminder(self):
        """测试格式化限行提醒"""
        manager = mt.MessageTemplateManager()

        result = manager.format_traffic_reminder("今日限行")

        assert "今日限行" in result
        assert "⚠️" in result or "【" in result

    def test_format_traffic_reminder_exception_handling(self):
        """测试格式化限行提醒时的异常处理"""
        manager = mt.MessageTemplateManager()
        # 通过mock Template来触发异常
        with patch("jjz_alert.base.message_templates.Template") as mock_template:
            mock_template.side_effect = Exception("模板错误")

            result = manager.format_traffic_reminder("明日限行")

            # 应该返回备用格式
            assert "明日限行" in result

    def test_update_templates(self):
        """测试更新模板"""
        manager = mt.MessageTemplateManager()
        new_templates = {"pending_status": "待审核 ${display_name}"}

        manager.update_templates(new_templates)

        assert manager.get_template("pending_status") == "待审核 ${display_name}"

    def test_get_template_existing(self):
        """测试获取存在的模板"""
        manager = mt.MessageTemplateManager()
        template = manager.get_template("valid_status")
        assert template is not None
        assert "${display_name}" in template

    def test_get_template_nonexistent(self):
        """测试获取不存在的模板"""
        manager = mt.MessageTemplateManager()
        template = manager.get_template("nonexistent_template")
        assert template is None

    def test_list_templates(self):
        """测试列出所有模板"""
        manager = mt.MessageTemplateManager()
        templates = manager.list_templates()

        assert isinstance(templates, dict)
        assert "valid_status" in templates
        assert "expired_status" in templates
        # 确保返回的是副本，不是原始字典
        templates["test"] = "test"
        assert "test" not in manager.templates


class TestInitializeTemplatesFromConfig:
    """测试从配置初始化模板"""

    def test_initialize_with_custom_templates(self, monkeypatch):
        """测试使用自定义模板初始化"""
        custom_manager = mt.MessageTemplateManager()
        monkeypatch.setattr(mt, "template_manager", custom_manager)

        class DummyTemplate(SimpleNamespace):
            valid_status = "CUSTOM ${display_name}"
            expired_status = "CUSTOM EXPIRED ${display_name}"
            pending_status = None
            error_status = None
            traffic_reminder_prefix = None
            sycs_part = None

        dummy_config = SimpleNamespace(
            global_config=SimpleNamespace(message_templates=DummyTemplate())
        )

        class DummyConfigManager:
            def load_config(self):
                return dummy_config

        mt.initialize_templates_from_config(DummyConfigManager())

        assert custom_manager.get_template("valid_status") == "CUSTOM ${display_name}"
        assert (
            custom_manager.get_template("expired_status")
            == "CUSTOM EXPIRED ${display_name}"
        )

    def test_initialize_with_none_config_manager(self, monkeypatch):
        """测试使用None配置管理器（自动创建）"""
        custom_manager = mt.MessageTemplateManager()
        monkeypatch.setattr(mt, "template_manager", custom_manager)

        with patch("jjz_alert.config.config.config_manager") as mock_cm:

            class DummyTemplate(SimpleNamespace):
                valid_status = "AUTO ${display_name}"
                expired_status = None
                pending_status = None
                error_status = None
                traffic_reminder_prefix = None
                sycs_part = None

            dummy_config = SimpleNamespace(
                global_config=SimpleNamespace(message_templates=DummyTemplate())
            )
            mock_cm.load_config.return_value = dummy_config

            mt.initialize_templates_from_config(None)

            assert custom_manager.get_template("valid_status") == "AUTO ${display_name}"

    def test_initialize_with_no_custom_templates(self, monkeypatch):
        """测试没有自定义模板时使用默认模板"""
        custom_manager = mt.MessageTemplateManager()
        original_templates = custom_manager.templates.copy()
        monkeypatch.setattr(mt, "template_manager", custom_manager)

        class DummyTemplate(SimpleNamespace):
            valid_status = None
            expired_status = None
            pending_status = None
            error_status = None
            traffic_reminder_prefix = None
            sycs_part = None

        dummy_config = SimpleNamespace(
            global_config=SimpleNamespace(message_templates=DummyTemplate())
        )

        class DummyConfigManager:
            def load_config(self):
                return dummy_config

        mt.initialize_templates_from_config(DummyConfigManager())

        # 模板应该保持不变（使用默认）
        assert (
            custom_manager.get_template("valid_status")
            == original_templates["valid_status"]
        )

    def test_initialize_with_exception(self, monkeypatch):
        """测试初始化时发生异常"""
        custom_manager = mt.MessageTemplateManager()
        original_templates = custom_manager.templates.copy()
        monkeypatch.setattr(mt, "template_manager", custom_manager)

        class DummyConfigManager:
            def load_config(self):
                raise Exception("配置加载失败")

        mt.initialize_templates_from_config(DummyConfigManager())

        # 异常时应该保持默认模板
        assert (
            custom_manager.get_template("valid_status")
            == original_templates["valid_status"]
        )
