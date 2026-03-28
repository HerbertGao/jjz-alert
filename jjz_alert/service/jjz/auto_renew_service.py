"""
六环外进京证自动续办服务

在到期前一天自动提交续办申请，支持随机时间调度和结果通知。
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from jjz_alert.base.error_handler import is_token_error
from jjz_alert.base.http import http_post
from jjz_alert.base.logger import get_structured_logger, LogCategory
from jjz_alert.config.config_models import AutoRenewConfig, PlateConfig
from jjz_alert.service.jjz.jjz_parse import (
    extract_renew_metadata,
    parse_all_jjz_records,
)
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.jjz_status_enum import JJZStatusEnum

logger = logging.getLogger(__name__)


@dataclass
class RenewResult:
    """续办结果"""

    plate: str
    success: bool
    message: str
    step: str = ""
    jjrq: Optional[str] = None


class AutoRenewService:
    """六环外进京证自动续办服务"""

    def __init__(self):
        self.structured_logger = get_structured_logger("auto_renew")

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    async def execute_renew(
        self,
        plate_config: PlateConfig,
        jjz_status: JJZStatus,
        response_data: Dict[str, Any],
    ) -> RenewResult:
        """
        对单个车牌执行续办流程

        Args:
            plate_config: 车牌配置（含 auto_renew 配置）
            jjz_status: 当前进京证状态（含 vId 等车辆字段）
            response_data: stateList 原始响应（用于提取元数据）
        """
        plate = plate_config.plate
        ar_config = plate_config.auto_renew
        start_time = time.time()

        self.structured_logger.log_structured(
            level=logging.INFO,
            message="开始执行自动续办",
            category=LogCategory.BUSINESS,
            plate_number=plate,
            operation="auto_renew",
        )

        try:
            # 获取账户 token 和 base_url
            token, base_url = self._get_account_info()
            if not token:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message="未找到可用的进京证账户",
                    step="init",
                )

            # 防重复：检查 Redis 当日记录
            if await self._has_renewed_today(plate):
                return RenewResult(
                    plate=plate,
                    success=True,
                    message="当日已提交续办，自动跳过",
                    step="dedup_skip",
                )

            # 校验必需的车辆字段
            if not jjz_status.vId:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message="缺少车辆标识(vId)，无法续办",
                    step="validate_fields",
                )

            # ① 车辆校验
            result = self._vehicle_check(
                base_url, token, jjz_status.plate, jjz_status.hpzl or "02"
            )
            if not result:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"车辆校验失败: {self._last_api_error}",
                    step="vehicle_check",
                )

            # ② 获取驾驶人信息
            driver_info = self._get_driver_info(base_url, token)
            if not driver_info:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"获取驾驶人信息失败: {self._last_api_error}",
                    step="get_driver_info",
                )

            # ③ 驾驶人校验
            result = self._driver_check(base_url, token, driver_info)
            if not result:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"驾驶人校验失败: {self._last_api_error}",
                    step="driver_check",
                )

            # ④ 获取可选进京日期
            handle_data = self._check_handle(
                base_url, token, jjz_status.vId, jjz_status.plate
            )
            if not handle_data or not handle_data.get("jjrqs"):
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"当前无可选进京日期: {self._last_api_error}",
                    step="check_handle",
                )

            # ⑤ 检查是否需填行驶路线
            road_ok = self._check_road_info(base_url, token, jjz_status.vId)
            if not road_ok:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"行驶路线校验失败: {self._last_api_error}",
                    step="check_road_info",
                )

            # ⑥ 组装并提交申请
            jjrq = handle_data["jjrqs"][0]
            metadata = extract_renew_metadata(response_data)
            request_body = self._build_apply_request(
                jjz_status, ar_config, driver_info, jjrq, metadata
            )

            submit_result = self._submit_apply(base_url, token, request_body)
            if not submit_result:
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"提交续办申请失败: {self._last_api_error}",
                    step="submit_apply",
                )

            # 记录 Redis 防重复
            await self._mark_renewed_today(plate)

            duration_ms = round((time.time() - start_time) * 1000, 2)
            self.structured_logger.log_business_operation(
                operation="auto_renew",
                plate_number=plate,
                success=True,
                duration_ms=duration_ms,
                extra_data={"jjrq": jjrq},
            )

            return RenewResult(
                plate=plate,
                success=True,
                message=f"续办申请已提交，进京日期 {jjrq}，等待审核",
                step="done",
                jjrq=jjrq,
            )

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            self.structured_logger.log_business_operation(
                operation="auto_renew",
                plate_number=plate,
                success=False,
                duration_ms=duration_ms,
                extra_data={"error": str(e)},
            )
            return RenewResult(
                plate=plate,
                success=False,
                message=f"续办异常: {e}",
                step="exception",
            )

    # ------------------------------------------------------------------
    # 续办判断
    # ------------------------------------------------------------------

    def should_renew(self, plate_config: PlateConfig, jjz_status: JJZStatus) -> bool:
        """判断是否应触发续办"""
        ar = plate_config.auto_renew
        if not ar or not ar.enabled:
            return False

        # 仅六环外
        if jjz_status.jjzzlmc and "六环外" not in jjz_status.jjzzlmc:
            return False

        # 已有待审记录
        if jjz_status.sfyecbzxx:
            logger.info(f"车牌 {plate_config.plate} 已有待审记录，跳过续办")
            return False

        # 注意：elzsfkb 的检查由调用方处理，以便在不可办理时推送通知

        # 判断有效期：明天到期或已过期
        if jjz_status.valid_end:
            try:
                end_date = datetime.strptime(jjz_status.valid_end, "%Y-%m-%d").date()
                today = date.today()
                tomorrow = today + timedelta(days=1)

                if end_date <= tomorrow:
                    return True
            except (ValueError, TypeError):
                pass

        # 状态为过期
        if jjz_status.status == JJZStatusEnum.EXPIRED.value:
            return True

        return False

    # ------------------------------------------------------------------
    # API 调用链
    # ------------------------------------------------------------------

    def _get_account_info(self):
        """获取第一个可用账户的 token 和 base_url"""
        try:
            from jjz_alert.config.config import config_manager

            app_config = config_manager.load_config()
            if not app_config.jjz_accounts:
                return None, None
            account = app_config.jjz_accounts[0]
            # 从 stateList URL 中提取 base_url
            url = account.jjz.url
            # url 形如 https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList
            # 提取到 /pro 之前的部分
            idx = url.find("/pro")
            base_url = url[:idx] if idx != -1 else url.rsplit("/", 2)[0]
            return account.jjz.token, base_url
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return None, None

    def _api_call(
        self, base_url: str, token: str, path: str, json_data: Dict = None
    ) -> Optional[Dict]:
        """通用 API 调用，返回 code==200 时的完整响应，失败时将错误信息存入 _last_api_error"""
        url = f"{base_url}{path}"
        headers = {"Authorization": token, "Content-Type": "application/json"}
        self._last_api_error = ""
        try:
            resp = http_post(url, headers=headers, json_data=json_data or {})
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                msg = data.get("msg", "")
                self._last_api_error = f"code={data.get('code')}, msg={msg}"
                logger.warning(f"API {path} 返回非200: {data}")
                return None
            return data
        except Exception as e:
            self._last_api_error = str(e)
            logger.error(f"API {path} 调用失败: {e}")
            return None

    def _vehicle_check(self, base_url: str, token: str, hphm: str, hpzl: str) -> bool:
        result = self._api_call(
            base_url,
            token,
            "/pro/applyRecordController/applyVehicleCheck",
            {"hphm": hphm, "hpzl": hpzl},
        )
        return result is not None

    def _get_driver_info(self, base_url: str, token: str) -> Optional[Dict[str, str]]:
        result = self._api_call(base_url, token, "/pro/applyRecordController/getJsrxx")
        if result and result.get("data"):
            return result["data"]
        return None

    def _driver_check(
        self, base_url: str, token: str, driver_info: Dict[str, str]
    ) -> bool:
        result = self._api_call(
            base_url,
            token,
            "/pro/applyRecordController/applyCheckNum",
            {
                "jsrxm": driver_info.get("jsrxm", ""),
                "jszh": driver_info.get("jszh", ""),
                "dabh": driver_info.get("dabh", ""),
                "txrxx": [],
                "txrkg": "0",
                "wtxr": "",
            },
        )
        return result is not None

    def _check_handle(
        self, base_url: str, token: str, vId: str, hphm: str
    ) -> Optional[Dict]:
        result = self._api_call(
            base_url,
            token,
            "/pro/applyRecordController/checkHandle",
            {"vId": vId, "jjzzl": "02", "hphm": hphm},
        )
        if result:
            return result.get("data")
        return None

    def _check_road_info(self, base_url: str, token: str, vId: str) -> bool:
        result = self._api_call(
            base_url,
            token,
            "/pro/applyRecordController/checkInputRoadInfo",
            {"vId": vId},
        )
        return result is not None

    # ------------------------------------------------------------------
    # 请求体组装
    # ------------------------------------------------------------------

    def _build_apply_request(
        self,
        jjz_status: JJZStatus,
        ar_config: AutoRenewConfig,
        driver_info: Dict[str, str],
        jjrq: str,
        metadata: Dict[str, str],
    ) -> Dict[str, Any]:
        """组装 insertApplyRecord 请求体"""
        dest = ar_config.destination
        accom = ar_config.accommodation
        loc = ar_config.apply_location

        return {
            # stateList 中的车辆信息
            "vId": jjz_status.vId or "",
            "hphm": jjz_status.plate,
            "hpzl": jjz_status.hpzl or "02",
            "ylzsfkb": jjz_status.ylzsfkb if jjz_status.ylzsfkb is not None else True,
            "elzsfkb": jjz_status.elzsfkb if jjz_status.elzsfkb is not None else True,
            "elzqyms": metadata.get("elzqyms", ""),
            "ylzqyms": metadata.get("ylzqyms", ""),
            "elzmc": metadata.get("elzmc", ""),
            "ylzmc": metadata.get("ylzmc", ""),
            "cllx": jjz_status.cllx or "01",
            # 固定六环外
            "jjzzl": "02",
            # 驾驶人信息
            "jsrxm": driver_info.get("jsrxm", ""),
            "jszh": driver_info.get("jszh", ""),
            "dabh": driver_info.get("dabh", ""),
            # 同行人（空）
            "txrxx": [],
            # 进京日期
            "jjrq": jjrq,
            # 用户配置的目的地信息
            "area": dest.area,
            "jjdq": dest.area_code,
            "xxdz": dest.address,
            "jjdzgdjd": dest.lng,
            "jjdzgdwd": dest.lat,
            # 进京目的
            "jjmd": ar_config.purpose,
            "jjmdmc": ar_config.purpose_name,
            # 申请地坐标
            "sqdzgdjd": loc.lng,
            "sqdzgdwd": loc.lat,
            # 住宿
            "sfzj": "1" if accom.enabled else "0",
            "zjxxdz": accom.address if accom.enabled else "",
            "zjxxdzgdjd": accom.lng if accom.enabled else "",
            "zjxxdzgdwd": accom.lat if accom.enabled else "",
            # 进京状态和路口（空）
            "jingState": "",
            "jjlk": "",
            "jjlkmc": "",
            "jjlkgdjd": "",
            "jjlkgdwd": "",
        }

    def _submit_apply(self, base_url: str, token: str, request_body: Dict) -> bool:
        result = self._api_call(
            base_url,
            token,
            "/pro/applyRecordController/insertApplyRecord",
            request_body,
        )
        return result is not None

    # ------------------------------------------------------------------
    # Redis 防重复
    # ------------------------------------------------------------------

    async def _has_renewed_today(self, plate: str) -> bool:
        try:
            from jjz_alert.config.redis.operations import redis_get

            key = f"auto_renew:{plate}:{date.today().isoformat()}"
            val = await redis_get(key)
            return val is not None
        except Exception:
            return False

    async def _mark_renewed_today(self, plate: str):
        try:
            from jjz_alert.config.redis.operations import redis_set

            key = f"auto_renew:{plate}:{date.today().isoformat()}"
            await redis_set(key, "1", ttl=86400)
        except Exception as e:
            logger.warning(f"写入续办防重复记录失败: {e}")

    # ------------------------------------------------------------------
    # 通知
    # ------------------------------------------------------------------

    async def push_renew_result(self, plate_config: PlateConfig, result: RenewResult):
        """推送续办结果通知"""
        from jjz_alert.base.message_templates import template_manager
        from jjz_alert.service.notification.push_priority import PushPriority
        from jjz_alert.service.notification.unified_pusher import unified_pusher

        display_name = plate_config.display_name or plate_config.plate

        if result.success:
            title = "进京证自动续办成功"
            body = template_manager.format_message(
                "renew_success",
                display_name=display_name,
                jjrq=result.jjrq or "",
            )
            priority = PushPriority.NORMAL
        else:
            # 判断是否为 Token 失效
            is_token_err = False
            try:
                is_token_err = is_token_error(Exception(result.message))
            except Exception:
                pass

            if is_token_err:
                title = "进京证续办失败 - Token已失效"
                body = template_manager.format_message(
                    "renew_token_expired",
                    display_name=display_name,
                )
            else:
                title = "进京证自动续办失败"
                body = template_manager.format_message(
                    "renew_failure",
                    display_name=display_name,
                    step=result.step,
                    reason=result.message,
                )
            priority = PushPriority.HIGH

        for notification in plate_config.notifications:
            try:
                await unified_pusher.push(
                    notification_config=notification,
                    title=title,
                    body=body,
                    priority=priority,
                    plate=plate_config.plate,
                    icon=plate_config.icon,
                )
            except Exception as e:
                logger.error(f"续办结果推送失败: {e}")

    # ------------------------------------------------------------------
    # 随机延迟
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_random_delay(
        time_window_start: str = "00:00", time_window_end: str = "06:00"
    ) -> int:
        """计算从当前时刻到时间窗口内随机时刻的等待秒数"""
        start_parts = list(map(int, time_window_start.split(":")))
        end_parts = list(map(int, time_window_end.split(":")))
        start_seconds = start_parts[0] * 3600 + start_parts[1] * 60
        end_seconds = end_parts[0] * 3600 + end_parts[1] * 60

        now = datetime.now()
        now_seconds = now.hour * 3600 + now.minute * 60 + now.second

        if now_seconds >= end_seconds:
            # 已超过窗口结束时间
            return 0

        # 有效随机范围的起点：窗口起始或当前时间（取较晚者）
        effective_start = max(start_seconds, now_seconds)

        # 从当前时刻到随机目标时刻的延迟
        random_target = random.randint(effective_start, end_seconds)
        return random_target - now_seconds


# 全局实例
auto_renew_service = AutoRenewService()


async def run_auto_renew_check():
    """
    自动续办检查入口 — 由定时任务调用

    流程：随机延迟 → 加载配置 → 遍历启用续办的车牌 → 查询状态 → 执行续办 → 推送结果
    """
    from jjz_alert.config.config import config_manager
    from jjz_alert.service.jjz.jjz_service import JJZService

    app_config = config_manager.load_config()
    ar_global = app_config.global_config.auto_renew

    # 找出启用了续办的车牌
    renew_plates = [
        p for p in app_config.plates if p.auto_renew and p.auto_renew.enabled
    ]
    if not renew_plates:
        logger.debug("无启用自动续办的车牌，跳过")
        return

    # 随机延迟
    delay = AutoRenewService.calculate_random_delay(
        ar_global.time_window_start, ar_global.time_window_end
    )
    if delay > 0:
        target_time = datetime.now() + timedelta(seconds=delay)
        logger.info(
            f"自动续办将在 {target_time.strftime('%H:%M:%S')} 执行 "
            f"(延迟 {delay // 60} 分钟)"
        )
        await asyncio.sleep(delay)

    logger.info(f"开始自动续办检查，共 {len(renew_plates)} 个车牌")

    jjz_service = JJZService()

    # 一次性查询所有车辆状态（stateList 返回所有车辆数据）
    accounts = jjz_service._load_accounts()
    if not accounts:
        logger.error("无可用进京证账户")
        return

    response_data = jjz_service._check_jjz_status(
        accounts[0].jjz.url, accounts[0].jjz.token
    )
    if not response_data or "error" in response_data:
        logger.warning("查询进京证状态失败，跳过自动续办")
        return

    all_records = parse_all_jjz_records(
        response_data, jjz_service._determine_status, JJZStatus
    )

    for plate_config in renew_plates:
        plate = plate_config.plate
        try:
            # 从已解析的记录中找到匹配车牌的六环外最新记录
            target_record = None
            for record in all_records:
                if record.plate.upper() == plate.upper():
                    if record.jjzzlmc and "六环外" in record.jjzzlmc:
                        if target_record is None or (record.apply_time or "") > (
                            target_record.apply_time or ""
                        ):
                            target_record = record

            if not target_record:
                logger.info(f"车牌 {plate} 未找到六环外进京证记录")
                continue

            # 六环外不可办理时发通知（在 should_renew 之前检查，避免不可达）
            if target_record.elzsfkb is False:
                await auto_renew_service.push_renew_result(
                    plate_config,
                    RenewResult(
                        plate=plate,
                        success=False,
                        message="六环外进京证当前不可办理",
                        step="eligibility_check",
                    ),
                )
                continue

            # 判断是否需要续办
            if not auto_renew_service.should_renew(plate_config, target_record):
                logger.info(f"车牌 {plate} 不满足续办条件，跳过")
                continue

            # 执行续办
            renew_result = await auto_renew_service.execute_renew(
                plate_config, target_record, response_data
            )

            # 推送结果
            await auto_renew_service.push_renew_result(plate_config, renew_result)

            logger.info(
                f"车牌 {plate} 续办{'成功' if renew_result.success else '失败'}: "
                f"{renew_result.message}"
            )

        except Exception as e:
            logger.error(f"车牌 {plate} 自动续办异常: {e}")
            await auto_renew_service.push_renew_result(
                plate_config,
                RenewResult(
                    plate=plate,
                    success=False,
                    message=f"续办异常: {e}",
                    step="exception",
                ),
            )
