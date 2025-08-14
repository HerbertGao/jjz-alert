"""
错误处理工具模块

提供统一的错误分类、重试机制和监控
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Type, Union, List
from functools import wraps
from enum import Enum


class JJZError(Exception):
    """JJZ系统基础异常"""
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now()


class ConfigurationError(JJZError):
    """配置错误"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "CONFIG_ERROR", details)


class NetworkError(JJZError):
    """网络连接错误"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "NETWORK_ERROR", details)


class APIError(JJZError):
    """API调用错误"""
    def __init__(self, message: str, status_code: int = None, details: Dict[str, Any] = None):
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, "API_ERROR", details)


class CacheError(JJZError):
    """缓存操作错误"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "CACHE_ERROR", details)


class RetryableError(JJZError):
    """可重试的错误"""
    def __init__(self, message: str, retry_after: int = 5, details: Dict[str, Any] = None):
        details = details or {}
        details["retry_after"] = retry_after
        super().__init__(message, "RETRYABLE_ERROR", details)


class ErrorSeverity(Enum):
    """错误严重级别"""
    LOW = "low"           # 轻微错误，记录但不影响系统运行
    MEDIUM = "medium"     # 中等错误，可能影响部分功能，需要关注
    HIGH = "high"         # 高级错误，影响主要功能，需要立即处理
    CRITICAL = "critical" # 严重错误，系统无法正常运行，需要紧急修复


class RecoveryStrategy(Enum):
    """恢复策略"""
    NONE = "none"                 # 无恢复策略
    RETRY = "retry"               # 重试
    FALLBACK = "fallback"         # 使用备用方案
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断
    GRACEFUL_DEGRADATION = "graceful_degradation"  # 优雅降级


class ErrorCategory:
    """错误分类管理"""
    
    # 错误严重级别映射
    SEVERITY_MAPPING = {
        ConfigurationError: ErrorSeverity.HIGH,
        NetworkError: ErrorSeverity.MEDIUM,
        APIError: ErrorSeverity.HIGH,
        CacheError: ErrorSeverity.MEDIUM,
        RetryableError: ErrorSeverity.LOW,
    }
    
    # 错误恢复策略映射
    RECOVERY_MAPPING = {
        ConfigurationError: RecoveryStrategy.FALLBACK,
        NetworkError: RecoveryStrategy.RETRY,
        APIError: RecoveryStrategy.RETRY,
        CacheError: RecoveryStrategy.GRACEFUL_DEGRADATION,
        RetryableError: RecoveryStrategy.RETRY,
    }
    
    @classmethod
    def get_severity(cls, error: Exception) -> ErrorSeverity:
        """获取错误严重级别"""
        error_type = type(error)
        return cls.SEVERITY_MAPPING.get(error_type, ErrorSeverity.MEDIUM)
    
    @classmethod
    def get_recovery_strategy(cls, error: Exception) -> RecoveryStrategy:
        """获取错误恢复策略"""
        error_type = type(error)
        return cls.RECOVERY_MAPPING.get(error_type, RecoveryStrategy.NONE)
    
    @classmethod
    def should_notify_admin(cls, error: Exception) -> bool:
        """判断是否需要通知管理员"""
        severity = cls.get_severity(error)
        return severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
    
    @classmethod
    def should_auto_recover(cls, error: Exception) -> bool:
        """判断是否应该自动恢复"""
        strategy = cls.get_recovery_strategy(error)
        return strategy != RecoveryStrategy.NONE


class CircuitBreaker:
    """熔断器实现"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def call(self, func, *args, **kwargs):
        """执行函数调用，带熔断保护"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
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


class AutoRecoveryManager:
    """自动恢复管理器"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.recovery_attempts: Dict[str, Dict] = {}
    
    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        return self.circuit_breakers[service_name]
    
    async def execute_with_recovery(
        self,
        func: Callable,
        service_name: str,
        fallback_func: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> Any:
        """执行函数并应用自动恢复策略"""
        try:
            # 尝试正常执行
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
                
        except Exception as e:
            recovery_strategy = ErrorCategory.get_recovery_strategy(e)
            
            if recovery_strategy == RecoveryStrategy.CIRCUIT_BREAKER:
                circuit_breaker = self.get_circuit_breaker(service_name)
                try:
                    if asyncio.iscoroutinefunction(func):
                        return await circuit_breaker.call(func, *args, **kwargs)
                    else:
                        return circuit_breaker.call(func, *args, **kwargs)
                except Exception:
                    if fallback_func:
                        logging.warning(f"服务 {service_name} 熔断，使用备用方案")
                        if asyncio.iscoroutinefunction(fallback_func):
                            return await fallback_func(*args, **kwargs)
                        else:
                            return fallback_func(*args, **kwargs)
                    raise
            
            elif recovery_strategy == RecoveryStrategy.FALLBACK and fallback_func:
                logging.warning(f"服务 {service_name} 失败，使用备用方案: {e}")
                if asyncio.iscoroutinefunction(fallback_func):
                    return await fallback_func(*args, **kwargs)
                else:
                    return fallback_func(*args, **kwargs)
            
            elif recovery_strategy == RecoveryStrategy.GRACEFUL_DEGRADATION:
                logging.warning(f"服务 {service_name} 降级运行: {e}")
                return None  # 返回降级结果
            
            else:
                # 其他策略或无策略，直接抛出异常
                raise
    
    def get_status(self) -> Dict[str, Any]:
        """获取恢复管理器状态"""
        return {
            "circuit_breakers": {
                name: {
                    "state": cb.state,
                    "failure_count": cb.failure_count,
                    "last_failure_time": cb.last_failure_time.isoformat() if cb.last_failure_time else None
                }
                for name, cb in self.circuit_breakers.items()
            },
            "recovery_attempts": self.recovery_attempts
        }


def with_error_handling(
    exceptions: Union[Type[Exception], tuple] = Exception,
    default_return: Any = None,
    log_level: str = "auto",  # auto表示根据错误级别自动确定
    raise_on_error: bool = False,
    enable_recovery: bool = True,
    service_name: Optional[str] = None
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
                
                # 处理关键错误
                if ErrorCategory.should_notify_admin(e):
                    try:
                        await handle_critical_error(e, context)
                    except Exception as notify_error:
                        logger.error(f"发送管理员通知失败: {notify_error}")
                
                # 尝试自动恢复
                if enable_recovery and ErrorCategory.should_auto_recover(e) and service_name:
                    try:
                        return await recovery_manager.execute_with_recovery(
                            func, service_name, None, *args, **kwargs
                        )
                    except Exception:
                        pass  # 恢复失败，继续原有逻辑
                
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
                
                # 处理关键错误
                if ErrorCategory.should_notify_admin(e):
                    try:
                        # 同步版本无法直接调用异步函数，记录待处理
                        logger.warning(f"检测到关键错误，需要管理员通知: {e}")
                    except Exception:
                        pass
                
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
    exceptions: Union[Type[Exception], tuple] = (NetworkError, APIError, CacheError)
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


class ErrorCollector:
    """错误收集器，用于监控和统计错误"""
    
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.error_counts: Dict[str, int] = {}
    
    def record_error(self, error: Exception, context: str = ""):
        """记录错误"""
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "context": context
        }
        
        if isinstance(error, JJZError):
            error_info.update({
                "error_code": error.error_code,
                "details": error.details
            })
        
        self.errors.append(error_info)
        
        # 统计错误数量
        error_type = error_info["type"]
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # 限制错误记录数量，保留最近的100条
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误统计摘要"""
        return {
            "total_errors": len(self.errors),
            "error_counts": self.error_counts.copy(),
            "recent_errors": self.errors[-10:] if self.errors else []
        }
    
    def clear_errors(self):
        """清除错误记录"""
        self.errors.clear()
        self.error_counts.clear()


class AdminNotifier:
    """管理员通知器，用于发送系统错误通知"""
    
    def __init__(self):
        self.last_notification_time = {}
        self.notification_interval = 3600  # 1小时内相同类型错误只通知一次
    
    async def notify_admin(self, error: Exception, context: str = ""):
        """向管理员发送错误通知"""
        try:
            from config.config_v2 import config_manager
            from service.notification.unified_pusher import unified_pusher, PushPriority
            
            # 获取配置
            config = config_manager.load_config()
            admin_config = config.global_config.admin
            
            if not admin_config or not admin_config.notifications:
                return
            
            error_type = type(error).__name__
            current_time = datetime.now().timestamp()
            
            # 检查是否需要限制通知频率
            last_time = self.last_notification_time.get(error_type, 0)
            if current_time - last_time < self.notification_interval:
                return
            
            # 构造通知消息
            message = self._build_error_message(error, context)
            
            # 发送通知
            for notification in admin_config.notifications:
                await unified_pusher.push_notification(
                    title="🚨 JJZ系统错误告警",
                    message=message,
                    push_config=notification,
                    priority=PushPriority.HIGH
                )
            
            # 更新最后通知时间
            self.last_notification_time[error_type] = current_time
            logging.info(f"已向管理员发送错误通知: {error_type}")
            
        except Exception as e:
            logging.error(f"发送管理员通知失败: {e}")
    
    def _build_error_message(self, error: Exception, context: str) -> str:
        """构建错误通知消息"""
        lines = []
        lines.append(f"⚠️ 系统错误类型: {type(error).__name__}")
        lines.append(f"📝 错误描述: {str(error)}")
        
        if context:
            lines.append(f"🔍 错误上下文: {context}")
        
        if isinstance(error, JJZError):
            lines.append(f"🔢 错误代码: {error.error_code}")
            if error.details:
                lines.append(f"📋 详细信息: {error.details}")
        
        lines.append(f"⏰ 发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 添加可能的解决方案
        if isinstance(error, ConfigurationError):
            lines.append("💡 建议: 请检查配置文件是否正确")
        elif isinstance(error, NetworkError):
            lines.append("💡 建议: 请检查网络连接和API地址")
        elif isinstance(error, APIError):
            lines.append("💡 建议: 请检查API Token是否有效")
        elif "Token" in str(error) or "token" in str(error):
            lines.append("💡 建议: 进京证Token可能已失效，请更新")
        
        return "\n".join(lines)


# 全局实例
error_collector = ErrorCollector()
admin_notifier = AdminNotifier()
recovery_manager = AutoRecoveryManager()


async def handle_critical_error(error: Exception, context: str = ""):
    """处理关键错误，记录并通知管理员"""
    error_collector.record_error(error, context)
    
    # 对于关键错误类型，通知管理员
    critical_errors = (ConfigurationError, APIError, NetworkError)
    if isinstance(error, critical_errors) or "Token" in str(error):
        await admin_notifier.notify_admin(error, context)


def is_token_error(error: Exception) -> bool:
    """检查是否为Token相关错误"""
    error_msg = str(error).lower()
    token_keywords = ["token", "unauthorized", "403", "401", "认证失败", "令牌"]
    return any(keyword in error_msg for keyword in token_keywords)


def get_error_handling_status() -> Dict[str, Any]:
    """获取错误处理系统状态"""
    try:
        error_summary = error_collector.get_error_summary()
        recovery_status = recovery_manager.get_status()
        
        return {
            "status": "healthy",
            "error_collector": {
                "total_errors": error_summary.get("total_errors", 0),
                "error_types": error_summary.get("error_counts", {}),
                "recent_errors": len(error_summary.get("recent_errors", []))
            },
            "recovery_manager": {
                "circuit_breakers_count": len(recovery_status.get("circuit_breakers", {})),
                "open_circuit_breakers": [
                    name for name, status in recovery_status.get("circuit_breakers", {}).items()
                    if status.get("state") == "open"
                ],
                "recovery_attempts": len(recovery_status.get("recovery_attempts", {}))
            },
            "admin_notifier": {
                "notification_interval": admin_notifier.notification_interval,
                "last_notifications": len(admin_notifier.last_notification_time)
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }