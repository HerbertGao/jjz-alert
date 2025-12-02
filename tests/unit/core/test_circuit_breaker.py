"""
CircuitBreaker 单元测试
"""

import asyncio

import pytest

from jjz_alert.base.circuit_breaker import CircuitBreaker


@pytest.mark.unit
class TestCircuitBreaker:
    """CircuitBreaker测试类"""

    def test_call_with_coroutine_result(self):
        """测试同步call方法错误调用返回协程的函数"""
        breaker = CircuitBreaker()

        # 创建一个返回协程的函数（但不是async def定义的）
        async def async_func():
            return "result"

        def wrapper():
            return async_func()

        # 应该捕获到返回协程对象的错误
        with pytest.raises(TypeError) as exc_info:
            breaker.call(wrapper)

        assert "返回了协程对象" in str(exc_info.value)
        assert "acall()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_acall_with_open_circuit_and_reset(self):
        """测试异步acall方法在熔断器打开状态下尝试重置"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0)

        # 触发熔断器打开
        async def failing_func():
            raise Exception("Test error")

        with pytest.raises(Exception):
            await breaker.acall(failing_func)

        # 现在熔断器应该是打开的
        assert breaker.state == "open"

        # 等待超时时间
        await asyncio.sleep(0.1)

        # 下一次调用应该尝试重置，进入半开状态并成功
        async def success_func():
            return "success"

        result = await breaker.acall(success_func)
        assert result == "success"
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_acall_with_open_circuit_no_reset(self):
        """测试异步acall方法在熔断器打开状态下不满足重置条件"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=60)

        # 触发熔断器打开
        async def failing_func():
            raise Exception("Test error")

        with pytest.raises(Exception):
            await breaker.acall(failing_func)

        # 现在熔断器应该是打开的
        assert breaker.state == "open"

        # 立即再次调用应该直接抛出熔断器异常
        async def another_func():
            return "result"

        with pytest.raises(Exception) as exc_info:
            await breaker.acall(another_func)

        assert "Circuit breaker is open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_acall_with_sync_function(self):
        """测试异步acall方法调用同步函数（使用to_thread）"""
        breaker = CircuitBreaker()

        # 定义一个同步函数
        def sync_func(value):
            return value * 2

        # acall应该能够处理同步函数，使用to_thread
        result = await breaker.acall(sync_func, 21)
        assert result == 42
        assert breaker.state == "closed"
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_acall_with_sync_function_failure(self):
        """测试异步acall方法调用失败的同步函数"""
        breaker = CircuitBreaker(failure_threshold=2)

        # 定义一个会失败的同步函数
        def failing_sync_func():
            raise ValueError("Sync function error")

        # 第一次失败
        with pytest.raises(ValueError):
            await breaker.acall(failing_sync_func)

        assert breaker.failure_count == 1
        assert breaker.state == "closed"

        # 第二次失败应该打开熔断器
        with pytest.raises(ValueError):
            await breaker.acall(failing_sync_func)

        assert breaker.failure_count == 2
        assert breaker.state == "open"

    def test_call_with_open_circuit_and_reset(self):
        """测试同步call方法在熔断器打开状态下尝试重置"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0)

        # 触发熔断器打开
        def failing_func():
            raise Exception("Test error")

        with pytest.raises(Exception):
            breaker.call(failing_func)

        # 现在熔断器应该是打开的
        assert breaker.state == "open"

        # 等待超时时间（虽然timeout=0，但datetime比较可能需要微小延迟）
        import time

        time.sleep(0.01)

        # 下一次调用应该尝试重置，进入半开状态并成功
        def success_func():
            return "success"

        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state == "closed"

    def test_call_with_open_circuit_no_reset(self):
        """测试同步call方法在熔断器打开状态下不满足重置条件"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=60)

        # 触发熔断器打开
        def failing_func():
            raise Exception("Test error")

        with pytest.raises(Exception):
            breaker.call(failing_func)

        # 现在熔断器应该是打开的
        assert breaker.state == "open"

        # 立即再次调用应该直接抛出熔断器异常
        def another_func():
            return "result"

        with pytest.raises(Exception) as exc_info:
            breaker.call(another_func)

        assert "Circuit breaker is open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_acall_multiple_operations(self):
        """测试异步acall的多次操作场景"""
        breaker = CircuitBreaker(failure_threshold=3)

        async def operation(should_fail=False):
            if should_fail:
                raise Exception("Operation failed")
            return "success"

        # 多次成功操作
        for _ in range(5):
            result = await breaker.acall(operation, should_fail=False)
            assert result == "success"
            assert breaker.state == "closed"

        # 两次失败操作（不足以触发熔断）
        for _ in range(2):
            with pytest.raises(Exception):
                await breaker.acall(operation, should_fail=True)
            assert breaker.state == "closed"

        # 第三次失败应该触发熔断
        with pytest.raises(Exception):
            await breaker.acall(operation, should_fail=True)
        assert breaker.state == "open"
