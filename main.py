from config.config import get_jjz_accounts, get_plate_configs, get_remind_times, get_remind_enable
from service.jjz_checker import check_jjz_status
from service.bark_pusher import push_bark, BarkLevel
from service.traffic_limiter import traffic_limiter
from utils.parse import parse_status

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

def format_status_display(status):
    """
    格式化状态显示
    如果状态包含"审核通过"字样，则只显示括号内的内容
    否则显示完整状态
    """
    if '审核通过' in status and '(' in status and ')' in status:
        # 提取括号内的内容
        start = status.find('(') + 1
        end = status.find(')')
        if start > 0 and end > start:
            return status[start:end]
    return status

def find_plate_config(plate, plate_configs):
    """
    根据车牌号查找对应的配置
    """
    for plate_config in plate_configs:
        if plate_config.get('plate') == plate:
            return plate_config
    return None

def main():
    # 获取配置
    jjz_accounts = get_jjz_accounts()
    plate_configs = get_plate_configs()
    
    print(f'[INFO] 读取到 {len(jjz_accounts)} 个进京证账户配置')
    print(f'[INFO] 读取到 {len(plate_configs)} 个车牌号配置')
    
    if not jjz_accounts:
        print('[ERROR] 未配置任何进京证账户')
        return
    
    if not plate_configs:
        print('[ERROR] 未配置任何车牌号')
        return
    
    # 创建车牌号配置的查找字典，提高查找效率
    plate_config_dict = {config['plate']: config for config in plate_configs}
    
    # 遍历每个进京证账户
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
            
            # 解析查询结果
            all_status = parse_status(data)
            if all_status:
                print(f'[INFO] 账户 {account["name"]} 查询到 {len(all_status)} 条进京证记录')
                
                for info in all_status:
                    plate = info['plate']
                    print(f'[INFO] 处理车牌号: {plate}')
                    
                    # 查找该车牌号对应的配置
                    plate_config = plate_config_dict.get(plate)
                    
                    if not plate_config:
                        print(f'[WARN] 车牌号 {plate} 未在配置中找到对应设置，跳过推送')
                        continue
                    
                    # 提取括号内的内容
                    jjz_type_short = info['jjz_type']
                    if '（' in jjz_type_short and '）' in jjz_type_short:
                        jjz_type_short = jjz_type_short.split('（')[1].split('）')[0]
                    
                    # 格式化状态显示
                    status_display = format_status_display(info['status'])
                    
                    # 检查是否限行
                    is_limited = traffic_limiter.check_plate_limited(plate)
                    plate_display = f"{plate} （今日限行）" if is_limited else plate
                    
                    # 根据状态决定是否显示有效期和剩余天数
                    if info['status'] == '审核通过(生效中)':
                        msg = f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}，有效期 {info['start_date']} 至 {info['end_date']}，剩余 {info['days_left']} 天。"
                    else:
                        msg = f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}。"
                    level = BarkLevel.CRITICAL if info['status'] != '审核通过(生效中)' else BarkLevel.ACTIVE
                    
                    # 使用车牌号专用图标向所有bark配置发送通知
                    for bark_idx, bark_config in enumerate(plate_config['bark_configs'], 1):
                        result = push_bark('进京证状态', None, msg, bark_config['bark_server'],
                                  encrypt=bark_config.get('bark_encrypt', False),
                                  encrypt_key=bark_config.get('bark_encrypt_key'),
                                  encrypt_iv=bark_config.get('bark_encrypt_iv'),
                                  level=level,
                                  icon=plate_config['plate_icon'])
                        print(f'[INFO] 车牌{plate} Bark{bark_idx} 推送结果: {result}')
            else:
                print(f'[WARN] 账户 {account["name"]} 未获取到任何进京证信息')
        except Exception as e:
            print(f'[ERROR] 账户 {account["name"]} 处理异常: {e}')

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
    if get_remind_enable():
        schedule_jobs()
    else:
        main() 