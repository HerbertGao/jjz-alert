# 初始化日志（需在其他自定义模块之前导入）
import utils.logger

import asyncio
import datetime
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from service.cache.cache_service import CacheService
from service.jjz.jjz_service import JJZService
from service.notification.push_helpers import (
    push_jjz_status,
    push_jjz_reminder,
    push_admin_notification
)
from service.notification.unified_pusher import PushPriority
from service.traffic.traffic_service import TrafficService
from service.homeassistant import sync_to_homeassistant
from service.jjz.jjz_status import JJZStatusEnum


# 删除不再需要的转换函数，直接使用新的推送服务


async def main():
    """
    主函数 - 按照优化后的执行顺序处理进京证查询和推送
    """
    logging.info("开始执行进京证查询和推送任务")

    # 初始化服务
    cache_service = CacheService()
    jjz_service = JJZService(cache_service)
    traffic_service = TrafficService(cache_service)

    # 步骤1: 一次性读取所有配置
    logging.info("步骤1: 读取配置")
    # 使用全局配置管理器实例，避免重复加载
    from config.config_v2 import config_manager

    app_config = config_manager.load_config()

    # 直接从配置对象获取数据，避免重复调用加载函数
    jjz_accounts = app_config.jjz_accounts
    plate_configs = app_config.plates
    admin_notifications = app_config.global_config.admin.notifications

    logging.info(f"读取到 {len(jjz_accounts)} 个进京证账户配置")
    logging.info(f"读取到 {len(plate_configs)} 个车牌号配置")
    logging.info(f"读取到 {len(admin_notifications)} 个管理员通知配置")

    # 验证配置
    if not jjz_accounts:
        logging.error("未配置任何进京证账户")
        return

    if not plate_configs:
        logging.error("未配置任何车牌号")
        # 若有管理员通知，发送提醒
        if admin_notifications:
            result = await push_admin_notification(
                plate_configs=[],
                title="配置错误",
                message="系统未配置任何车牌号，无法查询进京证",
                priority=PushPriority.HIGH
            )
            logging.info(f"管理员通知推送结果: {result}")
        return

    # 步骤3: 智能预加载限行规则缓存
    logging.info("步骤3: 智能预加载限行规则缓存")
    try:
        # 根据当前时间智能查询限行规则
        smart_rules = await traffic_service.get_smart_traffic_rules()

        # 传递已查询的规则给服务状态方法，避免重复查询
        today_rule = smart_rules.get("target_rule")
        service_status = await traffic_service.get_service_status(today_rule)
        logging.info(f"限行服务状态: {service_status['status']}")
    except Exception as e:
        logging.error(f"预加载限行规则失败: {e}")

    # 步骤4: 批量获取所有车牌的进京证数据（优化版本）
    logging.info("步骤4: 批量获取所有车牌的进京证数据")
    
    # 获取所有配置的车牌
    configured_plates = [plate.plate for plate in plate_configs]
    logging.info(f"需要查询的车牌: {configured_plates}")

    # 使用优化的批量查询方法，减少API调用次数
    try:
        all_jjz_results = await jjz_service.get_multiple_status_optimized(configured_plates)
        all_jjz_statuses = []
        
        for plate, status in all_jjz_results.items():
            if status and status.status != JJZStatusEnum.ERROR.value:
                all_jjz_statuses.append(status)
                logging.info(f"车牌 {plate} 状态: {status.status}")
            elif status:
                logging.error(f"车牌 {plate} 查询失败: {status.error_message}")
            else:
                logging.error(f"车牌 {plate} 查询结果为空")
                
    except Exception as e:
        logging.error(f"批量查询进京证数据失败: {e}")
        all_jjz_statuses = []

    logging.info(f"总共获取到 {len(all_jjz_statuses)} 条进京证记录")

    # 步骤5: 开始推送通知
    logging.info("步骤5: 开始推送通知")

    if not all_jjz_statuses:
        logging.warning("未获取到任何进京证数据，跳过推送")
        return

    # 按车牌分组进京证状态
    plate_to_statuses = {}
    for status in all_jjz_statuses:
        plate = status.plate
        if plate not in plate_to_statuses:
            plate_to_statuses[plate] = []
        plate_to_statuses[plate].append(status)

    now = datetime.datetime.now()
    send_next_day = now.hour > 20 or (now.hour == 20 and now.minute >= 30)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    tomorrow_date = datetime.date.today() + datetime.timedelta(days=1)
    tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")

    # 准备HA同步数据
    jjz_results_for_ha = {}      # 存储最终的进京证状态
    traffic_results_for_ha = {}  # 存储限行状态
    
    # 优化: 提前批量获取限行状态，避免重复查询
    logging.info("步骤5.1: 批量获取限行状态")
    try:
        # 批量获取所有车牌的限行状态，避免重复查询
        all_traffic_results = await traffic_service.check_multiple_plates(configured_plates)
        logging.info(f"批量获取限行状态完成: {len(all_traffic_results)} 个车牌")
    except Exception as e:
        logging.error(f"批量获取限行状态失败: {e}")
        all_traffic_results = {}
    
    # 优化: 并发处理推送通知
    async def process_plate_async(plate_cfg):
        """异步处理单个车牌的推送"""
        plate = plate_cfg.plate
        statuses = plate_to_statuses.get(plate, [])

        if not statuses:
            logging.warning(f"未找到车牌 {plate} 的进京证信息，跳过")
            return None, None

        # 选择最新的状态
        latest_status = max(statuses, key=lambda s: s.apply_time or '')
        jjz_data = latest_status.to_dict()

        logging.info(f"准备推送车牌 {plate} 的进京证信息: {jjz_data}")

        # 获取预查询的限行状态
        traffic_result = all_traffic_results.get(plate)
        if traffic_result:
            logging.debug(f"车牌 {plate} 限行状态: 限行={traffic_result.is_limited}")
        else:
            logging.warning(f"未找到车牌 {plate} 的限行状态")

        # 推送任务
        try:
            if not send_next_day:
                # 当日推送
                push_result = await push_jjz_status(plate_cfg, jjz_data)
            else:
                # 次日推送处理
                tomorrow_statuses = [
                    s for s in statuses
                    if (s.valid_start and s.valid_end and
                        s.valid_start <= tomorrow_str <= s.valid_end)
                ]

                if tomorrow_statuses:
                    # 选择次日有效的状态
                    tomorrow_active = [s for s in tomorrow_statuses if s.status == JJZStatusEnum.VALID.value]
                    tomorrow_status = tomorrow_active[0] if tomorrow_active else tomorrow_statuses[0]
                    tomorrow_data = tomorrow_status.to_dict()
                    
                    logging.info(f"准备推送车牌 {plate} 的次日进京证信息: {tomorrow_data}")
                    push_result = await push_jjz_status(plate_cfg, tomorrow_data, target_date=tomorrow_date, is_next_day=True)
                else:
                    # 无次日记录，需要提醒办理
                    if latest_status.valid_end and latest_status.valid_end <= today_str:
                        warn_msg = f"车牌 {plate} 明日尚未查询到进京证信息，请注意及时办理进京证。"
                        push_result = await push_jjz_reminder(plate_cfg, warn_msg, priority=PushPriority.HIGH)
                    else:
                        push_result = None
            
            if push_result:
                logging.info(f"车牌{plate} 推送结果: {push_result}")
            
            return latest_status, traffic_result
            
        except Exception as e:
            logging.error(f"处理车牌 {plate} 时发生异常: {e}")
            return latest_status, traffic_result

    # 步骤5.2: 并发处理所有车牌的推送
    logging.info("步骤5.2: 并发处理推送通知")
    
    # 创建并发任务
    plate_tasks = [process_plate_async(plate_cfg) for plate_cfg in plate_configs if plate_cfg.plate in plate_to_statuses]
    
    if not plate_tasks:
        logging.warning("没有有效的车牌需要处理")
        return
    
    # 并发执行所有车牌处理
    try:
        plate_results = await asyncio.gather(*plate_tasks, return_exceptions=True)
        
        # 收集结果用于HA同步
        for i, result in enumerate(plate_results):
            if isinstance(result, Exception):
                logging.error(f"车牌处理异常: {result}")
                continue
                
            jjz_status, traffic_status = result
            if jjz_status:
                plate = jjz_status.plate
                jjz_results_for_ha[plate] = jjz_status
                if traffic_status:
                    traffic_results_for_ha[plate] = traffic_status
                    
    except Exception as e:
        logging.error(f"并发处理车牌时发生异常: {e}")
        
    logging.info(f"并发处理完成，准备同步 {len(jjz_results_for_ha)} 个车牌到HA")

    logging.info("进京证查询和推送任务执行完成")
    
    # 步骤6: 同步数据到Home Assistant（推送完成后）
    logging.info("步骤6: 同步数据到Home Assistant")
    try:
        if jjz_results_for_ha and traffic_results_for_ha:
            ha_sync_result = await sync_to_homeassistant(jjz_results_for_ha, traffic_results_for_ha)
            
            if ha_sync_result:
                success_count = ha_sync_result.get('success_plates', 0)
                total_count = ha_sync_result.get('total_plates', 0)
                success_rate = ha_sync_result.get('success_rate', 0)
                
                if success_count > 0:
                    logging.info(f"Home Assistant同步完成: {success_count}/{total_count} 车牌成功 ({success_rate}%)")
                else:
                    logging.warning(f"Home Assistant同步失败: {ha_sync_result.get('errors', [])}")
            else:
                logging.debug("Home Assistant集成未启用或同步被跳过")
        else:
            logging.warning("没有数据需要同步到Home Assistant")
            
    except Exception as e:
        logging.error(f"Home Assistant同步异常: {e}")

    logging.info("所有任务执行完成")


def schedule_jobs():
    scheduler = BlockingScheduler()
    # 使用全局配置管理器实例
    from config.config_v2 import config_manager

    app_config = config_manager.load_config()
    remind_times = (
        app_config.global_config.remind.times
        if app_config.global_config.remind
        else ["08:00", "12:30", "19:00", "23:55"]
    )

    def async_main_wrapper():
        """Wrapper to run async main function in sync scheduler"""
        asyncio.run(main())

    for time_str in remind_times:
        hour, minute = map(int, time_str.split(":"))
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(async_main_wrapper, trigger, misfire_grace_time=None)
        logging.info(f"已添加定时任务: 每天 {hour:02d}:{minute:02d}")
    logging.info("定时任务调度器启动")
    scheduler.start()


if __name__ == "__main__":
    from threading import Thread

    # 获取配置
    from config.config_v2 import config_manager

    app_config = config_manager.load_config()
    remind_enabled = (
        app_config.global_config.remind.enable
        if app_config.global_config.remind
        else False
    )
    api_enabled = (
        app_config.global_config.remind.api.enable
        if (app_config.global_config.remind and app_config.global_config.remind.api)
        else False
    )

    # 若提醒功能开启，同时满足 API 开关，则后台启动 REST API
    if remind_enabled and api_enabled:
        try:
            from rest_api import run_api

            api_thread = Thread(target=run_api, daemon=True)
            api_thread.start()
            logging.info("已在后台启动 REST API 服务")
        except ImportError:
            logging.warning("REST API 模块不可用，跳过API服务启动")

    if remind_enabled:
        # 启动定时任务（阻塞）
        schedule_jobs()
    else:
        # 仅执行一次查询
        asyncio.run(main())
