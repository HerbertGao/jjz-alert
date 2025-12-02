"""
缓存服务模块

提供统一的缓存管理接口
"""

import logging
from dataclasses import asdict
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from jjz_alert.base.error_handler import (
    with_error_handling,
    CacheError,
    RedisError,
)
from jjz_alert.config import get_cache_config
from jjz_alert.config.redis.operations import RedisOperations


class CacheService:
    """缓存服务"""

    def __init__(self, redis_ops: Optional[RedisOperations] = None):
        self.redis_ops = redis_ops or RedisOperations()
        self.config = get_cache_config()

        # 缓存键前缀
        self.JJZ_PREFIX = "jjz:"
        self.TRAFFIC_PREFIX = "traffic:"
        self.PUSH_HISTORY_PREFIX = "push_history:"
        self.STATS_PREFIX = "stats:"

    # =============================================================================
    # 进京证数据缓存
    # =============================================================================

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=False,
    )
    async def cache_jjz_data(self, plate: str, jjz_data: Dict[str, Any]) -> bool:
        """缓存进京证数据 - 永久缓存，供推送和后续其他操作使用"""
        key = f"{self.JJZ_PREFIX}{plate}"

        # 添加缓存时间戳
        cache_data = {**jjz_data, "cached_at": datetime.now().isoformat()}

        # 永久缓存，不设置TTL
        success = await self.redis_ops.set(key, cache_data)

        if success:
            logging.debug(f"进京证数据已缓存: {plate}")
            # 更新统计信息
            await self._update_cache_stats("jjz", "set")

        return success

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=None,
    )
    async def get_jjz_data(self, plate: str) -> Optional[Dict[str, Any]]:
        """获取进京证缓存数据"""
        key = f"{self.JJZ_PREFIX}{plate}"
        data = await self.redis_ops.get(key)

        if data:
            # 更新统计信息
            await self._update_cache_stats("jjz", "hit")
            logging.debug(f"进京证缓存命中: {plate}")
            return data
        else:
            # 更新统计信息
            await self._update_cache_stats("jjz", "miss")
            logging.debug(f"进京证缓存未命中: {plate}")
            return None

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=False,
    )
    async def delete_jjz_data(self, plate: str) -> bool:
        """删除进京证缓存数据"""
        key = f"{self.JJZ_PREFIX}{plate}"
        result = await self.redis_ops.delete(key)

        if result > 0:
            logging.debug(f"进京证缓存已删除: {plate}")
            await self._update_cache_stats("jjz", "delete")

        return result > 0

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=[],
    )
    async def get_all_jjz_plates(self) -> List[str]:
        """获取所有已缓存的车牌号"""
        pattern = f"{self.JJZ_PREFIX}*"
        keys = await self.redis_ops.keys(pattern)

        # 提取车牌号
        plates = []
        prefix_len = len(self.JJZ_PREFIX)
        for key in keys:
            if key.startswith(self.JJZ_PREFIX):
                plate = key[prefix_len:]
                plates.append(plate)

        return plates

    # =============================================================================
    # 限行规则缓存
    # =============================================================================

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=False,
    )
    async def cache_traffic_rules(self, rules_data: List[Dict[str, Any]]) -> bool:
        """缓存限行规则数据"""
        # 按日期存储规则
        success_count = 0

        for rule in rules_data:
            rule_date = rule.get("limited_time", "")
            if not rule_date:
                continue

            # 解析日期
            try:
                date_obj = datetime.strptime(rule_date, "%Y年%m月%d日").date()
                date_str = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                logging.warning(f"无效的限行规则日期格式: {rule_date}")
                continue

            key = f"{self.TRAFFIC_PREFIX}rules:{date_str}"

            # 计算到当天24:00的TTL
            now = datetime.now()
            end_of_day = datetime.combine(
                date_obj, datetime.max.time().replace(microsecond=0)
            )
            ttl_seconds = int((end_of_day - now).total_seconds())

            # 确保TTL为正数
            if ttl_seconds <= 0:
                ttl_seconds = 1  # 至少缓存1秒

            cache_data = {
                **rule,
                "cached_at": now.isoformat(),
                "expires_at": end_of_day.isoformat(),
            }

            if await self.redis_ops.set(key, cache_data, ttl=ttl_seconds):
                success_count += 1

        if success_count > 0:
            logging.info(f"限行规则已缓存: {success_count}条")
            await self._update_cache_stats("traffic", "set", success_count)

        return success_count > 0

    @with_error_handling(
        exceptions=(CacheError, RedisError, Exception),
        service_name="cache_service",
        default_return=None,
    )
    async def get_traffic_rule(self, target_date: date) -> Optional[Dict[str, Any]]:
        """获取指定日期的限行规则"""
        date_str = target_date.strftime("%Y-%m-%d")
        key = f"{self.TRAFFIC_PREFIX}rules:{date_str}"

        data = await self.redis_ops.get(key)

        if data:
            await self._update_cache_stats("traffic", "hit")
            logging.debug(f"限行规则缓存命中: {date_str}")
            return data
        else:
            await self._update_cache_stats("traffic", "miss")
            logging.debug(f"限行规则缓存未命中: {date_str}")
            return None

    async def get_today_traffic_rule(self) -> Optional[Dict[str, Any]]:
        """获取今日限行规则"""
        return await self.get_traffic_rule(date.today())

    async def get_traffic_rules_batch(
        self, dates: List[date]
    ) -> Dict[date, Optional[Dict[str, Any]]]:
        """批量获取多个日期的限行规则"""
        try:
            results = {}

            for target_date in dates:
                date_str = target_date.strftime("%Y-%m-%d")
                key = f"{self.TRAFFIC_PREFIX}rules:{date_str}"

                data = await self.redis_ops.get(key)

                if data:
                    await self._update_cache_stats("traffic", "hit")
                    results[target_date] = data
                else:
                    await self._update_cache_stats("traffic", "miss")
                    results[target_date] = None

            # 只在批量查询时记录一次日志
            hit_count = sum(1 for data in results.values() if data is not None)
            logging.debug(f"批量查询限行规则: 查询{len(dates)}天，命中{hit_count}天")

            return results

        except Exception as e:
            logging.error(f"批量获取限行规则缓存失败: dates={dates}, error={e}")
            await self._update_cache_stats("traffic", "error")
            return {date: None for date in dates}

    # =============================================================================
    # 推送历史缓存
    # =============================================================================

    async def record_push_history(
        self, plate: str, push_record: Dict[str, Any]
    ) -> bool:
        """记录推送历史"""
        try:
            key = f"{self.PUSH_HISTORY_PREFIX}{plate}"

            # 添加时间戳
            record_with_timestamp = {
                **push_record,
                "timestamp": datetime.now().isoformat(),
            }

            # 添加到列表头部
            await self.redis_ops.lpush(key, record_with_timestamp)

            # 保持列表长度，只保留最近100条记录
            await self.redis_ops.ltrim(key, 0, 99)

            # 设置过期时间
            await self.redis_ops.expire(key, self.config.push_history_ttl)

            logging.debug(f"推送历史已记录: {plate}")
            return True

        except Exception as e:
            logging.error(f"记录推送历史失败: plate={plate}, error={e}")
            return False

    async def get_push_history(
        self, plate: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取推送历史"""
        try:
            key = f"{self.PUSH_HISTORY_PREFIX}{plate}"
            return await self.redis_ops.lrange(key, 0, limit - 1)
        except Exception as e:
            logging.error(f"获取推送历史失败: plate={plate}, error={e}")
            return []

    async def check_recent_push(
        self, plate: str, message_type: str, window_minutes: int = 60
    ) -> bool:
        """检查最近是否有相同类型的推送（防重复推送）"""
        try:
            history = await self.get_push_history(plate, limit=20)
            cutoff_time = datetime.now() - timedelta(minutes=window_minutes)

            for record in history:
                try:
                    record_time = datetime.fromisoformat(record["timestamp"])
                    if (
                        record_time > cutoff_time
                        and record.get("message_type") == message_type
                    ):
                        return True
                except (ValueError, KeyError):
                    continue

            return False

        except Exception as e:
            logging.error(f"检查重复推送失败: plate={plate}, error={e}")
            return False

    # =============================================================================
    # 缓存统计
    # =============================================================================

    async def _update_cache_stats(
        self, cache_type: str, operation: str, count: int = 1
    ):
        """更新缓存统计信息"""
        try:
            today = date.today().strftime("%Y-%m-%d")
            key = f"{self.STATS_PREFIX}{cache_type}:{today}"

            # 增加计数
            field = f"{operation}_count"
            await self.redis_ops.hincrby(key, field, count)

            # 设置过期时间（保留30天）
            await self.redis_ops.expire(key, 30 * 24 * 3600)

        except Exception as e:
            logging.debug(f"更新缓存统计失败: {e}")

    async def get_cache_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            stats = {
                "jjz": {
                    "total_hits": 0,
                    "total_misses": 0,
                    "total_sets": 0,
                    "total_errors": 0,
                },
                "traffic": {
                    "total_hits": 0,
                    "total_misses": 0,
                    "total_sets": 0,
                    "total_errors": 0,
                },
                "daily_stats": [],
            }

            # 获取最近几天的统计
            for i in range(days):
                target_date = date.today() - timedelta(days=i)
                date_str = target_date.strftime("%Y-%m-%d")

                daily_stat = {"date": date_str}

                for cache_type in ["jjz", "traffic"]:
                    key = f"{self.STATS_PREFIX}{cache_type}:{date_str}"
                    cache_data = await self.redis_ops.hgetall(key)

                    hits = int(cache_data.get("hit_count", 0))
                    misses = int(cache_data.get("miss_count", 0))
                    sets = int(cache_data.get("set_count", 0))
                    errors = int(cache_data.get("error_count", 0))

                    daily_stat[f"{cache_type}_hits"] = hits
                    daily_stat[f"{cache_type}_misses"] = misses
                    daily_stat[f"{cache_type}_sets"] = sets
                    daily_stat[f"{cache_type}_errors"] = errors

                    # 累加到总统计
                    stats[cache_type]["total_hits"] += hits
                    stats[cache_type]["total_misses"] += misses
                    stats[cache_type]["total_sets"] += sets
                    stats[cache_type]["total_errors"] += errors

                stats["daily_stats"].append(daily_stat)

            # 计算命中率
            for cache_type in ["jjz", "traffic"]:
                total_requests = (
                    stats[cache_type]["total_hits"] + stats[cache_type]["total_misses"]
                )
                if total_requests > 0:
                    hit_rate = stats[cache_type]["total_hits"] / total_requests * 100
                    stats[cache_type]["hit_rate"] = round(hit_rate, 2)
                else:
                    stats[cache_type]["hit_rate"] = 0.0

            return stats

        except Exception as e:
            logging.error(f"获取缓存统计失败: {e}")
            return {}

    # =============================================================================
    # 缓存管理
    # =============================================================================

    async def clear_cache(self, cache_type: Optional[str] = None) -> Dict[str, int]:
        """清理缓存"""
        try:
            result = {"deleted_keys": 0}

            if cache_type is None or cache_type == "jjz":
                # 清理进京证缓存
                jjz_keys = await self.redis_ops.keys(f"{self.JJZ_PREFIX}*")
                if jjz_keys:
                    deleted = await self.redis_ops.delete(*jjz_keys)
                    result["jjz_deleted"] = deleted
                    result["deleted_keys"] += deleted

            if cache_type is None or cache_type == "traffic":
                # 清理限行规则缓存
                traffic_keys = await self.redis_ops.keys(f"{self.TRAFFIC_PREFIX}*")
                if traffic_keys:
                    deleted = await self.redis_ops.delete(*traffic_keys)
                    result["traffic_deleted"] = deleted
                    result["deleted_keys"] += deleted

            if cache_type is None or cache_type == "push_history":
                # 清理推送历史缓存
                push_keys = await self.redis_ops.keys(f"{self.PUSH_HISTORY_PREFIX}*")
                if push_keys:
                    deleted = await self.redis_ops.delete(*push_keys)
                    result["push_history_deleted"] = deleted
                    result["deleted_keys"] += deleted

            logging.info(f"缓存清理完成: {result}")
            return result

        except Exception as e:
            logging.error(f"清理缓存失败: {e}")
            return {"error": str(e)}

    async def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        try:
            # 获取各类缓存的键数量
            jjz_keys = await self.redis_ops.keys(f"{self.JJZ_PREFIX}*")
            traffic_keys = await self.redis_ops.keys(f"{self.TRAFFIC_PREFIX}*")
            push_history_keys = await self.redis_ops.keys(
                f"{self.PUSH_HISTORY_PREFIX}*"
            )

            # 获取缓存配置
            config_dict = asdict(self.config)

            info = {
                "config": config_dict,
                "key_counts": {
                    "jjz": len(jjz_keys),
                    "traffic": len(traffic_keys),
                    "push_history": len(push_history_keys),
                    "total": len(jjz_keys) + len(traffic_keys) + len(push_history_keys),
                },
                "cached_plates": await self.get_all_jjz_plates(),
            }

            return info

        except Exception as e:
            logging.error(f"获取缓存信息失败: {e}")
            return {"error": str(e)}


# 全局缓存服务实例
cache_service = CacheService()
