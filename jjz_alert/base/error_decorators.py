"""
错误处理装饰器
"""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, Union

from jjz_alert.base.error_exceptions import (
    JJZError,
    NetworkError,
    APIError,
    CacheError,
)
from jjz_alert.base.error_enums import ErrorSeverity
from jjz_alert.base.error_category import ErrorCategory
from jjz_alert.base.error_collector import error_collector
from jjz_alert.base.recovery_manager import recovery_manager
from jjz_alert.base.error_utils import handle_critical_error
from jjz_alert.base.error_utils import _run_async_safe


def with_error_handling(
    exceptions: Union[Type[Exception], tuple] = Exception,
    default_return: Any = None,
    log_level: str = "auto",  # auto表示根据错误级别自动确定
    raise_on_error: bool = False,
    enable_recovery: bool = True,
    service_name: Optional[str] = None,
    fallback_func: Optional[Callable] = None,
    on_error: Optional[Callable[[Exception, str], Any]] = None,
    recovery_config: Optional[Dict[str, Any]] = None,
):
    """
    增强的错误处理装饰器，支持分级处理和自动恢复

    Args:
        exceptions: 需要捕获的异常类型
        default_return: 异常时的默认返回值
        log_level: 日志级别，"auto"表示根据错误严重性自动确定
        raise_on_error: 是否重新抛出异常
        enable_recovery: 是否启用自动恢复
        service_name: 服务名称，用于恢复管理
        fallback_func: 出错时的默认兜底函数
        on_error: 发生错误后的钩子函数，签名为 (error, context)
        recovery_config: 自定义恢复配置（目前主要用于重试策略）
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                logger = logging.getLogger(func.__module__)

                # 获取错误严重级别
                severity = ErrorCategory.get_severity(e)
                context = f"{func.__module__}.{func.__name__}"

                # 根据严重级别确定日志级别
                if log_level == "auto":
                    if severity == ErrorSeverity.CRITICAL:
                        actual_log_level = "critical"
                    elif severity == ErrorSeverity.HIGH:
                        actual_log_level = "error"
                    elif severity == ErrorSeverity.MEDIUM:
                        actual_log_level = "warning"
                    else:
                        actual_log_level = "info"
                else:
                    actual_log_level = log_level

                # 记录错误
                error_msg = f"{context} 执行失败: {e}"
                if actual_log_level == "critical":
                    logger.critical(error_msg)
                elif actual_log_level == "error":
                    logger.error(error_msg)
                elif actual_log_level == "warning":
                    logger.warning(error_msg)
                elif actual_log_level == "info":
                    logger.info(error_msg)

                # 记录到错误收集器
                error_collector.record_error(e, context)

                # 执行错误钩子
                if on_error:
                    try:
                        if asyncio.iscoroutinefunction(on_error):
                            await on_error(e, context)
                        else:
                            on_error(e, context)
                    except Exception as hook_error:
                        logger.warning(f"执行错误钩子失败: {hook_error}")

                # 处理关键错误
                if ErrorCategory.should_notify_admin(e):
                    try:
                        await handle_critical_error(e, context)
                    except Exception as notify_error:
                        logger.error(f"发送管理员通知失败: {notify_error}")

                # 尝试自动恢复
                recovery_attempted = False
                if (
                    enable_recovery
                    and ErrorCategory.should_auto_recover(e)
                    and service_name
                ):
                    recovery_attempted = True
                    try:
                        return await recovery_manager.execute_with_recovery(
                            func,
                            service_name,
                            fallback_func,
                            *args,
                            error=e,
                            recovery_config=recovery_config,
                            **kwargs,
                        )
                    except Exception as recovery_error:
                        logger.warning(f"自动恢复失败: {recovery_error}")

                # 如果未尝试自动恢复或未提供服务名，则直接使用兜底方案
                if fallback_func and not recovery_attempted:
                    try:
                        if asyncio.iscoroutinefunction(fallback_func):
                            return await fallback_func(*args, **kwargs)
                        return fallback_func(*args, **kwargs)
                    except Exception as fallback_error:
                        logger.error(f"备用方案执行失败: {fallback_error}")

                if raise_on_error:
                    raise
                return default_return

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger = logging.getLogger(func.__module__)

                # 获取错误严重级别
                severity = ErrorCategory.get_severity(e)
                context = f"{func.__module__}.{func.__name__}"

                # 根据严重级别确定日志级别
                if log_level == "auto":
                    if severity == ErrorSeverity.CRITICAL:
                        actual_log_level = "critical"
                    elif severity == ErrorSeverity.HIGH:
                        actual_log_level = "error"
                    elif severity == ErrorSeverity.MEDIUM:
                        actual_log_level = "warning"
                    else:
                        actual_log_level = "info"
                else:
                    actual_log_level = log_level

                # 记录错误
                error_msg = f"{context} 执行失败: {e}"
                if actual_log_level == "critical":
                    logger.critical(error_msg)
                elif actual_log_level == "error":
                    logger.error(error_msg)
                elif actual_log_level == "warning":
                    logger.warning(error_msg)
                elif actual_log_level == "info":
                    logger.info(error_msg)

                # 记录到错误收集器
                error_collector.record_error(e, context)

                if on_error:
                    try:
                        if asyncio.iscoroutinefunction(on_error):
                            logger.warning("同步函数不支持异步错误钩子，已跳过")
                        else:
                            on_error(e, context)
                    except Exception as hook_error:
                        logger.warning(f"执行错误钩子失败: {hook_error}")

                # 处理关键错误
                if ErrorCategory.should_notify_admin(e):
                    _run_async_safe(handle_critical_error(e, context))

                # 同步函数仅支持直接兜底方案
                if fallback_func and not asyncio.iscoroutinefunction(fallback_func):
                    try:
                        return fallback_func(*args, **kwargs)
                    except Exception as fallback_error:
                        logger.error(f"备用方案执行失败: {fallback_error}")
                elif fallback_func:
                    logger.warning("同步函数不支持异步备用方案，已跳过")

                if raise_on_error:
                    raise
                return default_return

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def with_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Union[Type[Exception], tuple] = (NetworkError, APIError, CacheError),
):
    """
    重试装饰器

    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟秒数
        backoff_factor: 延迟增长因子
        exceptions: 需要重试的异常类型
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logging.warning(
                            f"{func.__name__} 第{attempt + 1}次尝试失败: {e}, "
                            f"{current_delay}秒后重试"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logging.error(f"{func.__name__} 重试{max_attempts}次后仍然失败")
                except Exception as e:
                    # 非可重试异常直接抛出
                    raise

            # 所有重试都失败了
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logging.warning(
                            f"{func.__name__} 第{attempt + 1}次尝试失败: {e}, "
                            f"{current_delay}秒后重试"
                        )
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logging.error(f"{func.__name__} 重试{max_attempts}次后仍然失败")
                except Exception as e:
                    # 非可重试异常直接抛出
                    raise

            # 所有重试都失败了
            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
