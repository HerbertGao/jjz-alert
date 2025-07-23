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

def get_users():
    users = []
    idx = 1
    while True:
        jjz_token = os.getenv(f'USER{idx}_JJZ_TOKEN')
        bark_server = os.getenv(f'USER{idx}_BARK_SERVER')
        bark_encrypt = os.getenv(f'USER{idx}_BARK_ENCRYPT', 'false').lower() == 'true'
        bark_encrypt_key = os.getenv(f'USER{idx}_BARK_ENCRYPT_KEY') if bark_encrypt else None
        bark_encrypt_iv = os.getenv(f'USER{idx}_BARK_ENCRYPT_IV') if bark_encrypt else None
        if not jjz_token or not bark_server:
            break
        users.append({
            'jjz_token': jjz_token,
            'bark_server': bark_server.rstrip('/'),
            'bark_encrypt': bark_encrypt,
            'bark_encrypt_key': bark_encrypt_key,
            'bark_encrypt_iv': bark_encrypt_iv
        })
        idx += 1
    return users 