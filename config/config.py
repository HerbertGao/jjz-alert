import os
import yaml

def load_yaml_config(config_file='config.yaml'):
    """加载YAML配置文件"""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
    except Exception as e:
        print(f'[WARN] 无法加载YAML配置文件 {config_file}: {e}')
    return None

def is_remind_enabled():
    """获取定时提醒开关状态"""
    yaml_config = load_yaml_config()
    if yaml_config and 'global' in yaml_config and 'remind' in yaml_config['global']:
        return yaml_config['global']['remind'].get('enable', True)

    # 默认值
    return True

# 兼容旧名称
get_remind_enable = is_remind_enabled

def get_remind_times():
    """获取定时提醒时间列表"""
    yaml_config = load_yaml_config()
    if yaml_config and 'global' in yaml_config and 'remind' in yaml_config['global']:
        times = yaml_config['global']['remind'].get('times', [])
        result = []
        for t in times:
            try:
                hour, minute = map(int, t.split(':'))
                result.append((hour, minute))
            except Exception:
                continue
        return result
    
    # 默认值
    return []

def get_default_icon():
    """获取默认的Bark推送图标URL"""
    yaml_config = load_yaml_config()
    if yaml_config and 'global' in yaml_config:
        return yaml_config['global'].get('bark_default_icon', 'https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256')
    
    # 默认值
    return 'https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256'

def get_jjz_accounts():
    """获取进京证账户配置列表"""
    yaml_config = load_yaml_config()
    if yaml_config and 'jjz_accounts' in yaml_config:
        return parse_jjz_accounts(yaml_config['jjz_accounts'])
    
    # 如果没有配置，返回空列表
    return []

def get_plate_configs():
    """获取车牌号配置列表"""
    yaml_config = load_yaml_config()
    if yaml_config and 'plate_configs' in yaml_config:
        return parse_plate_configs(yaml_config['plate_configs'])
    
    # 如果没有配置，返回空列表
    return []

def parse_jjz_accounts(accounts_config):
    """解析进京证账户配置"""
    accounts = []
    
    if isinstance(accounts_config, list):
        for account_config in accounts_config:
            if 'jjz' not in account_config:
                continue
                
            jjz_config = account_config['jjz']
            accounts.append({
                'name': account_config.get('name', '未知账户'),
                'jjz_token': jjz_config['token'],
                'jjz_url': jjz_config['url']
            })
    
    return accounts

def parse_plate_configs(plate_configs):
    """解析车牌号配置"""
    plate_configs_list = []
    default_icon = get_default_icon()
    
    if isinstance(plate_configs, list):
        for plate_config in plate_configs:
            if 'plate' not in plate_config or 'bark_configs' not in plate_config:
                continue
                
            bark_configs = []
            
            # 检查bark_configs是否为数组格式
            if isinstance(plate_config['bark_configs'], list):
                for bark_config in plate_config['bark_configs']:
                    bark_configs.append({
                        'bark_server': bark_config['server'].rstrip('/'),
                        'bark_encrypt': bark_config.get('encrypt', False),
                        'bark_encrypt_key': bark_config.get('encrypt_key'),
                        'bark_encrypt_iv': bark_config.get('encrypt_iv'),
                    })
            
            if bark_configs:
                plate_configs_list.append({
                    'plate': plate_config['plate'],
                    'plate_icon': plate_config.get('plate_icon', default_icon),
                    'bark_configs': bark_configs
                })
    
    return plate_configs_list

# 兼容旧版本的函数
def get_users():
    """兼容旧版本的get_users函数"""
    print('[WARN] get_users() 函数已废弃，请使用 get_jjz_accounts() 和 get_plate_configs()')
    return []

def parse_yaml_users(users_config):
    """兼容旧版本的parse_yaml_users函数"""
    print('[WARN] parse_yaml_users() 函数已废弃')
    return [] 