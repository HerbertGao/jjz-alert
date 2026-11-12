import atexit
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import urllib3
from curl_cffi.requests import Session

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 同时进行的上游请求上限。超出的请求在工作线程队列里等待，不占用事件循环。
HTTP_WORKER_LIMIT = 4
_HTTP_EXECUTOR = ThreadPoolExecutor(
    max_workers=HTTP_WORKER_LIMIT,
    thread_name_prefix="jjz-http",
)
atexit.register(lambda: _HTTP_EXECUTOR.shutdown(wait=False, cancel_futures=True))


def _get_once(url, verify, headers):
    with Session() as session:
        return session.get(
            url,
            verify=verify,
            timeout=10,
            headers=headers,
            impersonate="chrome110",
        )


def _post_once(url, headers, json_data, verify):
    with Session() as session:
        return session.post(
            url,
            headers=headers,
            json=json_data,
            verify=verify,
            timeout=10,
            impersonate="chrome110",
        )


def http_get(url, verify=False, headers=None, max_retries=3) -> Any:
    """HTTP GET请求，带重试机制"""
    for attempt in range(max_retries):
        try:
            return _get_once(url, verify, headers)
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"HTTP GET请求失败，重试 {attempt + 1}/{max_retries}: {e}"
                )
                time.sleep(1 * (attempt + 1))  # 递增延迟
            else:
                logging.error(f"HTTP GET请求最终失败: {e}")
                raise


def http_post(url, headers=None, json_data=None, verify=False, max_retries=3):
    """HTTP POST请求，带重试机制"""
    for attempt in range(max_retries):
        try:
            return _post_once(url, headers, json_data, verify)
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"HTTP POST请求失败，重试 {attempt + 1}/{max_retries}: {e}"
                )
                time.sleep(1 * (attempt + 1))  # 递增延迟
            else:
                logging.error(f"HTTP POST请求最终失败: {e}")
                raise


async def http_post_async(
    url, headers=None, json_data=None, verify=False, max_retries=3
):
    """异步 POST。单次请求在有上限的工作线程中执行，重试等待使用 asyncio.sleep。"""
    loop = asyncio.get_running_loop()
    for attempt in range(max_retries):
        try:
            return await loop.run_in_executor(
                _HTTP_EXECUTOR,
                _post_once,
                url,
                headers,
                json_data,
                verify,
            )
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"HTTP POST请求失败，重试 {attempt + 1}/{max_retries}: {e}"
                )
                await asyncio.sleep(1 * (attempt + 1))
            else:
                logging.error(f"HTTP POST请求最终失败: {e}")
                raise
