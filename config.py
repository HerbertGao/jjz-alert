import os
from dotenv import load_dotenv

load_dotenv()

def get_users():
    users = []
    idx = 1
    while True:
        jjz_token = os.getenv(f'USER{idx}_JJZ_TOKEN')
        bark_server = os.getenv(f'USER{idx}_BARK_SERVER')
        bark_key = os.getenv(f'USER{idx}_BARK_KEY')
        if not jjz_token or not bark_server or not bark_key:
            break
        users.append({
            'jjz_token': jjz_token,
            'bark_server': bark_server.rstrip('/'),
            'bark_key': bark_key
        })
        idx += 1
    return users 