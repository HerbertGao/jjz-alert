import requests

def http_get(url):
    resp = requests.get(url)
    return resp

def http_post(url, headers=None, json_data=None):
    resp = requests.post(url, headers=headers, json=json_data)
    return resp 