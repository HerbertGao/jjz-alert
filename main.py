from config.config import get_jjz_accounts, get_plate_configs, get_remind_times, is_remind_enabled
from service.jjz_checker import check_jjz_status
from service.bark_pusher import push_bark, BarkLevel
from service.traffic_limiter import traffic_limiter
from utils.parse import parse_status

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


def main():
    """
    主函数 - 按照优化后的执行顺序处理进京证查询和推送
    """
    print('[INFO] 开始执行进京证查询和推送任务')
    
    # 步骤1: 读取进京证账户配置
    print('[INFO] 步骤1: 读取进京证账户配置')
    jjz_accounts = get_jjz_accounts()
    print(f'[INFO] 读取到 {len(jjz_accounts)} 个进京证账户配置')
    
    if not jjz_accounts:
        print('[ERROR] 未配置任何进京证账户')
        return
    
    # 步骤2: 读取车牌号配置
    print('[INFO] 步骤2: 读取车牌号配置')
    plate_configs = get_plate_configs()
    print(f'[INFO] 读取到 {len(plate_configs)} 个车牌号配置')
    
    if not plate_configs:
        print('[ERROR] 未配置任何车牌号')
        return
    
    # 步骤3: 创建车牌号配置的查找字典
    print('[INFO] 步骤3: 创建车牌号配置的查找字典')
    plate_config_dict = {config['plate']: config for config in plate_configs}
    print(f'[INFO] 创建了包含 {len(plate_config_dict)} 个车牌号的查找字典')
    
    # 步骤4: 读取尾号限行规则（并缓存）
    print('[INFO] 步骤4: 读取尾号限行规则（并缓存）')
    traffic_limiter.preload_cache()
    
    # 显示缓存状态
    cache_status = traffic_limiter.get_cache_status()
    print(f'[INFO] 缓存状态: {cache_status["status"]}')
    print(f'[INFO] 缓存日期: {cache_status["cache_date"]}')
    print(f'[INFO] 缓存规则数: {cache_status["cache_count"]}')
    
    # 步骤5: 遍历所有进京证账户获取全部进京证数据（创建列表）
    print('[INFO] 步骤5: 遍历所有进京证账户获取全部进京证数据')
    all_jjz_data = []  # 存储所有进京证数据
    
    for account_idx, account in enumerate(jjz_accounts, 1):
        print(f'[INFO] 查询账户 {account_idx}/{len(jjz_accounts)}: {account["name"]}')
        
        try:
            # 查询该账户下的所有车辆信息
            data = check_jjz_status(account['jjz_url'], account['jjz_token'])
            if 'error' in data:
                print(f'[ERROR] 账户 {account["name"]} 查询失败: {data["error"]}')
                # 向所有车牌号配置发送错误通知
                for plate_config in plate_configs:
                    for bark_idx, bark_config in enumerate(plate_config['bark_configs'], 1):
                        result = push_bark('进京证查询失败', None, data['error'], bark_config['bark_server'],
                                  encrypt=bark_config.get('bark_encrypt', False),
                                  encrypt_key=bark_config.get('bark_encrypt_key'),
                                  encrypt_iv=bark_config.get('bark_encrypt_iv'),
                                  level=BarkLevel.CRITICAL,
                                  icon=plate_config['plate_icon'])
                        print(f'[INFO] 车牌{plate_config["plate"]} Bark{bark_idx}推送结果: {result}')
                continue
            
            # 解析查询结果并添加到总列表
            account_status = parse_status(data)
            if account_status:
                print(f'[INFO] 账户 {account["name"]} 查询到 {len(account_status)} 条进京证记录')
                all_jjz_data.extend(account_status)
            else:
                print(f'[WARN] 账户 {account["name"]} 未获取到任何进京证信息')
                
        except Exception as e:
            print(f'[ERROR] 账户 {account["name"]} 处理异常: {e}')
    
    print(f'[INFO] 总共获取到 {len(all_jjz_data)} 条进京证记录')
    
    # 步骤6: 按照 plate_configs 推送通知（通过 push_utils 统一逻辑）
    print('[INFO] 步骤6: 按照 plate_configs 推送通知（统一逻辑）')

    if not all_jjz_data:
        print('[WARN] 未获取到任何进京证数据，跳过推送')
        return

    # 使用公共工具按车牌分组
    from service.push_utils import group_by_plate, select_record, push_plate  # 避免循环引用

    plate_to_infos = group_by_plate(all_jjz_data)

    for plate_config in plate_configs:
        plate = plate_config['plate']
        infos = plate_to_infos.get(plate, [])
        if not infos:
            print(f'[WARN] 未找到车牌 {plate} 的进京证信息，跳过')
            continue

        selected = select_record(infos)
        print(f'[INFO] 准备推送车牌 {plate} 的进京证信息: {selected}')

        push_results = push_plate(selected, plate_config)
        for idx, res in enumerate(push_results, 1):
            print(f'[INFO] 车牌{plate} Bark{idx} 推送结果: {res}')

    print('[INFO] 进京证查询和推送任务执行完成')

def schedule_jobs():
    scheduler = BlockingScheduler()
    remind_times = get_remind_times()
    for hour, minute in remind_times:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(main, trigger, misfire_grace_time=None)
        print(f'[INFO] 已添加定时任务: 每天 {hour:02d}:{minute:02d}')
    print('[INFO] 定时任务调度器启动')
    scheduler.start()

if __name__ == '__main__':
    from threading import Thread
    from service.rest_api import run_api, is_api_enabled

    # 若提醒功能开启，同时满足 API 开关，则后台启动 REST API
    if is_remind_enabled() and is_api_enabled():
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        print('[INFO] 已在后台启动 REST API 服务')

    if is_remind_enabled():
        # 启动定时任务（阻塞）
        schedule_jobs()
    else:
        # 仅执行一次查询
        main() 