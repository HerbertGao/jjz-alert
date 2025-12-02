# 初始化日志（需在其他自定义模块之前导入）

"""
RESTful API for querying JJZ status for a single plate and pushing notification.
该 API 受 `global.remind.enable` 和 `global.remind.api.enable` 双重控制；只有两者均为 true 时才会启动。

Endpoints
---------
GET /health              Health check - 综合系统健康状态
GET /metrics             Monitoring metrics - 详细的监控指标
POST /query              Body: {"plates": ["京A12345", "津B67890"]}
                        Trigger a query for the specified plates and send notifications
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from jjz_alert.base.logger import get_structured_logger
from jjz_alert.config.config import config_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logging.info("应用启动完成")
    yield
    # 关闭时执行
    logging.info("开始清理应用资源...")

    try:
        # 关闭 MQTT 连接
        from jjz_alert.service.homeassistant.ha_mqtt import ha_mqtt_publisher

        if ha_mqtt_publisher.enabled():
            await ha_mqtt_publisher.close()
            logging.info("MQTT 连接已关闭")
    except Exception as e:
        logging.error(f"关闭 MQTT 连接时出错: {e}")

    try:
        # 关闭 Redis 连接
        from jjz_alert.config.redis.connection import close_redis

        await close_redis()
        logging.info("Redis 连接已关闭")
    except Exception as e:
        logging.error(f"关闭 Redis 连接时出错: {e}")

    try:
        # 关闭 Home Assistant 客户端
        from jjz_alert.service.homeassistant.ha_client import close_ha_client

        await close_ha_client()
        logging.info("Home Assistant 客户端已关闭")
    except Exception as e:
        logging.error(f"关闭 Home Assistant 客户端时出错: {e}")

    logging.info("应用资源清理完成")


app = FastAPI(title="JJZ Alert API", version="2.0.0", lifespan=lifespan)

# 创建结构化日志记录器
structured_logger = get_structured_logger("rest_api")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录API请求的结构化日志"""
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response_time_ms = round(process_time * 1000, 2)

    # 只在DEBUG级别或错误状态码时记录API调用日志
    if logging.getLogger().isEnabledFor(logging.DEBUG) or response.status_code >= 400:
        structured_logger.log_api_call(
            method=request.method,
            endpoint=str(request.url.path),
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            extra_data={
                "query_params": dict(request.query_params),
                "user_agent": request.headers.get("user-agent"),
                "client_ip": request.client.host if request.client else None,
            },
        )

    return response


class QueryRequest(BaseModel):
    plates: List[str] = Field(
        ..., min_items=1, description='车牌号列表，如 ["京A12345", "津B67890"]'
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Enhanced health check endpoint with comprehensive system status"""
    from datetime import datetime
    import time

    start_time = time.time()
    timestamp = datetime.now().isoformat()

    try:
        # 检查配置状态
        app_config = config_manager.load_config()
        config_status = "ok" if app_config.jjz_accounts else "no_accounts"

        health_data = {
            "status": "ok",
            "version": "2.0.0",
            "timestamp": timestamp,
            "uptime_seconds": int(time.time()),  # 简化的运行时间
            "config": {
                "status": config_status,
                "accounts_count": len(app_config.jjz_accounts),
                "plates_count": len(app_config.plates),
                "admin_notifications": len(
                    app_config.global_config.admin.notifications
                ),
            },
            "services": {},
        }

        # 检查Redis连接
        try:
            from jjz_alert.config.redis.connection import redis_manager

            redis_health = await redis_manager.health_check()
            health_data["services"]["redis"] = {
                "status": redis_health.get("status", "unknown"),
                "ping_ms": redis_health.get("ping_ms", -1),
                "connected": redis_health.get("status") == "healthy",
            }
        except Exception as e:
            health_data["services"]["redis"] = {
                "status": "error",
                "error": str(e),
                "connected": False,
            }

        # 检查缓存服务
        try:
            from jjz_alert.service.cache.cache_service import CacheService

            cache_service = CacheService()
            cache_info = await cache_service.get_cache_info()
            cache_stats = await cache_service.get_cache_stats(days=1)

            health_data["services"]["cache"] = {
                "status": "ok",
                "total_keys": cache_info.get("key_counts", {}).get("total", 0),
                "jjz_keys": cache_info.get("key_counts", {}).get("jjz", 0),
                "traffic_keys": cache_info.get("key_counts", {}).get("traffic", 0),
                "hit_rate": cache_stats.get("overall", {}).get("hit_rate", 0),
            }
        except Exception as e:
            health_data["services"]["cache"] = {"status": "error", "error": str(e)}

        # 检查JJZ服务
        try:
            from jjz_alert.service.jjz.jjz_service import jjz_service

            jjz_status = await jjz_service.get_service_status()
            health_data["services"]["jjz"] = {
                "status": jjz_status.get("status", "unknown"),
                "cached_plates": jjz_status.get("cached_plates_count", 0),
                "accounts_count": jjz_status.get("accounts_count", 0),
            }
        except Exception as e:
            health_data["services"]["jjz"] = {"status": "error", "error": str(e)}

        # 检查推送服务
        try:
            from jjz_alert.service.notification.unified_pusher import unified_pusher

            push_status = await unified_pusher.get_service_status()
            health_data["services"]["notification"] = {
                "status": push_status.get("status", "unknown"),
                "apprise_enabled": push_status.get("service_details", {}).get(
                    "apprise_enabled", False
                ),
                "apprise_available": push_status.get("service_details", {}).get(
                    "apprise_available", False
                ),
            }
        except Exception as e:
            health_data["services"]["notification"] = {
                "status": "error",
                "error": str(e),
            }

        # 检查Home Assistant集成
        try:
            from jjz_alert.service.homeassistant.ha_sync import get_ha_service_status

            ha_status = await get_ha_service_status()
            health_data["services"]["homeassistant"] = ha_status
        except Exception as e:
            health_data["services"]["homeassistant"] = {
                "status": "error",
                "error": str(e),
            }

        # 检查错误处理系统
        try:
            from jjz_alert.base.error_handler import get_error_handling_status

            error_handling_status = get_error_handling_status()
            health_data["error_handling"] = error_handling_status
        except Exception as e:
            health_data["error_handling"] = {"status": "error", "error": str(e)}

        # 计算总体健康状态
        service_statuses = [
            health_data["services"].get("redis", {}).get("status") == "healthy",
            health_data["services"].get("cache", {}).get("status") == "ok",
            health_data["services"].get("jjz", {}).get("status") == "healthy",
        ]

        if all(service_statuses):
            health_data["status"] = "healthy"
        elif any(service_statuses):
            health_data["status"] = "degraded"
        else:
            health_data["status"] = "unhealthy"

        # 添加响应时间
        health_data["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

        return health_data

    except Exception as e:
        logging.error(f"健康检查失败: {e}")
        return {
            "status": "error",
            "version": "2.0.0",
            "error": str(e),
            "timestamp": timestamp,
            "response_time_ms": round((time.time() - start_time) * 1000, 2),
        }


@app.get("/metrics")
async def metrics() -> Dict[str, Any]:
    """监控指标端点，提供详细的系统性能和运行指标"""
    from datetime import datetime, timedelta
    import time

    start_time = time.time()
    timestamp = datetime.now().isoformat()

    try:
        metrics_data = {
            "timestamp": timestamp,
            "uptime_seconds": int(time.time()),  # 简化的运行时间
            "system": {},
            "performance": {},
            "business": {},
            "errors": {},
        }

        # 系统指标
        try:
            # Redis指标
            from jjz_alert.config.redis.connection import redis_manager

            redis_health = await redis_manager.health_check()

            # 缓存指标
            from jjz_alert.service.cache.cache_service import CacheService

            cache_service = CacheService()
            cache_info = await cache_service.get_cache_info()
            cache_stats = await cache_service.get_cache_stats(days=7)  # 过去7天统计

            metrics_data["system"] = {
                "redis": {
                    "status": redis_health.get("status", "unknown"),
                    "ping_ms": redis_health.get("ping_ms", -1),
                    "memory_used": redis_health.get("memory_used", 0),
                    "total_keys": cache_info.get("key_counts", {}).get("total", 0),
                },
                "cache": {
                    "jjz_keys": cache_info.get("key_counts", {}).get("jjz", 0),
                    "traffic_keys": cache_info.get("key_counts", {}).get("traffic", 0),
                    "push_history_keys": cache_info.get("key_counts", {}).get(
                        "push_history", 0
                    ),
                    "hit_rate_7d": cache_stats.get("overall", {}).get("hit_rate", 0),
                    "total_operations_7d": cache_stats.get("overall", {}).get(
                        "total_operations", 0
                    ),
                },
            }
        except Exception as e:
            metrics_data["system"]["error"] = str(e)

        # 性能指标
        try:
            # JJZ服务指标
            from jjz_alert.service.jjz.jjz_service import jjz_service

            jjz_status = await jjz_service.get_service_status()

            # 推送服务指标
            from jjz_alert.service.notification.unified_pusher import unified_pusher

            push_status = await unified_pusher.get_service_status()

            # Home Assistant指标
            from jjz_alert.service.homeassistant.ha_sync import get_ha_service_status

            ha_status = await get_ha_service_status()

            metrics_data["performance"] = {
                "jjz_service": {
                    "cached_plates": jjz_status.get("cached_plates_count", 0),
                    "accounts_configured": jjz_status.get("accounts_count", 0),
                    "cache_hit_rate": jjz_status.get("cache_stats", {}).get(
                        "hit_rate", 0
                    ),
                },
                "notification_service": {
                    "total_channels": push_status.get("configuration", {}).get(
                        "total_channels", 0
                    ),
                    "apprise_channels": push_status.get("configuration", {}).get(
                        "apprise_channels", 0
                    ),
                    "apprise_enabled": push_status.get("service_details", {}).get(
                        "apprise_enabled", False
                    ),
                },
                "homeassistant": {
                    "enabled": ha_status.get("enabled", False),
                    "connection_ok": ha_status.get("connection", False),
                    "last_sync": ha_status.get("last_sync"),
                },
            }
        except Exception as e:
            metrics_data["performance"]["error"] = str(e)

        # 业务指标
        try:
            # 配置统计
            app_config = config_manager.load_config()

            # 推送历史统计（过去24小时）
            yesterday = datetime.now() - timedelta(days=1)

            metrics_data["business"] = {
                "configuration": {
                    "total_plates": len(app_config.plates),
                    "total_accounts": len(app_config.jjz_accounts),
                    "admin_notifications": len(
                        app_config.global_config.admin.notifications
                    ),
                },
                "operations_24h": {
                    "estimated_queries": 0,  # 需要从日志或缓存中统计
                    "estimated_pushes": 0,  # 需要从推送历史中统计
                    "ha_syncs": 0,  # 需要从HA同步历史中统计
                },
            }
        except Exception as e:
            metrics_data["business"]["error"] = str(e)

        # 错误指标
        try:
            from jjz_alert.base.error_handler import get_error_handling_status

            error_status = get_error_handling_status()

            metrics_data["errors"] = {
                "total_errors": error_status.get("error_collector", {}).get(
                    "total_errors", 0
                ),
                "error_types": error_status.get("error_collector", {}).get(
                    "error_types", {}
                ),
                "recent_errors": error_status.get("error_collector", {}).get(
                    "recent_errors", 0
                ),
                "circuit_breakers": {
                    "total": error_status.get("recovery_manager", {}).get(
                        "circuit_breakers_count", 0
                    ),
                    "open": len(
                        error_status.get("recovery_manager", {}).get(
                            "open_circuit_breakers", []
                        )
                    ),
                    "open_list": error_status.get("recovery_manager", {}).get(
                        "open_circuit_breakers", []
                    ),
                },
                "admin_notifications": {
                    "interval_seconds": error_status.get("admin_notifier", {}).get(
                        "notification_interval", 0
                    ),
                    "recent_notifications": error_status.get("admin_notifier", {}).get(
                        "last_notifications", 0
                    ),
                },
            }
        except Exception as e:
            metrics_data["errors"]["error"] = str(e)

        # 添加响应时间
        metrics_data["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

        return metrics_data

    except Exception as e:
        logging.error(f"获取监控指标失败: {e}")
        return {
            "timestamp": timestamp,
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2),
        }


@app.post("/query")
async def query_plates(request: QueryRequest):
    """Trigger query & push for one or multiple plate numbers"""
    input_plates = [p.strip().upper() for p in request.plates if p.strip()]
    if not input_plates:
        raise HTTPException(status_code=400, detail="plates 不能为空")

    # Check if API is enabled
    if not is_api_enabled():
        raise HTTPException(
            status_code=403, detail="REST API 已关闭，请在配置中启用后再试"
        )

    # 使用统一的推送服务
    from jjz_alert.service.notification.jjz_push_service import jjz_push_service

    try:
        # 执行统一的推送工作流
        workflow_result = await jjz_push_service.execute_push_workflow(
            plate_numbers=input_plates,
            force_refresh=False,  # API推送不强制刷新缓存
            include_ha_sync=True,
        )

        # 转换为API响应格式
        response_data: Dict[str, Any] = {}

        # 检查是否有配置错误
        if not workflow_result["success"] and workflow_result["errors"]:
            # 检查是否是配置相关错误
            config_errors = [
                err
                for err in workflow_result["errors"]
                if "配置" in err or "未找到车牌配置" in err
            ]
            if config_errors:
                if "未找到车牌配置" in config_errors[0]:
                    raise HTTPException(status_code=404, detail=config_errors[0])
                else:
                    raise HTTPException(status_code=500, detail=config_errors[0])

        # 为每个请求的车牌生成响应
        for plate in input_plates:
            plate_result = workflow_result["plate_results"].get(plate)

            if plate_result:
                response_data[plate] = {
                    "success": plate_result["success"],
                    "jjz_status": plate_result["jjz_status"],
                    "traffic_status": plate_result["traffic_status"],
                    "push_results": plate_result["push_result"],
                    "error": plate_result.get("error"),
                }
            else:
                # 车牌未在结果中找到，可能是配置问题
                response_data[plate] = {
                    "success": False,
                    "jjz_status": None,
                    "traffic_status": None,
                    "push_results": None,
                    "error": "车牌处理失败或未找到配置",
                }

        # 添加总体统计信息
        response_data["_summary"] = {
            "total_plates": workflow_result["total_plates"],
            "success_plates": workflow_result["success_plates"],
            "failed_plates": workflow_result["failed_plates"],
            "ha_sync_result": workflow_result["ha_sync_result"],
            "workflow_success": workflow_result["success"],
        }

        return response_data

    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logging.error(f"API推送工作流执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"推送执行失败: {str(e)}")


def is_api_enabled() -> bool:
    """检查API是否启用"""
    try:
        app_config = config_manager.load_config()
        remind_enabled = (
            app_config.global_config.remind.enable
            if app_config.global_config.remind
            else False
        )
        api_enabled = (
            app_config.global_config.remind.api.enable
            if (app_config.global_config.remind and app_config.global_config.remind.api)
            else False
        )
        return remind_enabled and api_enabled
    except Exception as e:
        logging.error(f"检查API状态失败: {e}")
        return False


def run_api(host: str = None, port: int = None):
    """启动REST API服务
    优先级：显式参数 > 配置 global.remind.api.(host/port) > 默认 0.0.0.0:8000
    """
    cfg_host, cfg_port = None, None
    try:
        app_config = config_manager.load_config()
        if (
            app_config
            and app_config.global_config
            and app_config.global_config.remind
            and app_config.global_config.remind.api
        ):
            cfg_host = app_config.global_config.remind.api.host
            cfg_port = app_config.global_config.remind.api.port
    except Exception:
        pass

    final_host = host or cfg_host or "0.0.0.0"
    final_port = port or cfg_port or 8000

    uvicorn.run(
        app, host=final_host, port=final_port, log_level="warning", access_log=False
    )
