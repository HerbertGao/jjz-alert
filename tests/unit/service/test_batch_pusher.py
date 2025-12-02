"""
BatchPusher 单元测试
"""

from unittest.mock import AsyncMock, patch

import pytest

from jjz_alert.config.config import PlateConfig, NotificationConfig
from jjz_alert.config.config_models import AppriseUrlConfig
from jjz_alert.service.notification.batch_pusher import (
    BatchPusher,
    BatchPushItem,
    BatchGroup,
    batch_pusher,
)
from jjz_alert.service.notification.push_priority import PushPriority
from jjz_alert.service.notification.url_utils import (
    parse_apprise_url_item,
    process_url_placeholders,
)


@pytest.mark.unit
class TestBatchPushItem:
    """BatchPushItem 数据类测试"""

    def test_create_basic(self):
        """测试创建基本推送项"""
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="测试标题",
            body="测试内容",
            priority=PushPriority.NORMAL,
        )
        assert item.plate_config.plate == "京A12345"
        assert item.title == "测试标题"
        assert item.body == "测试内容"
        assert item.priority == PushPriority.NORMAL
        assert item.jjz_data == {}
        assert item.traffic_reminder is None

    def test_create_with_all_fields(self):
        """测试创建包含所有字段的推送项"""
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="测试标题",
            body="测试内容",
            priority=PushPriority.HIGH,
            jjz_data={"key": "value"},
            traffic_reminder="限行提醒",
        )
        assert item.priority == PushPriority.HIGH
        assert item.jjz_data == {"key": "value"}
        assert item.traffic_reminder == "限行提醒"


@pytest.mark.unit
class TestBatchGroup:
    """BatchGroup 数据类测试"""

    def test_create_basic(self):
        """测试创建基本分组"""
        group = BatchGroup(batch_key="test_key", url="https://example.com")
        assert group.batch_key == "test_key"
        assert group.url == "https://example.com"
        assert group.items == []

    def test_create_with_items(self):
        """测试创建包含推送项的分组"""
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="测试",
            body="内容",
            priority=PushPriority.NORMAL,
        )
        group = BatchGroup(
            batch_key="test_key", url="https://example.com", items=[item]
        )
        assert len(group.items) == 1


@pytest.mark.unit
class TestBatchPusher:
    """BatchPusher 测试类"""

    def test_init(self):
        """测试初始化"""
        pusher = BatchPusher()
        assert pusher._batch_groups == {}

    def test_global_instance(self):
        """测试全局实例"""
        assert batch_pusher is not None
        assert isinstance(batch_pusher, BatchPusher)


@pytest.mark.unit
class TestParseAppriseUrlItem:
    """parse_apprise_url_item 函数测试"""

    def test_parse_string_url(self):
        """测试解析字符串 URL"""
        url, batch_key = parse_apprise_url_item("https://example.com")
        assert url == "https://example.com"
        assert batch_key is None

    def test_parse_apprise_url_config_without_batch_key(self):
        """测试解析 AppriseUrlConfig（无 batch_key）"""
        config = AppriseUrlConfig(url="https://example.com")
        url, batch_key = parse_apprise_url_item(config)
        assert url == "https://example.com"
        assert batch_key is None

    def test_parse_apprise_url_config_with_batch_key(self):
        """测试解析 AppriseUrlConfig（有 batch_key）"""
        config = AppriseUrlConfig(url="https://example.com", batch_key="group1")
        url, batch_key = parse_apprise_url_item(config)
        assert url == "https://example.com"
        assert batch_key == "group1"

    def test_parse_dict_url(self):
        """测试解析字典格式 URL"""
        url, batch_key = parse_apprise_url_item(
            {"url": "https://example.com", "batch_key": "group1"}
        )
        assert url == "https://example.com"
        assert batch_key == "group1"

    def test_parse_invalid_type(self):
        """测试解析无效类型"""
        url, batch_key = parse_apprise_url_item(12345)
        assert url == ""
        assert batch_key is None


@pytest.mark.unit
class TestCollectBatchUrls:
    """collect_batch_urls 方法测试"""

    def test_collect_empty_configs(self):
        """测试空配置列表"""
        pusher = BatchPusher()
        result = pusher.collect_batch_urls([])
        assert result == {}

    def test_collect_no_batch_urls(self):
        """测试没有批量推送 URL 的配置"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(type="apprise", urls=["https://normal.com"])
            ],
        )
        result = pusher.collect_batch_urls([plate_config])
        assert result == {}

    def test_collect_with_batch_urls(self):
        """测试包含批量推送 URL 的配置"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch.com", batch_key="group1"),
                        "https://normal.com",
                    ],
                )
            ],
        )
        result = pusher.collect_batch_urls([plate_config])
        assert "group1" in result
        assert len(result["group1"]) == 1
        assert result["group1"][0][0].plate == "京A12345"
        assert result["group1"][0][1] == "https://batch.com"

    def test_collect_multiple_plates_same_batch_key(self):
        """测试多个车牌使用相同 batch_key"""
        pusher = BatchPusher()
        plate1 = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch1.com", batch_key="shared")
                    ],
                )
            ],
        )
        plate2 = PlateConfig(
            plate="京B67890",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch2.com", batch_key="shared")
                    ],
                )
            ],
        )
        result = pusher.collect_batch_urls([plate1, plate2])
        assert "shared" in result
        assert len(result["shared"]) == 2

    def test_collect_skip_non_apprise(self):
        """测试跳过非 apprise 类型"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="other",
                    urls=[
                        AppriseUrlConfig(url="https://batch.com", batch_key="group1")
                    ],
                )
            ],
        )
        result = pusher.collect_batch_urls([plate_config])
        assert result == {}


@pytest.mark.unit
class TestGetBatchUrlsForPlate:
    """get_batch_urls_for_plate 方法测试"""

    def test_no_batch_urls(self):
        """测试没有批量 URL"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(type="apprise", urls=["https://normal.com"])
            ],
        )
        result = pusher.get_batch_urls_for_plate(plate_config)
        assert result == set()

    def test_with_batch_urls(self):
        """测试包含批量 URL"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch1.com", batch_key="g1"),
                        AppriseUrlConfig(url="https://batch2.com", batch_key="g2"),
                        "https://normal.com",
                    ],
                )
            ],
        )
        result = pusher.get_batch_urls_for_plate(plate_config)
        assert "https://batch1.com" in result
        assert "https://batch2.com" in result
        assert "https://normal.com" not in result

    def test_skip_non_apprise(self):
        """测试跳过非 apprise 类型"""
        pusher = BatchPusher()
        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="other",
                    urls=[AppriseUrlConfig(url="https://batch.com", batch_key="g1")],
                )
            ],
        )
        result = pusher.get_batch_urls_for_plate(plate_config)
        assert result == set()


@pytest.mark.unit
class TestGroupPushItems:
    """group_push_items 方法测试"""

    def test_group_empty_items(self):
        """测试空推送项列表"""
        pusher = BatchPusher()
        result = pusher.group_push_items([], [])
        assert result == {}

    def test_group_items_by_batch_key(self):
        """测试按 batch_key 分组"""
        pusher = BatchPusher()

        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch.com", batch_key="group1")
                    ],
                )
            ],
        )

        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )

        result = pusher.group_push_items([item], [plate_config])
        assert "group1" in result
        assert len(result["group1"].items) == 1
        assert result["group1"].url == "https://batch.com"

    def test_group_multiple_items_same_batch_key(self):
        """测试多个推送项分配到同一 batch_key"""
        pusher = BatchPusher()

        plate1 = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch.com", batch_key="shared")
                    ],
                )
            ],
        )
        plate2 = PlateConfig(
            plate="京B67890",
            notifications=[
                NotificationConfig(
                    type="apprise",
                    urls=[
                        AppriseUrlConfig(url="https://batch.com", batch_key="shared")
                    ],
                )
            ],
        )

        item1 = BatchPushItem(
            plate_config=plate1,
            title="标题1",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="标题2",
            body="内容2",
            priority=PushPriority.HIGH,
        )

        result = pusher.group_push_items([item1, item2], [plate1, plate2])
        assert "shared" in result
        assert len(result["shared"].items) == 2

    def test_group_items_no_matching_config(self):
        """测试推送项没有匹配的配置"""
        pusher = BatchPusher()

        plate_config = PlateConfig(
            plate="京A12345",
            notifications=[
                NotificationConfig(type="apprise", urls=["https://normal.com"])
            ],
        )

        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )

        result = pusher.group_push_items([item], [plate_config])
        assert result == {}


@pytest.mark.unit
class TestMergeMessages:
    """merge_messages 方法测试"""

    def test_merge_empty_items(self):
        """测试合并空列表"""
        pusher = BatchPusher()
        title, body, priority = pusher.merge_messages([])
        assert title == ""
        assert body == ""
        assert priority == PushPriority.NORMAL

    def test_merge_single_item(self):
        """测试合并单个项目（不合并）"""
        pusher = BatchPusher()
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="原始标题",
            body="原始内容",
            priority=PushPriority.HIGH,
        )
        title, body, priority = pusher.merge_messages([item])
        assert title == "原始标题"
        assert body == "原始内容"
        assert priority == PushPriority.HIGH

    def test_merge_multiple_items(self):
        """测试合并多个项目"""
        pusher = BatchPusher()
        plate1 = PlateConfig(plate="京A12345", notifications=[])
        plate2 = PlateConfig(plate="京B67890", notifications=[])

        item1 = BatchPushItem(
            plate_config=plate1,
            title="标题1",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="标题2",
            body="内容2",
            priority=PushPriority.NORMAL,
        )

        title, body, priority = pusher.merge_messages([item1, item2])
        assert title == "进京证状态提醒"
        assert "内容1" in body
        assert "内容2" in body
        assert "\n" in body
        assert priority == PushPriority.NORMAL

    def test_merge_with_high_priority(self):
        """测试合并时取最高优先级"""
        pusher = BatchPusher()
        plate1 = PlateConfig(plate="京A12345", notifications=[])
        plate2 = PlateConfig(plate="京B67890", notifications=[])

        item1 = BatchPushItem(
            plate_config=plate1,
            title="标题1",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="标题2",
            body="内容2",
            priority=PushPriority.HIGH,
        )

        title, body, priority = pusher.merge_messages([item1, item2])
        assert priority == PushPriority.HIGH


@pytest.mark.unit
class TestGetMaxPriority:
    """_get_max_priority 方法测试"""

    def test_empty_items(self):
        """测试空列表"""
        pusher = BatchPusher()
        result = pusher._get_max_priority([])
        assert result == PushPriority.NORMAL

    def test_all_normal(self):
        """测试全部是 NORMAL 优先级"""
        pusher = BatchPusher()
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        items = [
            BatchPushItem(
                plate_config=plate_config,
                title="",
                body="",
                priority=PushPriority.NORMAL,
            ),
            BatchPushItem(
                plate_config=plate_config,
                title="",
                body="",
                priority=PushPriority.NORMAL,
            ),
        ]
        result = pusher._get_max_priority(items)
        assert result == PushPriority.NORMAL

    def test_contains_high(self):
        """测试包含 HIGH 优先级"""
        pusher = BatchPusher()
        plate_config = PlateConfig(plate="京A12345", notifications=[])
        items = [
            BatchPushItem(
                plate_config=plate_config,
                title="",
                body="",
                priority=PushPriority.NORMAL,
            ),
            BatchPushItem(
                plate_config=plate_config,
                title="",
                body="",
                priority=PushPriority.HIGH,
            ),
        ]
        result = pusher._get_max_priority(items)
        assert result == PushPriority.HIGH


@pytest.mark.unit
class TestProcessUrlPlaceholders:
    """process_url_placeholders 函数测试"""

    def test_basic_placeholders(self):
        """测试基本占位符替换"""
        url = "https://api.example.com/?plate={plate}&name={display_name}"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
        )
        assert "京A12345" in result
        assert "测试车辆" in result
        assert "{plate}" not in result
        assert "{display_name}" not in result

    def test_with_icon(self):
        """测试带图标的占位符"""
        url = "https://api.example.com/?icon={icon}"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
            icon="https://example.com/icon.png",
        )
        assert "https://example.com/icon.png" in result
        assert "{icon}" not in result

    def test_without_icon_ampersand(self):
        """测试无图标时移除 &icon={icon}"""
        url = "https://api.example.com/?param=1&icon={icon}"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
        )
        assert "icon=" not in result
        assert "{icon}" not in result

    def test_without_icon_question_ampersand(self):
        """测试无图标时移除 ?icon={icon}&"""
        url = "https://api.example.com/?icon={icon}&param=1"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
        )
        assert "icon=" not in result
        assert "param=1" in result

    def test_without_icon_question_only(self):
        """测试无图标时移除 ?icon={icon}"""
        url = "https://api.example.com/?icon={icon}"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
        )
        assert "icon=" not in result
        assert "{icon}" not in result

    def test_priority_placeholders(self):
        """测试优先级占位符"""
        url = "https://api.example.com/?level={level}&priority={priority}"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.HIGH,
        )
        assert "{level}" not in result
        assert "{priority}" not in result
        assert "critical" in result  # HIGH 对应 Bark 的 critical

    def test_normal_url_processing(self):
        """测试正常 URL 处理（不含占位符）"""
        url = "https://api.example.com/"
        result = process_url_placeholders(
            url=url,
            plate="京A12345",
            display_name="测试车辆",
            priority=PushPriority.NORMAL,
        )
        # 应该返回原始 URL（因为没有占位符）
        assert result == url
        assert isinstance(result, str)


@pytest.mark.unit
class TestExecuteBatchPush:
    """execute_batch_push 方法测试"""

    @pytest.mark.asyncio
    async def test_empty_groups(self):
        """测试空分组"""
        pusher = BatchPusher()
        result = await pusher.execute_batch_push({})
        assert result["success"] is True
        assert result["total_groups"] == 0
        assert result["success_groups"] == 0
        assert result["failed_groups"] == 0

    @pytest.mark.asyncio
    async def test_success_push(self):
        """测试成功推送"""
        pusher = BatchPusher()

        plate_config = PlateConfig(
            plate="京A12345",
            display_name="测试车辆",
            notifications=[],
        )
        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )
        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com",
            items=[item],
        )

        with patch.object(pusher, "_push_single_group") as mock_push:
            mock_push.return_value = {"success": True}

            result = await pusher.execute_batch_push({"test_key": group})

            assert result["success"] is True
            assert result["total_groups"] == 1
            assert result["success_groups"] == 1
            assert result["failed_groups"] == 0
            assert "京A12345" in result["batched_plates"]

    @pytest.mark.asyncio
    async def test_failed_push(self):
        """测试推送失败"""
        pusher = BatchPusher()

        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )
        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com",
            items=[item],
        )

        with patch.object(pusher, "_push_single_group") as mock_push:
            mock_push.return_value = {"success": False}

            result = await pusher.execute_batch_push({"test_key": group})

            assert result["success"] is False
            assert result["failed_groups"] == 1
            assert result["batched_plates"] == []

    @pytest.mark.asyncio
    async def test_exception_during_push(self):
        """测试推送时发生异常"""
        pusher = BatchPusher()

        plate_config = PlateConfig(plate="京A12345", notifications=[])
        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )
        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com",
            items=[item],
        )

        with patch.object(pusher, "_push_single_group") as mock_push:
            mock_push.side_effect = Exception("推送异常")

            result = await pusher.execute_batch_push({"test_key": group})

            assert result["success"] is False
            assert result["failed_groups"] == 1
            assert "test_key" in result["group_results"]
            assert result["group_results"]["test_key"]["success"] is False
            assert "error" in result["group_results"]["test_key"]

    @pytest.mark.asyncio
    async def test_partial_success(self):
        """测试部分成功"""
        pusher = BatchPusher()

        plate1 = PlateConfig(plate="京A12345", notifications=[])
        plate2 = PlateConfig(plate="京B67890", notifications=[])

        item1 = BatchPushItem(
            plate_config=plate1,
            title="标题1",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="标题2",
            body="内容2",
            priority=PushPriority.NORMAL,
        )

        group1 = BatchGroup(batch_key="key1", url="https://batch1.com", items=[item1])
        group2 = BatchGroup(batch_key="key2", url="https://batch2.com", items=[item2])

        with patch.object(pusher, "_push_single_group") as mock_push:
            mock_push.side_effect = [{"success": True}, {"success": False}]

            result = await pusher.execute_batch_push({"key1": group1, "key2": group2})

            assert result["success"] is True  # 至少有一个成功
            assert result["success_groups"] == 1
            assert result["failed_groups"] == 1


@pytest.mark.unit
class TestPushSingleGroup:
    """_push_single_group 方法测试"""

    @pytest.mark.asyncio
    async def test_empty_items(self):
        """测试空推送项"""
        pusher = BatchPusher()
        group = BatchGroup(batch_key="test", url="https://example.com", items=[])

        result = await pusher._push_single_group(group)

        assert result["success"] is True
        assert result["skipped"] is True
        assert "无推送项" in result["reason"]

    @pytest.mark.asyncio
    async def test_success_push(self):
        """测试成功推送"""
        pusher = BatchPusher()

        plate_config = PlateConfig(
            plate="京A12345",
            display_name="测试车辆",
            icon="https://example.com/icon.png",
            notifications=[],
        )
        item = BatchPushItem(
            plate_config=plate_config,
            title="标题",
            body="内容",
            priority=PushPriority.NORMAL,
        )
        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com/?plate={plate}",
            items=[item],
        )

        with patch(
            "jjz_alert.service.notification.batch_pusher.apprise_pusher"
        ) as mock_apprise:
            mock_apprise.send_notification = AsyncMock(return_value={"success": True})

            result = await pusher._push_single_group(group)

            assert result["success"] is True
            assert result["batch_key"] == "test_key"
            assert result["plate_count"] == 1
            assert "京A12345" in result["plates"]
            mock_apprise.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_multiple_items(self):
        """测试推送多个项目"""
        pusher = BatchPusher()

        plate1 = PlateConfig(plate="京A12345", display_name="车辆1", notifications=[])
        plate2 = PlateConfig(plate="京B67890", display_name="车辆2", notifications=[])

        item1 = BatchPushItem(
            plate_config=plate1,
            title="标题1",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="标题2",
            body="内容2",
            priority=PushPriority.HIGH,
        )

        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com/",
            items=[item1, item2],
        )

        with patch(
            "jjz_alert.service.notification.batch_pusher.apprise_pusher"
        ) as mock_apprise:
            mock_apprise.send_notification = AsyncMock(return_value={"success": True})

            result = await pusher._push_single_group(group)

            assert result["success"] is True
            assert result["plate_count"] == 2
            assert result["title"] == "进京证状态提醒"
            assert result["priority"] == "high"

    @pytest.mark.asyncio
    async def test_push_uses_first_plate_for_placeholders(self):
        """测试使用第一个车牌的信息处理占位符"""
        pusher = BatchPusher()

        plate1 = PlateConfig(
            plate="京A12345",
            display_name="第一辆车",
            icon="https://icon1.png",
            notifications=[],
        )
        plate2 = PlateConfig(
            plate="京B67890",
            display_name="第二辆车",
            icon="https://icon2.png",
            notifications=[],
        )

        item1 = BatchPushItem(
            plate_config=plate1,
            title="",
            body="内容1",
            priority=PushPriority.NORMAL,
        )
        item2 = BatchPushItem(
            plate_config=plate2,
            title="",
            body="内容2",
            priority=PushPriority.NORMAL,
        )

        group = BatchGroup(
            batch_key="test_key",
            url="https://batch.com/?plate={plate}&icon={icon}",
            items=[item1, item2],
        )

        with patch(
            "jjz_alert.service.notification.batch_pusher.apprise_pusher"
        ) as mock_apprise:
            mock_apprise.send_notification = AsyncMock(return_value={"success": True})

            await pusher._push_single_group(group)

            # 验证使用的是第一个车牌的信息
            call_args = mock_apprise.send_notification.call_args
            urls = call_args.kwargs.get("urls") or call_args[1].get("urls")
            assert "京A12345" in urls[0]
            assert "icon1" in urls[0]
