# 初始化日志（需在其他自定义模块之前导入）
import utils.logger

import datetime
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.config import (
    get_admin_bark_configs,
    get_jjz_accounts,
    get_plate_configs,
    get_remind_times,
    is_remind_enabled,
)
from service.bark_pusher import BarkLevel, push_bark
from service.jjz_checker import check_jjz_status
from service.push_utils import group_by_plate, push_admin, push_plate, select_record
from service.traffic_limiter import traffic_limiter
from utils.parse import parse_status


def main():
    """
    主函数 - 按照优化后的执行顺序处理进京证查询和推送
    """
    logging.info("开始执行进京证查询和推送任务")

    # 步骤1: 读取进京证账户配置
    logging.info("步骤1: 读取进京证账户配置")
    jjz_accounts = get_jjz_accounts()
    logging.info(f"读取到 {len(jjz_accounts)} 个进京证账户配置")

    if not jjz_accounts:
        logging.error("未配置任何进京证账户")
        return

    # 步骤2: 读取车牌号配置
    logging.info("步骤2: 读取车牌号配置")
    plate_configs = get_plate_configs()
    logging.info(f"读取到 {len(plate_configs)} 个车牌号配置")

    # 读取管理员 Bark 配置
    admin_bark_configs = get_admin_bark_configs()
    logging.info("读取到 %s 个管理员 Bark 配置", len(admin_bark_configs))

    if not plate_configs:
        logging.error("未配置任何车牌号")
        # 若有管理员 Bark，发送提醒
        if admin_bark_configs:
            for idx, bark_cfg in enumerate(admin_bark_configs, 1):
                push_bark(
                    "配置错误",
                    None,
                    "系统未配置任何车牌号，无法查询进京证",
                    bark_cfg["bark_server"],
                    encrypt=bark_cfg.get("bark_encrypt", False),
                    encrypt_key=bark_cfg.get("bark_encrypt_key"),
                    encrypt_iv=bark_cfg.get("bark_encrypt_iv"),
                    level=BarkLevel.CRITICAL,
                )
        return

    # 步骤4: 读取尾号限行规则（并缓存）
    logging.info("步骤4: 读取尾号限行规则（并缓存）")
    traffic_limiter.preload_cache()

    # 显示缓存状态
    cache_status = traffic_limiter.get_cache_status()
    logging.info(f'缓存状态: {cache_status["status"]}')
    logging.info(f'缓存日期: {cache_status["cache_date"]}')
    logging.info(f'缓存规则数: {cache_status["cache_count"]}')

    # 步骤5: 遍历所有进京证账户获取全部进京证数据
    logging.info("步骤5: 遍历所有进京证账户获取全部进京证数据")
    all_jjz_data = []  # 存储所有进京证数据

    for account_idx, account in enumerate(jjz_accounts, 1):
        logging.info(f'查询账户 {account_idx}/{len(jjz_accounts)}: {account["name"]}')

        try:
            # 查询该账户下的所有车辆信息
            data = check_jjz_status(account["jjz_url"], account["jjz_token"])
            logging.debug(f'账户 {account["name"]} API原始返回: {data}')
            if "error" in data:
                logging.error(f'账户 {account["name"]} 查询失败: {data["error"]}')
                # 向管理员发送错误通知
                push_admin("进京证查询失败", data["error"])
                continue

            # 解析查询结果并添加到总列表
            account_status = parse_status(data)
            if account_status:
                logging.info(
                    f'账户 {account["name"]} 查询到 {len(account_status)} 条进京证记录'
                )
                all_jjz_data.extend(account_status)
            else:
                logging.warning(f'账户 {account["name"]} 未获取到任何进京证信息')

        except Exception as e:
            logging.error(f'账户 {account["name"]} 处理异常: {e}')

    logging.info(f"总共获取到 {len(all_jjz_data)} 条进京证记录")

    # 步骤6: 开始推送通知
    logging.info("步骤6: 开始推送通知")

    if not all_jjz_data:
        logging.warning("未获取到任何进京证数据，跳过推送")
        return

    # 使用公共工具按车牌分组

    plate_to_infos = group_by_plate(all_jjz_data)

    now = datetime.datetime.now()
    send_next_day = now.hour > 20 or (now.hour == 20 and now.minute >= 30)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    tomorrow_date = datetime.date.today() + datetime.timedelta(days=1)
    tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")

    # 将每个车牌的推送逻辑封装成内部函数，避免重复代码
    def _process_plate(plate_cfg):
        """根据当前时间推送指定车牌的进京证状态"""
        plate = plate_cfg["plate"]
        infos = plate_to_infos.get(plate, [])
        if not infos:
            logging.warning(f"未找到车牌 {plate} 的进京证信息，跳过")
            return

        selected = select_record(infos)
        logging.info(f"准备推送车牌 {plate} 的进京证信息: {selected}")

        # 20:30 之前推送当日信息
        if not send_next_day:
            for idx, res in enumerate(push_plate(selected, plate_cfg), 1):
                logging.info(f"车牌{plate} 当日 Bark{idx} 推送结果: {res}")

        # 20:30 之后处理次日信息
        if send_next_day:
            # 查找次日适用的进京证记录
            tomorrow_records = [
                r
                for r in infos
                if (
                    r.get("start_date")
                    and r.get("end_date")
                    and r["start_date"] <= tomorrow_str <= r["end_date"]
                )
            ]
            if tomorrow_records:
                tomorrow_active = [
                    r for r in tomorrow_records if r["status"].startswith("审核通过")
                ]
                candidate_list = tomorrow_active or tomorrow_records
                tomorrow_selected = sorted(
                    candidate_list,
                    key=lambda x: (x.get("end_date") or ""),
                    reverse=True,
                )[0]
                logging.info(
                    f"准备推送车牌 {plate} 的次日进京证信息: {tomorrow_selected}"
                )
                for idx, res in enumerate(
                    push_plate(tomorrow_selected, plate_cfg, target_date=tomorrow_date),
                    1,
                ):
                    logging.info(f"车牌{plate} 次日 Bark{idx} 推送结果: {res}")
            else:
                # 无次日记录，且当日证仅到今日，需要提醒办理
                if selected.get("end_date") == today_str:
                    warn_msg = (
                        f"车牌 {plate} 明日尚未查询到进京证信息，请注意及时办理进京证。"
                    )
                    for bark_cfg in plate_cfg["bark_configs"]:
                        warn_res = push_bark(
                            "进京证提醒",
                            None,
                            warn_msg,
                            bark_cfg["bark_server"],
                            encrypt=bark_cfg.get("bark_encrypt", False),
                            encrypt_key=bark_cfg.get("bark_encrypt_key"),
                            encrypt_iv=bark_cfg.get("bark_encrypt_iv"),
                            level=BarkLevel.CRITICAL,
                            icon=plate_cfg.get("plate_icon"),
                        )
                        logging.info(f"车牌{plate} 次日提醒 Bark 推送结果: {warn_res}")

    # 遍历所有车牌配置并推送
    for plate_cfg in plate_configs:
        _process_plate(plate_cfg)

    logging.info("进京证查询和推送任务执行完成")


def schedule_jobs():
    scheduler = BlockingScheduler()
    remind_times = get_remind_times()
    for hour, minute in remind_times:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(main, trigger, misfire_grace_time=None)
        logging.info(f"已添加定时任务: 每天 {hour:02d}:{minute:02d}")
    logging.info("定时任务调度器启动")
    scheduler.start()


if __name__ == "__main__":
    from threading import Thread

    from service.rest_api import is_api_enabled, run_api

    # 若提醒功能开启，同时满足 API 开关，则后台启动 REST API
    if is_remind_enabled() and is_api_enabled():
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        logging.info("已在后台启动 REST API 服务")

    if is_remind_enabled():
        # 启动定时任务（阻塞）
        schedule_jobs()
    else:
        # 仅执行一次查询
        main()
