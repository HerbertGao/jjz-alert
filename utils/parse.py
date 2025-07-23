import datetime

def parse_status(data):
    if 'data' not in data or 'bzclxx' not in data['data']:
        print('[警告] 未找到 data.bzclxx 字段，原始返回：', data)
        return None
    all_status = []
    for car in data['data']['bzclxx']:
        plate = car.get('hphm', '未知车牌')
        bzxx_list = car.get('bzxx', [])
        for bz in bzxx_list:
            end_date = bz.get('yxqz')
            start_date = bz.get('yxqs')
            status = bz.get('blztmc', '未知状态')
            try:
                if end_date:
                    end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                    days_left = (end_dt - datetime.datetime.now()).days
                else:
                    days_left = '无'
            except Exception as e:
                print(f'[警告] 日期解析错误 {end_date}，异常：{e}')
                days_left = '日期格式错误'
            all_status.append({
                'plate': plate,
                'start_date': start_date,
                'end_date': end_date,
                'status': status,
                'days_left': days_left
            })
    return all_status 