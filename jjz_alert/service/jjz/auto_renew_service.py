"""
六环外进京证自动续办服务

封装续办 API 调用链、请求体组装、结果通知和当日防重。
触发由 `renew_trigger.schedule_renew` 派发，决策由 `renew_decider.decide` 给出。
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from jjz_alert.base.http import http_post
from jjz_alert.base.logger import get_structured_logger, LogCategory
from jjz_alert.config.config_models import AutoRenewConfig, PlateConfig
from jjz_alert.service.jjz.jjz_parse import extract_renew_metadata
from jjz_alert.service.jjz.jjz_status import JJZStatus

logger = logging.getLogger(__name__)


@dataclass
class RenewResult:
    """续办结果

    三态语义：
      success=True,  skipped=False → 成功（推"已提交，等待审核"）
      success=False, skipped=False → 失败（推失败原因，含 NOT_AVAILABLE / Token / API 链异常）
      success=False, skipped=True  → 静默跳过（写防重 key、不推送、记 INFO 日志）
    """

    plate: str
    success: bool
    message: str
    step: str = ""
    jjrq: Optional[str] = None
    skipped: bool = False


class AutoRenewService:
    """六环外进京证自动续办服务"""

    def __init__(self):
        self.structured_logger = get_structured_logger("auto_renew")
        self._last_api_error = ""

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    async def execute_renew(
        self,
        plate_config: PlateConfig,
        jjz_status: JJZStatus,
        response_data: Dict[str, Any],
        accounts=None,
        *,
        today_covered: bool,
        tomorrow_covered: bool,
    ) -> RenewResult:
        """
        对单个车牌执行续办流程

        Args:
            plate_config: 车牌配置（含 auto_renew 配置）
            jjz_status: 当前进京证状态（含 vId 等车辆字段）
            response_data: stateList 原始响应（用于提取元数据）
            accounts: 进京证账户列表（避免重复加载配置）
            today_covered: 该车牌今天是否已有任意进京证覆盖（用于 jjrqs useful 过滤）
            tomorrow_covered: 该车牌明天是否已有任意进京证覆盖（用于 jjrqs useful 过滤）

        Note:
            `today_covered` / `tomorrow_covered` 必传（无默认值），与 `decide()` 的
            keyword-only 强制理由一致：遗漏会静默走"无覆盖"路径，潜在错误难以发现，
            因此让 Python 在调用时立刻 TypeError 而非默认 False 静默错路径。
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
            token, base_url = self.extract_account_info(accounts)
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
                # 服务端啥都不给——视为异常，告警让人工看
                return RenewResult(
                    plate=plate,
                    success=False,
                    message=f"当前无可选进京日期: {self._last_api_error}",
                    step="check_handle",
                )

            # useful 过滤：只取实际填补覆盖缺口的日期
            today = date.today()
            tomorrow = today + timedelta(days=1)
            raw_jjrqs = handle_data["jjrqs"]
            useful = self._filter_useful(
                raw_jjrqs, today_covered, tomorrow_covered, today, tomorrow
            )
            if not useful:
                # useful=[] 有两种成因，必须区分：
                #   ① 原始 jjrqs 至少有一个合法日期但都已被本地覆盖 → 静默 SKIP，写防重
                #   ② 原始 jjrqs 全部无法解析（服务端数据异常）→ 告警，不写防重
                duration_ms = round((time.time() - start_time) * 1000, 2)
                if not self._has_parseable_date(raw_jjrqs):
                    logger.warning(
                        "[renew] checkHandle returned unparseable jjrqs plate=%s "
                        "jjrqs_sample=%s jjrqs_total=%d",
                        plate,
                        raw_jjrqs[:5],
                        len(raw_jjrqs),
                    )
                    self.structured_logger.log_business_operation(
                        operation="auto_renew",
                        plate_number=plate,
                        success=False,
                        duration_ms=duration_ms,
                        extra_data={
                            "step": "check_handle",
                            "reason": "unparseable_jjrqs",
                            # 截断防日志膨胀；服务端理论可返回任意长度
                            "jjrqs_sample": raw_jjrqs[:5],
                            "jjrqs_total": len(raw_jjrqs),
                        },
                    )
                    return RenewResult(
                        plate=plate,
                        success=False,
                        message=f"服务端返回的进京日期格式异常: {raw_jjrqs}",
                        step="check_handle",
                    )
                # ① 服务端给的日期全部被本地覆盖（典型场景：明天有待生效进京证）
                logger.info(
                    "[renew] silently skipped plate=%s reason=jjrqs_all_covered "
                    "jjrqs_sample=%s jjrqs_total=%d today_cov=%s tomorrow_cov=%s",
                    plate,
                    raw_jjrqs[:5],
                    len(raw_jjrqs),
                    today_covered,
                    tomorrow_covered,
                )
                self.structured_logger.log_business_operation(
                    operation="auto_renew",
                    plate_number=plate,
                    success=False,
                    duration_ms=duration_ms,
                    extra_data={
                        "step": "useful_filter_skip",
                        "skipped": True,
                        "reason": "jjrqs_all_covered",
                        # 截断防日志膨胀；服务端理论可返回任意长度
                        "jjrqs_sample": raw_jjrqs[:5],
                        "jjrqs_total": len(raw_jjrqs),
                        "today_covered": today_covered,
                        "tomorrow_covered": tomorrow_covered,
                    },
                )
                await self._mark_renewed_today(plate)
                return RenewResult(
                    plate=plate,
                    success=False,
                    message="服务端可办日期已被本地覆盖，无需续办",
                    step="useful_filter_skip",
                    skipped=True,
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
            jjrq = useful[0]
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
    # API 调用链
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_useful(
        jjrqs: List[str],
        today_covered: bool,
        tomorrow_covered: bool,
        today: date,
        tomorrow: date,
    ) -> List[str]:
        """从服务端返回的可办日期列表中过滤出"实际填补覆盖缺口"的日期。

        规则：
          - 等于今天且今天未覆盖 → 保留（填补今日断档）
          - 等于明天且明天未覆盖 → 保留（填补明日断档）
          - 晚于明天且明天未覆盖 → 保留（服务端给的连续段能覆盖明日起的真空）
          - 其它（已被覆盖、解析失败）→ 丢弃

        注意：本方法静默丢弃无法解析的日期。调用方在 useful=[] 时还需通过
        `_has_parseable_date` 区分"全部已被本地覆盖（静默 SKIP）"与"原始数据
        全部无法解析（服务端异常应告警）"两种语义。
        """
        useful: List[str] = []
        for d_str in jjrqs:
            try:
                d = date.fromisoformat(d_str)
            except (TypeError, ValueError):
                continue
            if d == today and not today_covered:
                useful.append(d_str)
            elif d == tomorrow and not tomorrow_covered:
                useful.append(d_str)
            elif d > tomorrow and not tomorrow_covered:
                useful.append(d_str)
        return useful

    @staticmethod
    def _has_parseable_date(jjrqs: List[str]) -> bool:
        """判断 jjrqs 中是否至少有一个能解析为合法日期的元素。

        用于在 useful=[] 时区分"日期合法但都已被覆盖"（应静默 SKIP + 写防重）
        与"日期格式全部异常"（应告警 + 不写防重）。
        """
        for d_str in jjrqs:
            try:
                date.fromisoformat(d_str)
                return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def extract_account_info(accounts) -> tuple:
        """从账户列表中提取第一个可用账户的 token 和 base_url"""
        if not accounts:
            return None, None
        account = accounts[0]
        url = account.jjz.url
        idx = url.find("/pro")
        if idx != -1:
            base_url = url[:idx]
        else:
            # fallback: 提取 scheme://host:port
            from urllib.parse import urlparse

            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        return account.jjz.token, base_url

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
        if not self._last_api_error:
            self._last_api_error = "API返回200但data为空"
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
            data = result.get("data")
            if not data:
                self._last_api_error = "API返回200但data为空"
            return data
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
            from jjz_alert.config.redis.operations import redis_ops

            key = f"auto_renew:{plate}:{date.today().isoformat()}"
            val = await redis_ops.get(key)
            return val is not None
        except Exception as e:
            # 不让异常阻断续办流程，但要可见——历史上 ImportError
            # 静默吞掉造成防重失效长期未被发现
            logger.warning(f"读取续办防重复记录失败 plate={plate}: {e}")
            return False

    async def _mark_renewed_today(self, plate: str):
        try:
            from jjz_alert.config.redis.operations import redis_ops

            key = f"auto_renew:{plate}:{date.today().isoformat()}"
            await redis_ops.set(key, "1", ttl=86400)
        except Exception as e:
            logger.warning(f"写入续办防重复记录失败: {e}")

    # ------------------------------------------------------------------
    # 通知
    # ------------------------------------------------------------------

    async def push_renew_result(self, plate_config: PlateConfig, result: RenewResult):
        """推送续办结果通知（dedup 跳过 / 静默跳过时均不推送）"""
        if result.skipped:
            logger.info(
                "[renew] skipped push plate=%s step=%s reason=%s",
                result.plate,
                result.step,
                result.message,
            )
            return
        if result.step == "dedup_skip":
            logger.debug(f"车牌 {result.plate} 当日已续办，不推送通知")
            return

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
            # 判断是否为 Token 失效（直接检查错误消息中的关键词）
            token_keywords = ["token", "unauthorized", "403", "401", "认证失败", "令牌"]
            msg_lower = (result.message or "").lower()
            is_token_err = any(kw in msg_lower for kw in token_keywords)

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

        # unified_pusher.push 内部会自动遍历 plate_config.notifications，
        # 不要在外层再循环（历史代码用错了 kwarg 名 + 循环重复推送）
        try:
            await unified_pusher.push(
                plate_config=plate_config,
                title=title,
                body=body,
                priority=priority,
                icon=plate_config.icon,
            )
        except Exception as e:
            logger.error("续办结果推送失败 plate=%s: %s", plate_config.plate, e)


# 全局实例
auto_renew_service = AutoRenewService()
