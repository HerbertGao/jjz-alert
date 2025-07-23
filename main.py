from config import get_users
from jjz_checker import check_jjz_status
from bark_pusher import push_bark
import datetime

def parse_status(data):
    # 假设返回数据结构中有 applyList，需根据实际接口调整
    if 'applyList' not in data:
        return None
    soon_expire = []
    for item in data['applyList']:
        end_date = item.get('endDate')
        plate = item.get('plateNo', '未知车牌')
        if end_date:
            try:
                end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                days_left = (end_dt - datetime.datetime.now()).days
                if days_left <= 3:
                    soon_expire.append((plate, end_date, days_left))
            except Exception:
                continue
    return soon_expire

def main():
    users = get_users()
    for user in users:
        data = check_jjz_status(user['jjz_token'])
        if 'error' in data:
            push_bark(user['bark_server'], user['bark_key'], '进京证查询失败', data['error'])
            continue
        soon_expire = parse_status(data)
        if soon_expire:
            for plate, end_date, days_left in soon_expire:
                msg = f"车牌 {plate} 的进京证将于 {end_date} 到期，剩余 {days_left} 天，请及时续办。"
                push_bark(user['bark_server'], user['bark_key'], '进京证即将到期', msg)

if __name__ == '__main__':
    main() 