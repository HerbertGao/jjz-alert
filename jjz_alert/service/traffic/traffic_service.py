"""
限行业务服务模块

提供尾号限行查询、缓存管理和业务逻辑封装
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any

from jjz_alert.service.cache.cache_service import CacheService
from jjz_alert.service.traffic.traffic_models import TrafficRule, PlateTrafficStatus
from jjz_alert.base.http import http_get
from jjz_alert.base.error_handler import (
    with_error_handling,
    TrafficServiceError,
    NetworkError,
    APIError,
)


class TrafficService:
    """限行业务服务（整合原TrafficLimiter功能）"""

    def __init__(self, cache_service: Optional[CacheService] = None):
        self.cache_service = cache_service or CacheService()
        self._limit_rules_url = (
            "https://yw.jtgl.beijing.gov.cn/jgjxx/services/getRuleWithWeek"
        )
        self._max_retries = 3

        # 兼容原TrafficLimiter的内存缓存（逐步迁移到Redis）
        self._memory_cache = None
        self._memory_cache_date = None
        self._cache_status = "uninitialized"  # uninitialized, loading, ready, error
        self._last_update_time = None
        self._retry_count = 0

    def _is_same_day(self, date1: date, date2: date) -> bool:
        """检查两个日期是否为同一天"""
        return date1 == date2

    def _get_plate_tail_number(self, plate: str) -> str:
        """获取车牌尾号，英文字母按0处理"""
        if not plate:
            return "0"

        tail = plate[-1]

        if tail.isalpha():
            return "0"
        elif tail.isdigit():
            return tail
        else:
            return "0"

    def _parse_traffic_response(
        self, response_data: Dict[str, Any]
    ) -> List[TrafficRule]:
        """解析限行规则API响应"""
        try:
            if response_data.get("state") != "success" or "result" not in response_data:
                error_msg = response_data.get("resultMsg", "未知错误")
                logging.error(f"限行规则API返回错误: {error_msg}")
                return []

            rules = []
            for rule_data in response_data["result"]:
                try:
                    # 解析日期
                    limited_time = rule_data.get("limitedTime", "")
                    if not limited_time:
                        continue

                    rule_date = datetime.strptime(limited_time, "%Y年%m月%d日").date()
                    limited_numbers = rule_data.get("limitedNumber", "")
                    is_limited = limited_numbers != "不限行"

                    rule = TrafficRule(
                        date=rule_date,
                        limited_numbers=limited_numbers,
                        limited_time=limited_time,
                        is_limited=is_limited,
                        description=rule_data.get("description"),
                        data_source="api",
                    )

                    rules.append(rule)

                except Exception as e:
                    logging.warning(f"解析单条限行规则失败: {e}, 规则数据: {rule_data}")
                    continue

            logging.info(f"成功解析 {len(rules)} 条限行规则")
            return rules

        except Exception as e:
            logging.error(f"解析限行规则响应失败: {e}")
            return []

    @with_error_handling(
        exceptions=(TrafficServiceError, NetworkError, APIError, Exception),
        service_name="traffic_service",
        default_return=[],
        recovery_config={"max_attempts": 3, "delay": 2.0},
    )
    async def _fetch_rules_from_api(self) -> List[TrafficRule]:
        """从API获取限行规则"""
        for attempt in range(self._max_retries):
            try:
                logging.info(
                    f"正在获取限行规则... (尝试 {attempt + 1}/{self._max_retries})"
                )

                resp = http_get(self._limit_rules_url, verify=False)
                resp.raise_for_status()
                data = resp.json()

                rules = self._parse_traffic_response(data)

                if rules:
                    # 缓存所有规则
                    await self._cache_rules(rules)
                    return rules
                else:
                    logging.warning(
                        f"获取到空的限行规则列表，尝试 {attempt + 1}/{self._max_retries}"
                    )

            except Exception as e:
                logging.error(
                    f"获取限行规则失败 (尝试 {attempt + 1}/{self._max_retries}): {e}"
                )

                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2)  # 等待2秒后重试

        logging.error("获取限行规则失败，已达到最大重试次数")
        raise TrafficServiceError("获取限行规则失败，已达到最大重试次数")

    async def _cache_rules(self, rules: List[TrafficRule]) -> bool:
        """缓存限行规则"""
        try:
            # 转换为缓存格式
            cache_data = []
            for rule in rules:
                rule_dict = rule.to_dict()
                rule_dict["cached_at"] = datetime.now().isoformat()
                cache_data.append(rule_dict)

            success = await self.cache_service.cache_traffic_rules(cache_data)

            if success:
                logging.info(f"已缓存 {len(rules)} 条限行规则")

            return success

        except Exception as e:
            logging.error(f"缓存限行规则失败: {e}")
            return False

    @with_error_handling(
        exceptions=(TrafficServiceError, Exception),
        service_name="traffic_service",
        default_return=None,
    )
    async def get_traffic_rule(
        self, target_date: date, use_cache: bool = True
    ) -> Optional[TrafficRule]:
        """获取指定日期的限行规则"""
        try:
            # 优先从缓存获取
            if use_cache:
                cached_data = await self.cache_service.get_traffic_rule(target_date)
                if cached_data:
                    # 减少重复的调试日志
                    logging.debug(f"限行规则缓存命中: {target_date}")

                    # 将缓存数据转换为TrafficRule对象
                    rule_date = datetime.fromisoformat(cached_data["date"]).date()
                    return TrafficRule(
                        date=rule_date,
                        limited_numbers=cached_data.get("limited_numbers", ""),
                        limited_time=cached_data.get("limited_time", ""),
                        is_limited=cached_data.get("is_limited", False),
                        description=cached_data.get("description"),
                        data_source="cache",
                        cached_at=cached_data.get("cached_at"),
                    )

            # 缓存未命中，从API获取
            rules = await self._fetch_rules_from_api()

            # 查找目标日期的规则
            for rule in rules:
                if rule.date == target_date:
                    return rule

            logging.warning(f"未找到日期 {target_date} 的限行规则")
            return None

        except Exception as e:
            logging.error(f"获取限行规则失败: date={target_date}, error={e}")
            raise TrafficServiceError(
                f"获取限行规则失败: {e}", details={"target_date": str(target_date)}
            )

    async def get_today_traffic_rule(self) -> Optional[TrafficRule]:
        """获取今日限行规则"""
        return await self.get_traffic_rule(date.today())

    async def check_plate_limited(
        self, plate: str, target_date: Optional[date] = None
    ) -> PlateTrafficStatus:
        """检查车牌在指定日期是否限行"""
        target_date = target_date or date.today()
        tail_number = self._get_plate_tail_number(plate)

        try:
            rule = await self.get_traffic_rule(target_date)

            if not rule:
                return PlateTrafficStatus(
                    plate=plate,
                    date=target_date,
                    is_limited=False,
                    tail_number=tail_number,
                    error_message=f"未找到日期 {target_date} 的限行规则",
                )

            # 检查是否限行
            is_limited = self._is_plate_limited_by_rule(tail_number, rule)

            return PlateTrafficStatus(
                plate=plate,
                date=target_date,
                is_limited=is_limited,
                tail_number=tail_number,
                rule=rule,
            )

        except Exception as e:
            logging.error(
                f"检查车牌限行状态失败: plate={plate}, date={target_date}, error={e}"
            )
            return PlateTrafficStatus(
                plate=plate,
                date=target_date,
                is_limited=False,
                tail_number=tail_number,
                error_message=str(e),
            )

    def _is_plate_limited_by_rule(self, tail_number: str, rule: TrafficRule) -> bool:
        """根据规则判断车牌尾号是否限行"""
        try:
            if not rule.is_limited or rule.limited_numbers == "不限行":
                return False

            # 解析限行号码
            limited_numbers = rule.limited_numbers

            if "和" in limited_numbers:
                numbers = limited_numbers.split("和")
                return tail_number in numbers
            else:
                # 处理其他可能的格式
                return tail_number in limited_numbers

        except Exception as e:
            logging.warning(f"判断车牌限行失败: {e}")
            return False

    async def check_multiple_plates(
        self, plates: List[str], target_date: Optional[date] = None
    ) -> Dict[str, PlateTrafficStatus]:
        """批量检查多个车牌的限行状态"""
        results = {}
        target_date = target_date or date.today()

        # 先获取当日规则，避免重复API调用
        rule = await self.get_traffic_rule(target_date)

        for plate in plates:
            try:
                tail_number = self._get_plate_tail_number(plate)

                if rule:
                    is_limited = self._is_plate_limited_by_rule(tail_number, rule)
                    status = PlateTrafficStatus(
                        plate=plate,
                        date=target_date,
                        is_limited=is_limited,
                        tail_number=tail_number,
                        rule=rule,
                    )
                else:
                    status = PlateTrafficStatus(
                        plate=plate,
                        date=target_date,
                        is_limited=False,
                        tail_number=tail_number,
                        error_message=f"未找到日期 {target_date} 的限行规则",
                    )

                results[plate] = status

            except Exception as e:
                logging.error(f"检查车牌 {plate} 限行状态失败: {e}")
                results[plate] = PlateTrafficStatus(
                    plate=plate,
                    date=target_date,
                    is_limited=False,
                    tail_number=self._get_plate_tail_number(plate),
                    error_message=str(e),
                )

        return results

    async def get_week_rules(
        self, start_date: Optional[date] = None
    ) -> List[TrafficRule]:
        """获取一周的限行规则"""
        start_date = start_date or date.today()
        rules = []

        # 生成一周的日期列表
        dates = [start_date + timedelta(days=i) for i in range(7)]

        # 批量获取缓存
        cached_rules = await self.cache_service.get_traffic_rules_batch(dates)

        # 处理缓存命中的规则
        for target_date, cached_data in cached_rules.items():
            if cached_data:
                rule_date = datetime.fromisoformat(cached_data["date"]).date()
                rule = TrafficRule(
                    date=rule_date,
                    limited_numbers=cached_data.get("limited_numbers", ""),
                    limited_time=cached_data.get("limited_time", ""),
                    is_limited=cached_data.get("is_limited", False),
                    description=cached_data.get("description"),
                    data_source="cache",
                    cached_at=cached_data.get("cached_at"),
                )
                rules.append(rule)

        # 对于缓存未命中的日期，从API获取
        missing_dates = [date for date, data in cached_rules.items() if data is None]
        if missing_dates:
            logging.debug(f"缓存未命中的日期: {missing_dates}")
            api_rules = await self._fetch_rules_from_api()

            for target_date in missing_dates:
                for rule in api_rules:
                    if rule.date == target_date:
                        rules.append(rule)
                        break

        logging.debug(f"成功获取 {len(rules)} 条限行规则")
        return rules

    async def refresh_rules_cache(self) -> List[TrafficRule]:
        """强制刷新限行规则缓存"""
        try:
            # 清理旧缓存
            await self.cache_service.clear_cache("traffic")

            # 重新获取
            return await self._fetch_rules_from_api()

        except Exception as e:
            logging.error(f"刷新限行规则缓存失败: {e}")
            return []

    async def get_service_status(
        self, today_rule: Optional[TrafficRule] = None
    ) -> Dict[str, Any]:
        """获取限行服务状态"""
        try:
            # 如果没有传入today_rule，才去查询
            if today_rule is None:
                today_rule = await self.get_today_traffic_rule()

            # 检查缓存统计
            cache_stats = await self.cache_service.get_cache_stats(days=1)
            traffic_stats = cache_stats.get("traffic", {})

            # 获取缓存的规则数量
            cache_info = await self.cache_service.get_cache_info()
            traffic_keys_count = cache_info.get("key_counts", {}).get("traffic", 0)

            return {
                "service": "TrafficService",
                "status": "healthy",
                "today_rule": today_rule.to_dict() if today_rule else None,
                "cached_rules_count": traffic_keys_count,
                "cache_stats": {
                    "hits": traffic_stats.get("total_hits", 0),
                    "misses": traffic_stats.get("total_misses", 0),
                    "hit_rate": traffic_stats.get("hit_rate", 0.0),
                },
                "api_url": self._limit_rules_url,
            }

        except Exception as e:
            logging.error(f"获取限行服务状态失败: {e}")
            return {"service": "TrafficService", "status": "error", "error": str(e)}

    # =============================================================================
    # 兼容原TrafficLimiter接口的方法
    # =============================================================================

    def _fetch_limit_rules_sync(self) -> Optional[List[Dict]]:
        """同步方式获取限行规则（兼容原TrafficLimiter）"""
        try:
            logging.info(f"正在获取限行规则... (重试次数: {self._retry_count})")
            resp = http_get(self._limit_rules_url, verify=False)
            resp.raise_for_status()
            data = resp.json()

            if data.get("state") == "success" and "result" in data:
                logging.info(f'成功获取限行规则，共 {len(data["result"])} 条')
                return data["result"]
            else:
                logging.error(f'获取限行规则失败: {data.get("resultMsg", "未知错误")}')
                return None
        except Exception as e:
            logging.error(f"获取限行规则异常: {e}")
            return None

    def _update_memory_cache_if_needed(self):
        """如果需要，更新内存缓存（兼容原TrafficLimiter）"""
        today = date.today()

        if (
            not self._memory_cache
            or not self._memory_cache_date
            or not self._is_same_day(self._memory_cache_date, today)
        ):
            self._update_memory_cache()

    def _update_memory_cache(self):
        """更新内存缓存（兼容原TrafficLimiter）"""
        import time

        self._cache_status = "loading"
        self._retry_count = 0

        while self._retry_count < self._max_retries:
            try:
                rules = self._fetch_limit_rules_sync()
                if rules:
                    self._memory_cache = rules
                    self._memory_cache_date = date.today()
                    self._last_update_time = time.time()
                    self._cache_status = "ready"
                    logging.info(f"成功缓存 {len(rules)} 条限行规则到内存")
                    return
                else:
                    self._retry_count += 1
                    if self._retry_count < self._max_retries:
                        logging.warning(
                            f"获取限行规则失败，{self._retry_count}/{self._max_retries} 次重试"
                        )
                        time.sleep(2)
                    else:
                        logging.error("获取限行规则失败，已达到最大重试次数")
                        self._cache_status = "error"
                        self._memory_cache = []
                        self._memory_cache_date = date.today()
                        self._last_update_time = time.time()
            except Exception as e:
                self._retry_count += 1
                logging.error(f"更新内存缓存异常: {e}")
                if self._retry_count < self._max_retries:
                    logging.warning(
                        f"准备第 {self._retry_count}/{self._max_retries} 次重试"
                    )
                    time.sleep(2)
                else:
                    logging.error("更新内存缓存失败，已达到最大重试次数")
                    self._cache_status = "error"
                    self._memory_cache = []
                    self._memory_cache_date = date.today()
                    self._last_update_time = time.time()

    def preload_cache(self):
        """预加载缓存（兼容原TrafficLimiter接口）"""
        logging.info("开始预加载尾号限行规则缓存")
        self._update_memory_cache()

        if self._cache_status == "ready":
            logging.info("尾号限行规则缓存预加载成功")
        else:
            logging.warning("尾号限行规则缓存预加载失败，将在使用时重试")

    def get_cache_status(self) -> Dict:
        """获取缓存状态信息（兼容原TrafficLimiter接口）"""
        return {
            "status": self._cache_status,
            "cache_date": (
                self._memory_cache_date.isoformat() if self._memory_cache_date else None
            ),
            "cache_count": len(self._memory_cache) if self._memory_cache else 0,
            "last_update": self._last_update_time,
            "retry_count": self._retry_count,
        }

    def check_plate_limited_sync(self, plate: str) -> bool:
        """检查车牌是否限行（兼容原TrafficLimiter接口，仅今日，同步方法）"""
        self._update_memory_cache_if_needed()
        return self._is_limited_today_memory(plate)

    def _is_limited_today_memory(self, plate: str) -> bool:
        """使用内存缓存检查指定车牌今天是否限行"""
        if not self._memory_cache or not self._memory_cache_date:
            return False

        today = date.today()
        if not self._is_same_day(self._memory_cache_date, today):
            return False

        # 获取今天的限行规则
        today_rule = None
        for rule in self._memory_cache:
            rule_date = datetime.strptime(rule["limitedTime"], "%Y年%m月%d日").date()
            if self._is_same_day(rule_date, today):
                today_rule = rule
                break

        if not today_rule:
            return False

        # 如果是不限行，返回False
        if today_rule["limitedNumber"] == "不限行":
            return False

        # 获取车牌尾号
        tail_number = self._get_plate_tail_number(plate)

        # 检查尾号是否在限行范围内
        limited_numbers = today_rule["limitedNumber"]

        # 解析限行号码（格式如："1和6"、"2和7"等）
        if "和" in limited_numbers:
            numbers = limited_numbers.split("和")
            return tail_number in numbers
        else:
            return tail_number in limited_numbers

    def check_plate_limited_on(self, plate: str, target: date) -> bool:
        """检查车牌在指定日期是否限行（兼容原TrafficLimiter接口）"""
        self._update_memory_cache_if_needed()
        if not self._memory_cache:
            return False

        # 查找目标日期对应的限行规则
        rule_for_day = None
        for rule in self._memory_cache:
            try:
                rule_date = datetime.strptime(
                    rule["limitedTime"], "%Y年%m月%d日"
                ).date()
            except Exception:
                continue
            if self._is_same_day(rule_date, target):
                rule_for_day = rule
                break

        if not rule_for_day or rule_for_day.get("limitedNumber") == "不限行":
            return False

        tail_number = self._get_plate_tail_number(plate)
        limited_numbers = rule_for_day["limitedNumber"]
        if "和" in limited_numbers:
            numbers = limited_numbers.split("和")
            return tail_number in numbers
        else:
            return tail_number in limited_numbers

    def get_today_limit_info(self) -> Optional[Dict]:
        """获取今天的限行信息（兼容原TrafficLimiter接口）"""
        self._update_memory_cache_if_needed()

        if not self._memory_cache:
            return None

        today = date.today()
        for rule in self._memory_cache:
            rule_date = datetime.strptime(rule["limitedTime"], "%Y年%m月%d日").date()
            if self._is_same_day(rule_date, today):
                return rule

        return None

    async def get_smart_traffic_rules(self) -> Dict[str, Optional[TrafficRule]]:
        """
        智能获取限行规则 - 根据当前时间决定查询今天还是明天的规则
        20:30前查询今天，20:30后查询明天
        """
        from datetime import datetime

        now = datetime.now()
        send_next_day = now.hour > 20 or (now.hour == 20 and now.minute >= 30)

        today = date.today()
        tomorrow = today + timedelta(days=1)

        result = {}

        # 使用批量查询，减少重复的缓存查询日志
        target_date = tomorrow if send_next_day else today
        cached_rules = await self.cache_service.get_traffic_rules_batch([target_date])

        target_rule = None
        if cached_rules.get(target_date):
            cached_data = cached_rules[target_date]
            rule_date = datetime.fromisoformat(cached_data["date"]).date()
            target_rule = TrafficRule(
                date=rule_date,
                limited_numbers=cached_data.get("limited_numbers", ""),
                limited_time=cached_data.get("limited_time", ""),
                is_limited=cached_data.get("is_limited", False),
                description=cached_data.get("description"),
                data_source="cache",
                cached_at=cached_data.get("cached_at"),
            )
        else:
            # 缓存未命中，从API获取
            target_rule = await self.get_traffic_rule(target_date)

        result["target_date"] = target_date
        result["target_rule"] = target_rule
        result["query_type"] = "tomorrow" if send_next_day else "today"

        rule_desc = target_rule.limited_numbers if target_rule else "无规则"
        time_desc = "明日" if send_next_day else "今日"
        logging.info(
            f"20:30{'后' if send_next_day else '前'}，查询{time_desc}限行规则: {rule_desc}"
        )

        return result


# 需要import asyncio
import asyncio

# 全局限行服务实例
traffic_service = TrafficService()

# 兼容原TrafficLimiter的全局实例别名
traffic_limiter = traffic_service
