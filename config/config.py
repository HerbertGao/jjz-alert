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

def get_remind_enable():
    """获取定时提醒开关状态"""
    yaml_config = load_yaml_config()
    if yaml_config and 'global' in yaml_config and 'remind' in yaml_config['global']:
        return yaml_config['global']['remind'].get('enable', True)
    
    # 默认值
    return True

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

def get_users():
    """获取用户配置列表"""
    yaml_config = load_yaml_config()
    if yaml_config and 'users' in yaml_config:
        return parse_yaml_users(yaml_config['users'])
    
    # 如果没有配置，返回空列表
    return []

def parse_yaml_users(users_config):
    """解析YAML格式的用户配置（支持数组格式）"""
    users = []
    default_icon = get_default_icon()
    
    # 检查是否为数组格式
    if isinstance(users_config, list):
        # 数组格式：users: [{name: "user1", ...}, {name: "user2", ...}]
        for user_config in users_config:
            if 'jjz' not in user_config or 'bark_configs' not in user_config:
                continue
                
            jjz_config = user_config['jjz']
            bark_configs = []
            
            # 检查bark_configs是否为数组格式
            if isinstance(user_config['bark_configs'], list):
                for bark_config in user_config['bark_configs']:
                    bark_configs.append({
                        'bark_server': bark_config['server'].rstrip('/'),
                        'bark_encrypt': bark_config.get('encrypt', False),
                        'bark_encrypt_key': bark_config.get('encrypt_key'),
                        'bark_encrypt_iv': bark_config.get('encrypt_iv'),
                        'bark_icon': bark_config.get('icon', default_icon),
                    })
            else:
                # 兼容旧的对象格式
                for bark_key, bark_config in user_config['bark_configs'].items():
                    bark_configs.append({
                        'bark_server': bark_config['server'].rstrip('/'),
                        'bark_encrypt': bark_config.get('encrypt', False),
                        'bark_encrypt_key': bark_config.get('encrypt_key'),
                        'bark_encrypt_iv': bark_config.get('encrypt_iv'),
                        'bark_icon': bark_config.get('icon', default_icon),
                    })
            
            if bark_configs:
                users.append({
                    'jjz_token': jjz_config['token'],
                    'jjz_url': jjz_config['url'],
                    'bark_configs': bark_configs
                })
    else:
        # 兼容旧的对象格式：users: {user1: {...}, user2: {...}}
        for user_key, user_config in users_config.items():
            if 'jjz' not in user_config or 'bark_configs' not in user_config:
                continue
                
            jjz_config = user_config['jjz']
            bark_configs = []
            
            # 检查bark_configs是否为数组格式
            if isinstance(user_config['bark_configs'], list):
                for bark_config in user_config['bark_configs']:
                    bark_configs.append({
                        'bark_server': bark_config['server'].rstrip('/'),
                        'bark_encrypt': bark_config.get('encrypt', False),
                        'bark_encrypt_key': bark_config.get('encrypt_key'),
                        'bark_encrypt_iv': bark_config.get('encrypt_iv'),
                        'bark_icon': bark_config.get('icon', default_icon),
                    })
            else:
                # 兼容旧的对象格式
                for bark_key, bark_config in user_config['bark_configs'].items():
                    bark_configs.append({
                        'bark_server': bark_config['server'].rstrip('/'),
                        'bark_encrypt': bark_config.get('encrypt', False),
                        'bark_encrypt_key': bark_config.get('encrypt_key'),
                        'bark_encrypt_iv': bark_config.get('encrypt_iv'),
                        'bark_icon': bark_config.get('icon', default_icon),
                    })
            
            if bark_configs:
                users.append({
                    'jjz_token': jjz_config['token'],
                    'jjz_url': jjz_config['url'],
                    'bark_configs': bark_configs
                })
    
    return users 