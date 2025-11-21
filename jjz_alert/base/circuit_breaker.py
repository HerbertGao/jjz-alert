"""
熔断器实现
"""

import asyncio
from datetime import datetime, timedelta


class CircuitBreaker:
    """熔断器实现"""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

    def call(self, func, *args, **kwargs):
        """执行同步函数调用，带熔断保护

        注意：此方法仅适用于同步函数。对于异步函数，请使用 acall() 方法。
        """
        # 检测异步函数，防止误用
        if asyncio.iscoroutinefunction(func):
            raise TypeError(
                "call() 方法不支持异步函数。请使用 acall() 方法来执行异步函数。"
            )

        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            # 检查返回结果是否是协程对象（处理动态创建的异步函数）
            if asyncio.iscoroutine(result):
                raise TypeError(
                    "函数返回了协程对象，但使用了同步 call() 方法。"
                    "请使用 acall() 方法来执行异步函数。"
                )
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def acall(self, func, *args, **kwargs):
        """执行异步函数调用，带熔断保护

        此方法正确处理异步函数，确保异常能被正确捕获，状态管理在异步操作完成后执行。
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is open")

        try:
            # 检查函数是否是异步的
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # 同步函数在线程池中执行，避免阻塞事件循环
                result = await asyncio.to_thread(func, *args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """判断是否应该尝试重置"""
        if self.last_failure_time is None:
            return False
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout)

    def _on_success(self):
        """成功时重置计数器"""
        self.failure_count = 0
        self.state = "closed"

    def _on_failure(self):
        """失败时增加计数器"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
