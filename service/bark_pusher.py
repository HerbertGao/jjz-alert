from enum import Enum
from urllib.parse import urlencode
from utils.crypto import encrypt_body
from utils.http import http_get
from config.config import get_default_icon

class BarkLevel(Enum):
    CRITICAL = 'critical'
    ACTIVE = 'active'
    TIME_SENSITIVE = 'timeSensitive'
    PASSIVE = 'passive'

def push_bark(title, subtitle, body, server, encrypt=False, encrypt_key=None, encrypt_iv=None, level=None, **kwargs):
    """
    普通推送：URL拼接title/subtitle/body及其它参数。
    加密推送：所有参数组装成json后加密，密文作为ciphertext参数，URL仅拼接title。
    """
    level_value = level.value if isinstance(level, BarkLevel) else (level if level else None)
    url = server.rstrip('/')
    query = {}

    # 添加默认的icon参数
    default_icon = get_default_icon()
    if 'icon' not in kwargs:
        kwargs['icon'] = default_icon

    if encrypt:
        payload = {}
        if body:
            payload['body'] = body
        if title:
            payload['title'] = title
        if subtitle:
            payload['subtitle'] = subtitle
        if level_value:
            payload['level'] = level_value
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        ciphertext = encrypt_body(payload, encrypt_key, encrypt_iv)
        url = f"{url}/{title}" if title else url
        query['ciphertext'] = ciphertext
        debug_info = f'[DEBUG] Bark加密推送: url={url}, body={body}, ciphertext={ciphertext}, payload={payload}'
    else:
        if level_value:
            query['level'] = level_value
        for k, v in kwargs.items():
            if v is not None:
                query[k] = v
        url = f"{url}/{title}" if title else url
        url = f"{url}/{subtitle}" if subtitle else url
        url = f"{url}/{body}" if body else url
        debug_info = f'[DEBUG] Bark普通推送: url={url}, body={body}'

    if query:
        url = f"{url}?{urlencode(query)}"
    print(debug_info)
    try:
        resp = http_get(url)
        print(f'[DEBUG] Bark响应: status={resp.status_code}, text={resp.text}')
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f'[DEBUG] Bark推送异常: {e}')
        return {"error": str(e)} 