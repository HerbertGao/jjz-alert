from utils.http import http_post


def check_jjz_status(url, token):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    try:
        resp = http_post(url, headers=headers, json_data={})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)} 