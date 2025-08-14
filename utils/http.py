import urllib3
from curl_cffi import requests

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def http_get(url, verify=False, headers=None):
    resp = requests.get(url, verify=verify, timeout=10, headers=headers)
    return resp


def http_post(url, headers=None, json_data=None, verify=False):
    resp = requests.post(url, headers=headers, json=json_data, verify=verify, timeout=10)
    return resp
