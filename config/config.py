import os
from dotenv import load_dotenv

load_dotenv()

def get_remind_enable():
    return os.getenv('REMIND_ENABLE', 'true').lower() == 'true'

def get_remind_times():
    times = os.getenv('REMIND_TIMES', '')
    result = []
    for t in times.split(','):
        t = t.strip()
        if not t:
            continue
        try:
            hour, minute = map(int, t.split(':'))
            result.append((hour, minute))
        except Exception:
            continue
    return result

def get_default_icon():
    """获取默认的Bark推送图标URL"""
    return os.getenv('BARK_DEFAULT_ICON', 'https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256')

def get_users():
    users = []
    idx = 1
    while True:
        jjz_token = os.getenv(f'USER{idx}_JJZ_TOKEN')
        jjz_url = os.getenv(f'USER{idx}_JJZ_URL')
        if not jjz_token or not jjz_url:
            break
        
        # 获取该用户的所有bark配置
        bark_configs = []
        bark_idx = 1
        while True:
            bark_server = os.getenv(f'USER{idx}_BARK{bark_idx}_SERVER')
            if not bark_server:
                break
            bark_encrypt = os.getenv(f'USER{idx}_BARK{bark_idx}_ENCRYPT', 'false').lower() == 'true'
            bark_encrypt_key = os.getenv(f'USER{idx}_BARK{bark_idx}_ENCRYPT_KEY') if bark_encrypt else None
            bark_encrypt_iv = os.getenv(f'USER{idx}_BARK{bark_idx}_ENCRYPT_IV') if bark_encrypt else None
            # 获取用户特定的图标配置，如果没有配置则使用默认图标
            bark_icon = os.getenv(f'USER{idx}_BARK{bark_idx}_ICON', get_default_icon())
            
            bark_configs.append({
                'bark_server': bark_server.rstrip('/'),
                'bark_encrypt': bark_encrypt,
                'bark_encrypt_key': bark_encrypt_key,
                'bark_encrypt_iv': bark_encrypt_iv,
                'bark_icon': bark_icon,
            })
            bark_idx += 1
        
        # 如果没有配置bark，使用旧的配置格式作为兼容
        if not bark_configs:
            bark_server = os.getenv(f'USER{idx}_BARK_SERVER')
            if bark_server:
                bark_encrypt = os.getenv(f'USER{idx}_BARK_ENCRYPT', 'false').lower() == 'true'
                bark_encrypt_key = os.getenv(f'USER{idx}_BARK_ENCRYPT_KEY') if bark_encrypt else None
                bark_encrypt_iv = os.getenv(f'USER{idx}_BARK_ENCRYPT_IV') if bark_encrypt else None
                # 获取用户特定的图标配置，如果没有配置则使用默认图标
                bark_icon = os.getenv(f'USER{idx}_BARK_ICON', get_default_icon())
                bark_configs.append({
                    'bark_server': bark_server.rstrip('/'),
                    'bark_encrypt': bark_encrypt,
                    'bark_encrypt_key': bark_encrypt_key,
                    'bark_encrypt_iv': bark_encrypt_iv,
                    'bark_icon': bark_icon,
                })
        
        if bark_configs:
            users.append({
                'jjz_token': jjz_token,
                'jjz_url': jjz_url,
                'bark_configs': bark_configs
            })
        idx += 1
    return users 