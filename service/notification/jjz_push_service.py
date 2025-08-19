"""
统一的进京证推送服务模块

提供统一的进京证查询+推送流程，供定时任务、REST API、单次推送等各种场景使用
"""

import asyncio
import datetime
import logging
from typing import Dict, List, Optional, Any

from config.config_v2 import config_manager, PlateConfig
from service.cache.cache_service import CacheService
from service.jjz.jjz_service import JJZService
from service.jjz.jjz_status import JJZStatusEnum
from service.notification.push_helpers import (
    push_jjz_status,
    push_jjz_reminder,
    push_admin_notification
)
from service.notification.unified_pusher import PushPriority
from service.traffic.traffic_service import TrafficService
from utils.logger import get_structured_logger
from service.homeassistant.ha_mqtt import ha_mqtt_publisher


class JJZPushService:
    """统一的进京证推送服务"""

    def __init__(self):
        self.cache_service = CacheService()
        self.jjz_service = JJZService(self.cache_service)
        self.traffic_service = TrafficService(self.cache_service)
        self.structured_logger = get_structured_logger("jjz_push_service")

    async def execute_push_workflow(
            self,
            plate_numbers: Optional[List[str]] = None,
            force_refresh: bool = False,
            include_ha_sync: bool = True
    ) -> Dict[str, Any]:
        """
        执行统一的进京证查询+推送工作流
        
        Args:
            plate_numbers: 指定车牌号列表，如为None则推送所有配置的车牌
            force_refresh: 是否强制刷新缓存
            include_ha_sync: 是否包含HA同步
            
        Returns:
            推送结果统计信息
        """
        logging.info("开始执行统一进京证推送工作流")

        workflow_result = {
            "success": False,
            "total_plates": 0,
            "success_plates": 0,
            "failed_plates": 0,
            "plate_results": {},
            "ha_sync_result": None,
            "errors": []
        }

        try:
            # 步骤1: 加载配置
            app_config = config_manager.load_config()
            jjz_accounts = app_config.jjz_accounts
            plate_configs = app_config.plates
            admin_notifications = app_config.global_config.admin.notifications

            if not jjz_accounts:
                error_msg = "未配置任何进京证账户"
                logging.error(error_msg)
                workflow_result["errors"].append(error_msg)

                if admin_notifications:
                    await push_admin_notification(
                        plate_configs=[],
                        title="配置错误",
                        message=error_msg,
                        priority=PushPriority.HIGH
                    )
                return workflow_result

            if not plate_configs:
                error_msg = "未配置任何车牌号"
                logging.error(error_msg)
                workflow_result["errors"].append(error_msg)

                if admin_notifications:
                    await push_admin_notification(
                        plate_configs=[],
                        title="配置错误",
                        message=error_msg,
                        priority=PushPriority.HIGH
                    )
                return workflow_result

            # 步骤2: 确定要处理的车牌
            if plate_numbers:
                # 过滤出配置中存在的车牌
                plate_dict = {p.plate.upper(): p for p in plate_configs}
                target_plates = []
                missing_plates = []

                for plate in plate_numbers:
                    plate_upper = plate.upper()
                    if plate_upper in plate_dict:
                        target_plates.append(plate_dict[plate_upper])
                    else:
                        missing_plates.append(plate)

                if missing_plates:
                    error_msg = f"未找到车牌配置: {', '.join(missing_plates)}"
                    logging.warning(error_msg)
                    workflow_result["errors"].append(error_msg)

                if not target_plates:
                    error_msg = "没有有效的车牌需要处理"
                    logging.error(error_msg)
                    workflow_result["errors"].append(error_msg)
                    return workflow_result
            else:
                # 处理所有配置的车牌
                target_plates = plate_configs

            workflow_result["total_plates"] = len(target_plates)
            logging.info(f"目标车牌数量: {len(target_plates)}")

            # 步骤3: 智能预加载限行规则缓存
            logging.info("预加载限行规则缓存")
            try:
                smart_rules = await self.traffic_service.get_smart_traffic_rules()
                today_rule = smart_rules.get("target_rule")
            except Exception as e:
                logging.warning(f"预加载限行规则失败: {e}")
                today_rule = None

            # 步骤4: 批量获取进京证数据
            logging.info("批量获取进京证数据")
            configured_plates = [plate.plate for plate in target_plates]

            try:
                if force_refresh:
                    # 强制刷新：逐个删除缓存后重新获取
                    for plate in configured_plates:
                        await self.cache_service.delete_jjz_data(plate)

                # 使用优化的批量查询
                all_jjz_results = await self.jjz_service.get_multiple_status_optimized(configured_plates)

            except Exception as e:
                error_msg = f"批量查询进京证数据失败: {e}"
                logging.error(error_msg)
                workflow_result["errors"].append(error_msg)
                return workflow_result

            # 步骤5: 批量获取限行状态
            logging.info("批量获取限行状态")
            try:
                all_traffic_results = await self.traffic_service.check_multiple_plates(configured_plates)
            except Exception as e:
                logging.warning(f"批量获取限行状态失败: {e}")
                all_traffic_results = {}

            # 步骤6: 并发处理推送
            logging.info("开始并发处理推送")

            # 准备HA同步数据
            jjz_results_for_ha = {}
            traffic_results_for_ha = {}

            # 判断是否需要次日推送
            now = datetime.datetime.now()
            send_next_day = now.hour > 20 or (now.hour == 20 and now.minute >= 30)
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            tomorrow_date = datetime.date.today() + datetime.timedelta(days=1)
            tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")

            async def process_single_plate(plate_config: PlateConfig) -> Dict[str, Any]:
                """处理单个车牌的推送"""
                plate = plate_config.plate
                plate_result = {
                    "plate": plate,
                    "success": False,
                    "jjz_status": None,
                    "traffic_status": None,
                    "push_result": None,
                    "error": None
                }

                try:
                    # 获取进京证状态
                    jjz_status = all_jjz_results.get(plate)
                    if not jjz_status or jjz_status.status == JJZStatusEnum.ERROR.value:
                        error_msg = f"车牌 {plate} 进京证查询失败"
                        if jjz_status and jjz_status.error_message:
                            error_msg += f": {jjz_status.error_message}"
                        plate_result["error"] = error_msg
                        logging.error(error_msg)
                        return plate_result

                    plate_result["jjz_status"] = jjz_status.to_dict()

                    # 获取限行状态
                    traffic_result = all_traffic_results.get(plate)
                    if traffic_result:
                        plate_result["traffic_status"] = {
                            "is_limited": traffic_result.is_limited,
                            "date": traffic_result.date.isoformat() if traffic_result.date else None,
                            "tail_number": traffic_result.tail_number
                        }

                    # 执行推送逻辑
                    jjz_data = jjz_status.to_dict()

                    if not send_next_day:
                        # 当日推送
                        traffic_reminder_text = None
                        if traffic_result and getattr(traffic_result, "is_limited", False):
                            # 如果今天限行，则在正文最开始拼接提醒
                            traffic_reminder_text = "今日限行"

                        push_result = await push_jjz_status(
                            plate_config,
                            jjz_data,
                            traffic_reminder=traffic_reminder_text,
                        )
                    else:
                        # 次日推送逻辑
                        if (jjz_status.valid_start and jjz_status.valid_end and
                                jjz_status.valid_start <= tomorrow_str <= jjz_status.valid_end and
                                jjz_status.status == JJZStatusEnum.VALID.value):
                            # 次日有效，推送次日信息
                            traffic_reminder_text = None
                            try:
                                # 计算明日是否限行
                                tomorrow_limit_status = await self.traffic_service.check_plate_limited(
                                    plate, target_date=tomorrow_date
                                )
                                if tomorrow_limit_status and tomorrow_limit_status.is_limited:
                                    traffic_reminder_text = "明日限行"
                            except Exception:
                                traffic_reminder_text = None

                            push_result = await push_jjz_status(
                                plate_config, jjz_data,
                                target_date=tomorrow_date,
                                is_next_day=True,
                                traffic_reminder=traffic_reminder_text,
                            )
                        else:
                            # 次日无效或过期，发送提醒
                            if jjz_status.valid_end and jjz_status.valid_end <= today_str:
                                warn_msg = f"车牌 {plate} 明日尚未查询到进京证信息，请注意及时办理进京证。"
                                push_result = await push_jjz_reminder(
                                    plate_config, warn_msg,
                                    priority=PushPriority.HIGH
                                )
                            else:
                                push_result = {"success": True, "skipped": "no_next_day_action_needed"}

                    plate_result["push_result"] = push_result
                    # 判断推送是否成功：success_count > 0 或者包含 success=True
                    if push_result:
                        success_count = push_result.get("success_count", 0)
                        explicit_success = push_result.get("success", False)
                        plate_result["success"] = success_count > 0 or explicit_success
                    else:
                        plate_result["success"] = False

                    # 收集HA同步数据
                    if plate_result["success"]:
                        jjz_results_for_ha[plate] = jjz_status
                        if traffic_result:
                            traffic_results_for_ha[plate] = traffic_result

                    return plate_result

                except Exception as e:
                    error_msg = f"处理车牌 {plate} 时发生异常: {e}"
                    logging.error(error_msg)
                    plate_result["error"] = error_msg
                    plate_result["success"] = False
                    return plate_result

            # 并发执行所有车牌处理
            plate_tasks = [process_single_plate(plate_config) for plate_config in target_plates]
            plate_results = await asyncio.gather(*plate_tasks, return_exceptions=True)

            # 统计结果
            for result in plate_results:
                if isinstance(result, Exception):
                    workflow_result["errors"].append(f"车牌处理异常: {result}")
                    workflow_result["failed_plates"] += 1
                else:
                    plate = result["plate"]
                    workflow_result["plate_results"][plate] = result
                    if result["success"]:
                        workflow_result["success_plates"] += 1
                    else:
                        workflow_result["failed_plates"] += 1
                        if result["error"]:
                            workflow_result["errors"].append(result["error"])

            # 步骤7: HA同步
            if include_ha_sync and jjz_results_for_ha:
                logging.info(f"开始HA同步，车牌数量: {len(jjz_results_for_ha)}")
                try:
                    from service.homeassistant import sync_to_homeassistant
                    ha_sync_result = await sync_to_homeassistant(jjz_results_for_ha, traffic_results_for_ha)
                    workflow_result["ha_sync_result"] = ha_sync_result

                    if ha_sync_result:
                        success_count = ha_sync_result.get('success_plates', 0)
                        total_count = ha_sync_result.get('total_plates', 0)
                        logging.info(f"HA同步完成: {success_count}/{total_count} 车牌成功")
                except Exception as e:
                    error_msg = f"HA同步失败: {e}"
                    logging.error(error_msg)
                    workflow_result["errors"].append(error_msg)

            # 步骤8: MQTT Discovery（可选）
            try:
                if jjz_results_for_ha and ha_mqtt_publisher.enabled():
                    logging.info("开始MQTT Discovery发布")
                    for plate, jjz_status in jjz_results_for_ha.items():
                        try:
                            plate_cfg = next((p for p in plate_configs if p.plate == plate), None)
                            display_name = plate_cfg.display_name if plate_cfg and plate_cfg.display_name else plate

                            # 计算合并状态，与 HA 合并实体一致
                            traffic_status = traffic_results_for_ha.get(plate)
                            if jjz_status.status == JJZStatusEnum.VALID.value and traffic_status and traffic_status.is_limited:
                                state_str = f"限行 ({traffic_status.tail_number})"
                            elif jjz_status.status == JJZStatusEnum.VALID.value:
                                state_str = "正常通行"
                            else:
                                state_str = jjz_status.to_dict().get("status_desc_formatted", jjz_status.status)

                            # 属性与此前 REST 轮询返回结构保持一致（已移除 REST 轮询端点）
                            attrs = {
                                "friendly_name": f"{display_name} 进京证与限行状态",
                                "plate_number": plate,
                                "display_name": display_name,
                                "jjz_status": jjz_status.status,
                                "jjz_status_desc": jjz_status.to_dict().get("status_desc_formatted"),
                                "jjz_type": jjz_status.to_dict().get("jjz_type_formatted"),
                                "jjz_apply_time": jjz_status.apply_time,
                                "jjz_valid_start": jjz_status.valid_start,
                                "jjz_valid_end": jjz_status.valid_end,
                                "jjz_days_remaining": jjz_status.days_remaining,
                                "jjz_remaining_count": jjz_status.sycs,
                                "traffic_limited_today": bool(traffic_status.is_limited) if traffic_status else False,
                                "traffic_limited_today_text": "限行" if (traffic_status and traffic_status.is_limited) else "不限行",
                                "traffic_rule_desc": (traffic_status.rule.limited_numbers if (traffic_status and traffic_status.rule) else "未知"),
                                "traffic_limited_tail_numbers": (traffic_status.rule.limited_numbers if (traffic_status and traffic_status.rule) else "0"),
                                "icon": "mdi:car",
                            }

                            await ha_mqtt_publisher.publish_discovery_and_state(
                                plate_number=plate,
                                display_name=display_name,
                                state=state_str,
                                attributes=attrs,
                            )
                        except Exception as e:
                            logging.warning(f"MQTT单车牌发布失败 {plate}: {e}")
            except Exception as e:
                logging.warning(f"MQTT发布阶段异常: {e}")

            # 设置总体成功状态
            workflow_result["success"] = workflow_result["success_plates"] > 0

            logging.info(
                f"统一推送工作流完成: 成功 {workflow_result['success_plates']}/{workflow_result['total_plates']} 个车牌")

            return workflow_result

        except Exception as e:
            error_msg = f"推送工作流执行异常: {e}"
            logging.error(error_msg)
            workflow_result["errors"].append(error_msg)
            return workflow_result

    async def push_single_plate(self, plate_number: str, force_refresh: bool = False) -> Dict[str, Any]:
        """推送单个车牌（便捷方法）"""
        return await self.execute_push_workflow(
            plate_numbers=[plate_number],
            force_refresh=force_refresh,
            include_ha_sync=True
        )

    async def push_all_plates(self, force_refresh: bool = False) -> Dict[str, Any]:
        """推送所有车牌（便捷方法）"""
        return await self.execute_push_workflow(
            plate_numbers=None,
            force_refresh=force_refresh,
            include_ha_sync=True
        )


# 全局实例
jjz_push_service = JJZPushService()
