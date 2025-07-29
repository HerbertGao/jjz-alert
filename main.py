from config.config import get_users, get_remind_times, get_remind_enable
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

def main():
    users = get_users()
    print(f'[INFO] 读取到 {len(users)} 个用户配置')
    for idx, user in enumerate(users, 1):
        try:
            data = check_jjz_status(user.get('jjz_url'), user['jjz_token'])
            if 'error' in data:
                print(f'[ERROR] 用户{idx} 查询失败: {data["error"]}')
                # 向所有bark配置发送错误通知
                for bark_idx, bark_config in enumerate(user['bark_configs'], 1):
                    result = push_bark('进京证查询失败', None, data['error'], bark_config['bark_server'],
                              encrypt=bark_config.get('bark_encrypt', False),
                              encrypt_key=bark_config.get('bark_encrypt_key'),
                              encrypt_iv=bark_config.get('bark_encrypt_iv'),
                              level=BarkLevel.CRITICAL)
                    print(f'[INFO] 用户{idx} Bark{bark_idx}推送结果: {result}')
                continue
            all_status = parse_status(data)
            if all_status:
                for info in all_status:
                    # 提取括号内的内容
                    jjz_type_short = info['jjz_type']
                    if '（' in jjz_type_short and '）' in jjz_type_short:
                        jjz_type_short = jjz_type_short.split('（')[1].split('）')[0]
                    
                    # 格式化状态显示
                    status_display = format_status_display(info['status'])
                    
                    # 检查是否限行
                    is_limited = traffic_limiter.check_plate_limited(info['plate'])
                    plate_display = f"{info['plate']} （今日限行）" if is_limited else info['plate']
                    
                    # 根据状态决定是否显示有效期和剩余天数
                    if info['status'] == '审核通过(生效中)':
                        msg = f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}，有效期 {info['start_date']} 至 {info['end_date']}，剩余 {info['days_left']} 天。"
                    else:
                        msg = f"车牌 {plate_display} 的进京证（{jjz_type_short}）状态：{status_display}。"
                    level = BarkLevel.CRITICAL if info['status'] != '审核通过(生效中)' else BarkLevel.ACTIVE
                    
                    # 向所有bark配置发送通知
                    for bark_idx, bark_config in enumerate(user['bark_configs'], 1):
                        result = push_bark('进京证状态', None, msg, bark_config['bark_server'],
                                  encrypt=bark_config.get('bark_encrypt', False),
                                  encrypt_key=bark_config.get('bark_encrypt_key'),
                                  encrypt_iv=bark_config.get('bark_encrypt_iv'),
                                  level=level)
                        print(f'[INFO] 用户{idx} Bark{bark_idx} {info["plate"]} 推送结果: {result}')
            else:
                print(f'[WARN] 用户{idx} 未获取到任何进京证信息')
        except Exception as e:
            print(f'[ERROR] 用户{idx} 处理异常: {e}')

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