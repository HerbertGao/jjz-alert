import requests

def push_bark(server, key, title, body=None):
    url = f"{server}/{key}/{title}"
    params = {}
    if body:
        params['body'] = body
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)} 