"""
进京证业务服务模块

提供进京证查询、缓存管理和业务逻辑封装
"""

import asyncio
import logging
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from jjz_alert.base.error_handler import (
    APIError,
    handle_critical_error,
    is_token_error,
    with_retry,
    with_error_handling,
    NetworkError,
    ConfigurationError,
)
from jjz_alert.base.http import http_post
from jjz_alert.base.logger import get_structured_logger, LogCategory
from jjz_alert.config.config import JJZAccount
from jjz_alert.service.cache.cache_service import CacheService
from jjz_alert.service.jjz.jjz_parse import parse_all_jjz_records
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum


def _is_effective_on(record: JJZStatus, day: date) -> bool:
    """记录是否在 `day` 当日构成有效覆盖。

    必须满足：valid_start/valid_end 均能解析为日期、day 在区间内、blztmc 含
    "生效中" 或 "待生效"（已批准未来生效也算覆盖）。

    实现注意：fromisoformat 走 ``datetime.date`` 而非模块级 ``date`` 符号，
    避免单元测试用 ``patch("jjz_service.date")`` 整体替换时把解析也炸掉。
    """
    import datetime as _dt

    if not record.valid_start or not record.valid_end:
        return False
    try:
        start = _dt.date.fromisoformat(record.valid_start)
        end = _dt.date.fromisoformat(record.valid_end)
    except (TypeError, ValueError):
        return False
    if not (start <= day <= end):
        return False
    blztmc = record.blztmc or ""
    return "生效中" in blztmc or "待生效" in blztmc


class JJZService:
    """进京证业务服务"""

    def __init__(self, cache_service: Optional[CacheService] = None):
        self.cache_service = cache_service or CacheService()
        self._accounts: List[JJZAccount] = []
        self._last_config_load = None
        self.structured_logger = get_structured_logger("jjz_service")

    def check_jjz_status(self, url: str, token: str) -> Dict[str, Any]:
        """查询进京证状态"""
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            resp = http_post(url, headers=headers, json_data={})
            resp.raise_for_status()
            logging.debug(f"进京证状态查询成功: {resp.json()}")
            return resp.json()
        except Exception as e:
            error_msg = str(e)

            # 特殊处理系统级错误
            if (
                "TLS connect error" in error_msg
                or "OPENSSL_internal" in error_msg
                or "curl: (35)" in error_msg
                or "Connection" in error_msg
                or "Session.request() got an unexpected keyword argument" in error_msg
                or "HTTP POST请求失败" in error_msg
                or "HTTP GET请求失败" in error_msg
            ):

                error_type = "系统级错误"
                if "TLS" in error_msg or "SSL" in error_msg:
                    error_type = "TLS/SSL连接错误"
                elif "Session.request()" in error_msg:
                    error_type = "HTTP请求参数错误"
                elif "HTTP" in error_msg:
                    error_type = "HTTP请求失败"
                elif "Connection" in error_msg:
                    error_type = "网络连接错误"

                logging.error(f"{error_type}: {error_msg}")
                # 异步通知管理员（不等待结果）
                asyncio.create_task(
                    self._notify_admin_system_error(error_type, error_msg)
                )
                return {"error": f"{error_type}: {error_msg}"}
            else:
                logging.error(f"进京证查询失败: {error_msg}")
                return {"error": error_msg}

    def load_accounts(self) -> List[JJZAccount]:
        """加载进京证账户配置"""
        try:
            current_time = datetime.now()

            # 缓存配置1分钟，避免频繁读取
            if (
                self._last_config_load is None
                or (current_time - self._last_config_load).total_seconds() > 60
            ):
                # 使用全局配置管理器实例，避免重复加载
                from jjz_alert.config.config import config_manager

                app_config = config_manager.load_config()
                self._accounts = app_config.jjz_accounts
                self._last_config_load = current_time
                logging.debug(f"已加载 {len(self._accounts)} 个进京证账户配置")

            return self._accounts

        except Exception as e:
            logging.error(f"加载进京证账户配置失败: {e}")
            return []

    def _determine_status(
        self, blzt: str, blztmc: str, yxqz: str, yxqs: str = None
    ) -> str:
        """根据新API格式确定进京证状态"""
        try:
            logging.debug(
                f"状态判断参数: blzt={blzt}, blztmc={blztmc}, yxqz={yxqz}, yxqs={yxqs}"
            )

            if not yxqz:
                return JJZStatusEnum.INVALID.value

            # 解析有效期结束时间 (格式: 2025-08-19)
            end_date = datetime.strptime(yxqz, "%Y-%m-%d").date()
            today = date.today()

            if end_date < today:
                return JJZStatusEnum.EXPIRED.value
            elif (
                (blzt == "1" or blzt == 1)
                and "审核通过" in blztmc
                and "生效中" in blztmc
            ):
                return JJZStatusEnum.VALID.value
            elif (
                (blzt == "6" or blzt == 6)
                and "审核通过" in blztmc
                and "待生效" in blztmc
            ):
                # 待生效状态，需要检查是否在有效期内
                if yxqs:
                    try:
                        start_date = datetime.strptime(yxqs, "%Y-%m-%d").date()
                        if start_date <= today <= end_date:
                            return (
                                JJZStatusEnum.VALID.value
                            )  # 待生效但在有效期内，视为有效
                        else:
                            return (
                                JJZStatusEnum.APPROVED_PENDING.value
                            )  # 待生效但还未到生效时间
                    except Exception:
                        return JJZStatusEnum.APPROVED_PENDING.value
                else:
                    return JJZStatusEnum.APPROVED_PENDING.value
            elif (blzt == "0" or blzt == 0) or "审核中" in blztmc:
                return JJZStatusEnum.PENDING.value
            else:
                return JJZStatusEnum.INVALID.value

        except Exception as e:
            logging.warning(f"确定进京证状态失败: {e}")
            return JJZStatusEnum.INVALID.value

    @with_error_handling(
        exceptions=(APIError, NetworkError, ConfigurationError, Exception),
        service_name="jjz_service",
        default_return=None,
        recovery_config={"max_attempts": 2, "delay": 1.0},
    )
    async def get_jjz_status(self, plate: str) -> JJZStatus:
        """获取进京证状态 - 每次运行主流程时都重新查询"""
        start_time = time.time()

        try:
            # 记录开始查询
            self.structured_logger.log_structured(
                level=logging.INFO,
                message=f"开始查询进京证状态",
                category=LogCategory.BUSINESS,
                plate_number=plate,
                operation="get_jjz_status",
            )

            # 每次运行主流程时都从API获取最新数据
            status = await self._fetch_from_api(plate)

            duration_ms = round((time.time() - start_time) * 1000, 2)
            success = status.status != JJZStatusEnum.ERROR.value

            # 查询成功后缓存数据，供推送和后续其他操作使用
            if success:
                await self._cache_status(status)

            # 记录业务操作结果
            self.structured_logger.log_business_operation(
                operation="get_jjz_status",
                plate_number=plate,
                success=success,
                duration_ms=duration_ms,
                extra_data={
                    "status": status.status,
                    "data_source": status.data_source,
                    "has_error": bool(status.error_message),
                },
            )

            return status

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # 记录失败的业务操作
            self.structured_logger.log_business_operation(
                operation="get_jjz_status",
                plate_number=plate,
                success=False,
                duration_ms=duration_ms,
                extra_data={"error": str(e), "error_type": type(e).__name__},
            )

            logging.error(f"获取进京证状态失败: plate={plate}, error={e}")
            return JJZStatus(
                plate=plate, status="error", error_message=str(e), data_source="api"
            )

    async def _query_multiple_status(self, plates: List[str]) -> Tuple[
        Dict[str, JJZStatus],
        Dict[str, Tuple[Dict[str, Any], "JJZAccount", JJZStatus, bool, bool]],
    ]:
        """
        内部实现：返回 (results, plate_contexts)。
        plate_contexts 按车牌记录续办专用五元组
        (response_data, account, renew_status, today_covered, tomorrow_covered)：
        - renew_status 仅取该车牌六环外记录中 apply_time 最新的一条
        - today_covered / tomorrow_covered 基于该车牌全部记录（六环内 ∪ 六环外）
          通过 `_is_effective_on` 计算，覆盖判定包含"生效中"与"已批准待生效"
        若车牌无六环外记录则不写入 plate_contexts（无 vId 等续办字段，无法 auto_renew）。
        多账户场景下保证后续续办派发使用正确账户与正确的六环外 status。
        """
        results = {plate: None for plate in plates}
        accounts = self.load_accounts()
        plate_contexts: Dict[
            str, Tuple[Dict[str, Any], JJZAccount, JJZStatus, bool, bool]
        ] = {}

        if not accounts:
            for plate in plates:
                results[plate] = JJZStatus(
                    plate=plate,
                    status="error",
                    error_message="未配置进京证账户",
                    data_source="api",
                )
            return results, plate_contexts

        # 同车牌可能出现在多账户里，记录三元组以便后续按 latest 同步选择正确账户
        plate_statuses: Dict[
            str, List[Tuple[JJZStatus, Dict[str, Any], JJZAccount]]
        ] = {plate: [] for plate in plates}

        for account in accounts:
            try:
                logging.debug(f"使用账户 {account.name} 查询所有进京证数据")

                response_data = self.check_jjz_status(
                    account.jjz.url, account.jjz.token
                )
                if "error" in response_data:
                    logging.warning(
                        f"账户 {account.name} 查询失败: {response_data['error']}"
                    )
                    continue

                all_records = parse_all_jjz_records(
                    response_data, self._determine_status, JJZStatus
                )

                for record in all_records:
                    for plate in plates:
                        if record.plate.upper() == plate.upper():
                            plate_statuses[plate].append(
                                (record, response_data, account)
                            )

            except Exception as e:
                logging.warning(f"账户 {account.name} 查询失败: {e}")
                continue

        today = date.today()
        tomorrow = today + timedelta(days=1)

        for plate in plates:
            triples = plate_statuses[plate]
            if triples:
                # 推送/显示用：所有记录中 apply_time 最新的一条
                latest_record, latest_response, latest_account = max(
                    triples, key=lambda t: t[0].apply_time or ""
                )
                results[plate] = latest_record

                if latest_record.status != JJZStatusEnum.ERROR.value:
                    await self._cache_status(latest_record)

                # 续办用：仅从六环外记录中选最新一条；无六环外则不写入 plate_contexts
                outer_triples = [
                    t for t in triples if t[0].jjzzlmc and "六环外" in t[0].jjzzlmc
                ]
                if outer_triples:
                    renew_record, renew_response, renew_account = max(
                        outer_triples, key=lambda t: t[0].apply_time or ""
                    )
                    # 覆盖信号基于全部记录（六环内 ∪ 六环外）；任意一条覆盖目标日即认为覆盖
                    today_covered = any(
                        _is_effective_on(t[0], today) for t in triples
                    )
                    tomorrow_covered = any(
                        _is_effective_on(t[0], tomorrow) for t in triples
                    )
                    plate_contexts[plate] = (
                        renew_response,
                        renew_account,
                        renew_record,
                        today_covered,
                        tomorrow_covered,
                    )
            else:
                results[plate] = JJZStatus(
                    plate=plate,
                    status="invalid",
                    error_message="未找到匹配车牌的记录",
                    data_source="api",
                )

        return results, plate_contexts

    @with_error_handling(
        exceptions=(APIError, NetworkError, ConfigurationError, Exception),
        service_name="jjz_service",
        default_return={},
        recovery_config={"max_attempts": 2, "delay": 1.0},
    )
    async def get_multiple_status_optimized(
        self, plates: List[str]
    ) -> Dict[str, JJZStatus]:
        """优化的批量获取多个车牌的进京证状态 - 减少API调用次数"""
        results, _ = await self._query_multiple_status(plates)
        return results

    @with_error_handling(
        exceptions=(APIError, NetworkError, ConfigurationError, Exception),
        service_name="jjz_service",
        default_return=({}, {}),
        recovery_config={"max_attempts": 2, "delay": 1.0},
    )
    async def get_multiple_status_with_context(self, plates: List[str]) -> Tuple[
        Dict[str, JJZStatus],
        Dict[str, Tuple[Dict[str, Any], "JJZAccount", JJZStatus, bool, bool]],
    ]:
        """返回每个车牌对应的续办上下文五元组
        ``(response_data, account, renew_status, today_covered, tomorrow_covered)``。

        ``renew_status`` 仅取该车牌六环外记录中 apply_time 最新的一条；若无六环外
        记录则不写入。``today_covered`` / ``tomorrow_covered`` 基于该车牌全部记录
        （六环内 ∪ 六环外）的覆盖判定结果。
        """
        return await self._query_multiple_status(plates)

    @with_retry(max_attempts=3, delay=1.0)
    async def _fetch_from_api(self, plate: str) -> JJZStatus:
        """从API获取进京证状态"""
        accounts = self.load_accounts()

        if not accounts:
            error = APIError("未配置进京证账户", details={"plate": plate})
            await handle_critical_error(error, f"获取车牌{plate}的进京证状态")
            return JJZStatus(
                plate=plate,
                status="error",
                error_message="未配置进京证账户",
                data_source="api",
            )

        # 查询所有账户，收集所有数据
        all_statuses = []
        last_error = None
        all_accounts_failed = True

        for account in accounts:
            try:
                logging.debug(f"使用账户 {account.name} 查询所有进京证数据")

                response_data = self.check_jjz_status(
                    account.jjz.url, account.jjz.token
                )
                if "error" in response_data:
                    last_error = response_data["error"]
                    error_msg = response_data["error"]
                    logging.warning(f"账户 {account.name} 查询失败: {error_msg}")

                    # 检查是否为Token错误，需要通知管理员
                    if is_token_error(Exception(error_msg)):
                        token_error = APIError(
                            f"账户 {account.name} Token可能已失效: {error_msg}",
                            details={"account": account.name, "plate": plate},
                        )
                        await handle_critical_error(
                            token_error, f"查询车牌{plate}进京证状态"
                        )
                    continue

                all_accounts_failed = False

                # 解析所有进京证数据
                all_records = parse_all_jjz_records(
                    response_data, self._determine_status, JJZStatus
                )

                # 查找匹配的车牌
                for record in all_records:
                    if record.plate.upper() == plate.upper():
                        all_statuses.append(record)

            except Exception as e:
                last_error = str(e)
                logging.warning(f"账户 {account.name} 查询失败: {e}")
                continue

        # 如果找到了匹配的记录，返回最新的
        if all_statuses:
            # 按申请时间排序，返回最新的
            latest_status = max(all_statuses, key=lambda s: s.apply_time or "")
            return latest_status

        # 如果所有账户都失败了，返回错误状态
        if all_accounts_failed and last_error:
            return JJZStatus(
                plate=plate, status="error", error_message=last_error, data_source="api"
            )

        # 没有找到匹配的记录
        return JJZStatus(
            plate=plate,
            status="invalid",
            error_message="未找到匹配车牌的记录",
            data_source="api",
        )

    async def _cache_status(self, status: JJZStatus) -> bool:
        """缓存进京证状态"""
        try:
            cache_data = status.to_dict()
            cache_data["cached_at"] = datetime.now().isoformat()

            success = await self.cache_service.cache_jjz_data(status.plate, cache_data)
            return success

        except Exception as e:
            logging.error(f"缓存进京证状态失败: plate={status.plate}, error={e}")
            return False

    async def get_multiple_status(self, plates: List[str]) -> Dict[str, JJZStatus]:
        """批量获取多个车牌的进京证状态"""
        results = {}

        for plate in plates:
            try:
                status = await self.get_jjz_status(plate)
                results[plate] = status
            except Exception as e:
                logging.error(f"获取车牌 {plate} 状态失败: {e}")
                results[plate] = JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.ERROR.value,
                    error_message=str(e),
                    data_source="api",
                )

        return results

    async def refresh_cache(self, plate: str) -> JJZStatus:
        """强制刷新指定车牌的缓存"""
        try:
            # 先删除旧缓存
            await self.cache_service.delete_jjz_data(plate)

            # 重新获取
            return await self.get_jjz_status(plate)

        except Exception as e:
            logging.error(f"刷新缓存失败: plate={plate}, error={e}")
            return JJZStatus(
                plate=plate, status="error", error_message=str(e), data_source="api"
            )

    async def get_cached_plates(self) -> List[str]:
        """获取所有已缓存的车牌号"""
        try:
            return await self.cache_service.get_all_jjz_plates()
        except Exception as e:
            logging.error(f"获取缓存车牌列表失败: {e}")
            return []

    async def check_expiring_permits(self, days_threshold: int = 3) -> List[JJZStatus]:
        """检查即将过期的进京证"""
        try:
            cached_plates = await self.get_cached_plates()
            expiring_permits = []

            for plate in cached_plates:
                status = await self.get_jjz_status(plate)

                if (
                    status.status == "valid"
                    and status.days_remaining is not None
                    and status.days_remaining <= days_threshold
                ):
                    expiring_permits.append(status)

            return expiring_permits

        except Exception as e:
            logging.error(f"检查即将过期的进京证失败: {e}")
            return []

    async def get_service_status(self) -> Dict[str, Any]:
        """获取JJZ服务状态"""
        try:
            accounts = self.load_accounts()
            cached_plates = await self.get_cached_plates()

            # 检查缓存统计
            cache_stats = await self.cache_service.get_cache_stats(days=1)
            jjz_stats = cache_stats.get("jjz", {})

            return {
                "service": "JJZService",
                "status": "healthy",
                "accounts_count": len(accounts),
                "cached_plates_count": len(cached_plates),
                "cached_plates": cached_plates,
                "cache_stats": {
                    "hits": jjz_stats.get("total_hits", 0),
                    "misses": jjz_stats.get("total_misses", 0),
                    "hit_rate": jjz_stats.get("hit_rate", 0.0),
                },
                "last_config_load": (
                    self._last_config_load.isoformat()
                    if self._last_config_load
                    else None
                ),
            }

        except Exception as e:
            logging.error(f"获取JJZ服务状态失败: {e}")
            return {"service": "JJZService", "status": "error", "error": str(e)}

    async def _notify_admin_system_error(self, error_type: str, error_msg: str):
        """
        通知管理员系统级错误

        Args:
            error_type: 错误类型
            error_msg: 错误信息
        """
        try:
            from jjz_alert.service.notification.push_helpers import (
                push_admin_notification,
            )
            from jjz_alert.service.notification.push_priority import PushPriority

            # 构建通知消息
            title = "🚨 进京证查询系统错误"
            message = f"""
🔧 服务: 进京证查询服务
❌ 错误类型: {error_type}
📝 错误详情: {error_msg}
⏰ 发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
💡 建议: 请检查系统配置和服务器状态
🔄 处理: 已跳过用户推送，仅通知管理员
            """.strip()

            # 直接使用全局管理员配置发送通知
            await push_admin_notification(
                title=title,
                message=message,
                priority=PushPriority.HIGH,
                category="system_error",
            )

            logging.info(f"已向管理员发送系统错误通知: {error_type}")

        except Exception as e:
            logging.error(f"发送管理员系统错误通知失败: {e}")

    async def _notify_admin_network_error(self, error_type: str, error_msg: str):
        """
        通知管理员网络错误（保留向后兼容）

        Args:
            error_type: 错误类型
            error_msg: 错误信息
        """
        # 调用系统错误通知函数
        await self._notify_admin_system_error(error_type, error_msg)


# 全局JJZ服务实例
jjz_service = JJZService()
