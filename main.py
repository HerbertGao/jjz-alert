from config.config import get_users, get_remind_times, get_remind_enable
from service.jjz_checker import check_jjz_status
from service.bark_pusher import push_bark, BarkLevel
from utils.parse import parse_status

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

def main():
    users = get_users()
    print(f'[INFO] 读取到 {len(users)} 个用户配置')
    for idx, user in enumerate(users, 1):
        try:
            data = check_jjz_status(user['jjz_token'])
            if 'error' in data:
                print(f'[ERROR] 用户{idx} 查询失败: {data["error"]}')
                result = push_bark('进京证查询失败', None, data['error'], user['bark_server'],
                          encrypt=user.get('bark_encrypt', False),
                          encrypt_key=user.get('bark_encrypt_key'),
                          encrypt_iv=user.get('bark_encrypt_iv'),
                          level=BarkLevel.CRITICAL)
                print(f'[INFO] 用户{idx} Bark推送结果: {result}')
                continue
            all_status = parse_status(data)
            if all_status:
                for info in all_status:
                    msg = f"车牌 {info['plate']} 的进京证（{info['jjz_type']}）状态：{info['status']}，有效期 {info['start_date']} 至 {info['end_date']}，剩余 {info['days_left']} 天。"
                    level = BarkLevel.CRITICAL if info['status'] != '审核通过(生效中)' else BarkLevel.ACTIVE
                    result = push_bark('进京证状态', None, msg, user['bark_server'],
                              encrypt=user.get('bark_encrypt', False),
                              encrypt_key=user.get('bark_encrypt_key'),
                              encrypt_iv=user.get('bark_encrypt_iv'),
                              level=level)
                    print(f'[INFO] 用户{idx} {info["plate"]} Bark推送结果: {result}')
            else:
                print(f'[WARN] 用户{idx} 未获取到任何进京证信息')
        except Exception as e:
            print(f'[ERROR] 用户{idx} 处理异常: {e}')

def schedule_jobs():
    scheduler = BlockingScheduler()
    remind_times = get_remind_times()
    for hour, minute in remind_times:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(main, trigger)
        print(f'[INFO] 已添加定时任务: 每天 {hour:02d}:{minute:02d}')
    print('[INFO] 定时任务调度器启动')
    scheduler.start()

if __name__ == '__main__':
    if get_remind_enable():
        schedule_jobs()
    else:
        main() 