import urllib3
import logging
import time
from curl_cffi import requests
from curl_cffi.requests import Session

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def http_get(url, verify=False, headers=None, max_retries=3):
    """HTTP GET请求，带重试机制"""
    for attempt in range(max_retries):
        try:
            # 使用Session来复用连接
            with Session() as session:
                resp = session.get(
                    url, 
                    verify=verify, 
                    timeout=10, 
                    headers=headers,
                    # 添加TLS相关配置
                    impersonate="chrome110",  # 模拟Chrome浏览器
                )
                return resp
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"HTTP GET请求失败，重试 {attempt + 1}/{max_retries}: {e}")
                time.sleep(1 * (attempt + 1))  # 递增延迟
            else:
                logging.error(f"HTTP GET请求最终失败: {e}")
                raise


def http_post(url, headers=None, json_data=None, verify=False, max_retries=3):
    """HTTP POST请求，带重试机制"""
    for attempt in range(max_retries):
        try:
            # 使用Session来复用连接
            with Session() as session:
                resp = session.post(
                    url, 
                    headers=headers, 
                    json=json_data, 
                    verify=verify, 
                    timeout=10,
                    # 添加TLS相关配置
                    impersonate="chrome110",  # 模拟Chrome浏览器
                )
                return resp
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"HTTP POST请求失败，重试 {attempt + 1}/{max_retries}: {e}")
                time.sleep(1 * (attempt + 1))  # 递增延迟
            else:
                logging.error(f"HTTP POST请求最终失败: {e}")
                raise
