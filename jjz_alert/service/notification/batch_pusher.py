"""
批量推送聚合器

支持将多个车牌的推送消息合并为单条发送
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple

from jjz_alert.config import PlateConfig
from jjz_alert.service.notification.apprise_pusher import apprise_pusher
from jjz_alert.service.notification.push_priority import PushPriority, PriorityMapper
from jjz_alert.service.notification.url_utils import (
    process_url_placeholders,
    parse_apprise_url_item,
)


@dataclass
class BatchPushItem:
    """批量推送项"""

    plate_config: PlateConfig
    title: str
    body: str
    priority: PushPriority
    jjz_data: Dict[str, Any] = field(default_factory=dict)
    traffic_reminder: Optional[str] = None


@dataclass
class BatchGroup:
    """批量推送分组"""

    batch_key: str
    url: str  # 原始 URL（未处理占位符）
    items: List[BatchPushItem] = field(default_factory=list)


class BatchPusher:
    """批量推送聚合器"""

    def __init__(self):
        self._batch_groups: Dict[str, BatchGroup] = {}

    def collect_batch_urls(
        self, plate_configs: List[PlateConfig]
    ) -> Dict[str, List[Tuple[PlateConfig, str]]]:
        """
        收集所有启用了批量推送的 URL

        Args:
            plate_configs: 车牌配置列表

        Returns:
            {batch_key: [(plate_config, url), ...]}
        """
        batch_urls: Dict[str, List[Tuple[PlateConfig, str]]] = defaultdict(list)

        for plate_config in plate_configs:
            for notification in plate_config.notifications:
                if notification.type != "apprise":
                    continue

                for url_item in notification.urls:
                    url, batch_key = parse_apprise_url_item(url_item)
                    if batch_key:
                        batch_urls[batch_key].append((plate_config, url))

        return dict(batch_urls)

    def get_batch_urls_for_plate(self, plate_config: PlateConfig) -> Set[str]:
        """
        获取单个车牌中启用了批量推送的原始 URL 集合

        Args:
            plate_config: 车牌配置

        Returns:
            启用了批量推送的 URL 集合（原始 URL，未处理占位符）
        """
        batch_urls = set()

        for notification in plate_config.notifications:
            if notification.type != "apprise":
                continue

            for url_item in notification.urls:
                url, batch_key = parse_apprise_url_item(url_item)
                if batch_key:
                    batch_urls.add(url)

        return batch_urls

    def group_push_items(
        self,
        items: List[BatchPushItem],
        plate_configs: List[PlateConfig],
    ) -> Dict[str, BatchGroup]:
        """
        将推送项按 batch_key 分组

        Args:
            items: 推送项列表
            plate_configs: 车牌配置列表（用于查找 batch_key 配置）

        Returns:
            {batch_key: BatchGroup}
        """
        # 构建 plate -> batch_key -> url 的映射
        plate_batch_map: Dict[str, Dict[str, str]] = {}
        for plate_config in plate_configs:
            plate_batch_map[plate_config.plate] = {}
            for notification in plate_config.notifications:
                if notification.type != "apprise":
                    continue
                for url_item in notification.urls:
                    url, batch_key = parse_apprise_url_item(url_item)
                    if batch_key:
                        plate_batch_map[plate_config.plate][batch_key] = url

        # 分组推送项
        groups: Dict[str, BatchGroup] = {}
        for item in items:
            plate = item.plate_config.plate
            batch_keys = plate_batch_map.get(plate, {})

            for batch_key, url in batch_keys.items():
                if batch_key not in groups:
                    groups[batch_key] = BatchGroup(
                        batch_key=batch_key,
                        url=url,
                        items=[],
                    )
                groups[batch_key].items.append(item)

        return groups

    def merge_messages(
        self,
        items: List[BatchPushItem],
    ) -> Tuple[str, str, PushPriority]:
        """
        合并多个推送项为单条消息

        Args:
            items: 推送项列表

        Returns:
            (merged_title, merged_body, max_priority)
        """
        if not items:
            return "", "", PushPriority.NORMAL

        if len(items) == 1:
            # 单条消息不需要合并
            item = items[0]
            return item.title, item.body, item.priority

        # 合并标题
        merged_title = "进京证状态提醒"

        # 合并正文：直接拼接
        body_parts = []
        for item in items:
            body_parts.append(item.body)

        merged_body = "\n".join(body_parts)

        # 优先级取最高
        max_priority = self._get_max_priority(items)

        return merged_title, merged_body, max_priority

    async def execute_batch_push(
        self,
        groups: Dict[str, BatchGroup],
    ) -> Dict[str, Any]:
        """
        执行批量推送

        Args:
            groups: 批量分组 {batch_key: BatchGroup}

        Returns:
            推送结果
        """
        results = {
            "success": False,
            "total_groups": len(groups),
            "success_groups": 0,
            "failed_groups": 0,
            "group_results": {},
            "batched_plates": set(),  # 已通过批量推送的车牌集合
            "timestamp": datetime.now().isoformat(),
        }

        if not groups:
            results["success"] = True
            return results

        for batch_key, group in groups.items():
            try:
                group_result = await self._push_single_group(group)
                results["group_results"][batch_key] = group_result

                if group_result.get("success"):
                    results["success_groups"] += 1
                    # 记录已推送的车牌
                    for item in group.items:
                        results["batched_plates"].add(item.plate_config.plate)
                else:
                    results["failed_groups"] += 1

            except Exception as e:
                error_msg = f"批量推送组 {batch_key} 失败: {e}"
                logging.error(error_msg)
                results["group_results"][batch_key] = {
                    "success": False,
                    "error": error_msg,
                }
                results["failed_groups"] += 1

        results["success"] = results["success_groups"] > 0
        # 转换 set 为 list 以便序列化
        results["batched_plates"] = list(results["batched_plates"])

        return results

    async def _push_single_group(self, group: BatchGroup) -> Dict[str, Any]:
        """
        推送单个批量分组

        Args:
            group: 批量分组

        Returns:
            推送结果
        """
        if not group.items:
            return {"success": True, "skipped": True, "reason": "无推送项"}

        # 合并消息
        title, body, priority = self.merge_messages(group.items)

        # 处理 URL 占位符
        # 对于批量推送，使用第一个车牌的信息处理占位符
        first_item = group.items[0]
        processed_url = process_url_placeholders(
            url=group.url,
            plate=first_item.plate_config.plate,
            display_name=first_item.plate_config.display_name
            or first_item.plate_config.plate,
            priority=priority,
            icon=first_item.plate_config.icon,
        )

        # 获取 Apprise 优先级
        apprise_priority = PriorityMapper.get_platform_priority(priority, "apprise")

        # 执行推送
        result = await apprise_pusher.send_notification(
            urls=[processed_url],
            title=title,
            body=body,
            priority=apprise_priority,
            body_format="text",
        )

        return {
            "success": result.get("success", False),
            "batch_key": group.batch_key,
            "plate_count": len(group.items),
            "plates": [item.plate_config.plate for item in group.items],
            "title": title,
            "priority": priority.value,
            "url_result": result,
        }

    def _get_max_priority(self, items: List[BatchPushItem]) -> PushPriority:
        """
        获取推送项列表中的最高优先级

        Args:
            items: 推送项列表

        Returns:
            最高优先级
        """
        if not items:
            return PushPriority.NORMAL

        priorities = [item.priority for item in items]
        if PushPriority.HIGH in priorities:
            return PushPriority.HIGH
        return PushPriority.NORMAL


# 全局实例
batch_pusher = BatchPusher()
