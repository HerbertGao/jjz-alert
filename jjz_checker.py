import requests

def check_jjz_status(token):
    url = "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, headers=headers, json={})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)} 