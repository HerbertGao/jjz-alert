"""
自动恢复管理器
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from jjz_alert.base.error_exceptions import JJZError, RetryableError
from jjz_alert.base.error_enums import RecoveryStrategy
from jjz_alert.base.error_category import ErrorCategory
from jjz_alert.base.circuit_breaker import CircuitBreaker


class AutoRecoveryManager:
    """自动恢复管理器"""

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.recovery_attempts: Dict[str, Dict] = {}
        self.default_retry_config = {
            "max_attempts": 3,
            "delay": 1.0,
            "backoff_factor": 2.0,
        }

    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        return self.circuit_breakers[service_name]

    async def _invoke(self, func: Callable, *args, **kwargs):
        """在自动恢复流程中执行函数，兼容同步与异步实现"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return await asyncio.to_thread(func, *args, **kwargs)

    def _record_attempt(
        self, service_name: str, strategy: RecoveryStrategy, success: bool
    ) -> None:
        entry = self.recovery_attempts.setdefault(
            service_name,
            {"total": 0, "success": 0, "failures": 0, "last_strategy": None},
        )
        entry["total"] += 1
        if success:
            entry["success"] += 1
        else:
            entry["failures"] += 1
        entry["last_strategy"] = strategy.value

    def _merge_retry_config(
        self, retry_config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        merged = self.default_retry_config.copy()
        if retry_config:
            merged.update(
                {
                    "max_attempts": max(
                        1, retry_config.get("max_attempts", merged["max_attempts"])
                    ),
                    "delay": max(0.0, retry_config.get("delay", merged["delay"])),
                    "backoff_factor": max(
                        1.0,
                        retry_config.get("backoff_factor", merged["backoff_factor"]),
                    ),
                }
            )
        return merged

    async def _execute_with_retry(
        self,
        func: Callable,
        retry_config: Dict[str, Any],
        *args,
        **kwargs,
    ):
        attempts = retry_config["max_attempts"]
        delay = retry_config["delay"]
        backoff_factor = retry_config["backoff_factor"]
        last_exception: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                return await self._invoke(func, *args, **kwargs)
            except Exception as exc:
                last_exception = exc
                if attempt == attempts - 1:
                    break
                logging.warning(
                    f"{func.__name__} 自动恢复第{attempt + 1}次失败: {exc}, "
                    f"{delay}秒后重试"
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor

        if last_exception:
            raise last_exception
        raise RetryableError("自动恢复失败，且未捕获具体异常")

    async def execute_with_recovery(
        self,
        func: Callable,
        service_name: str,
        fallback_func: Optional[Callable] = None,
        *args,
        error: Optional[Exception] = None,
        recovery_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """执行函数并应用自动恢复策略"""
        recovery_strategy = (
            ErrorCategory.get_recovery_strategy(error)
            if error
            else RecoveryStrategy.NONE
        )

        try:
            if recovery_strategy == RecoveryStrategy.CIRCUIT_BREAKER:
                circuit_breaker = self.get_circuit_breaker(service_name)
                # 使用 acall 方法正确处理异步函数，确保异常能被正确捕获
                result = await circuit_breaker.acall(func, *args, **kwargs)
                self._record_attempt(service_name, recovery_strategy, True)
                return result

            if recovery_strategy == RecoveryStrategy.RETRY:
                config = self._merge_retry_config(recovery_config)
                result = await self._execute_with_retry(func, config, *args, **kwargs)
                self._record_attempt(service_name, recovery_strategy, True)
                return result

            if recovery_strategy == RecoveryStrategy.FALLBACK and fallback_func:
                logging.warning(f"服务 {service_name} 失败，使用备用方案: {error}")
                if asyncio.iscoroutinefunction(fallback_func):
                    result = await fallback_func()
                else:
                    result = fallback_func()
                self._record_attempt(service_name, recovery_strategy, True)
                return result

            if recovery_strategy == RecoveryStrategy.GRACEFUL_DEGRADATION:
                logging.warning(f"服务 {service_name} 降级运行: {error}")
                self._record_attempt(service_name, recovery_strategy, True)
                return None

            raise error or JJZError("未提供可处理的错误")

        except Exception as exc:
            self._record_attempt(service_name, recovery_strategy, False)
            if fallback_func and recovery_strategy != RecoveryStrategy.FALLBACK:
                try:
                    logging.warning(
                        f"服务 {service_name} 自动恢复失败，尝试备用方案: {exc}"
                    )
                    if asyncio.iscoroutinefunction(fallback_func):
                        return await fallback_func()
                    return fallback_func()
                except Exception as fallback_error:
                    logging.error(
                        f"服务 {service_name} 备用方案执行失败: {fallback_error}"
                    )
                    raise fallback_error
            raise exc

    def get_status(self) -> Dict[str, Any]:
        """获取恢复管理器状态"""
        return {
            "circuit_breakers": {
                name: {
                    "state": cb.state,
                    "failure_count": cb.failure_count,
                    "last_failure_time": (
                        cb.last_failure_time.isoformat()
                        if cb.last_failure_time
                        else None
                    ),
                }
                for name, cb in self.circuit_breakers.items()
            },
            "recovery_attempts": self.recovery_attempts,
        }


# 全局恢复管理器实例
recovery_manager = AutoRecoveryManager()
