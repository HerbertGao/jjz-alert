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
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from config.config_v2 import config_manager
from service.jjz.jjz_service import JJZService
from service.traffic import traffic_limiter
from utils.logger import get_structured_logger
from utils.parse import parse_status

app = FastAPI(title="JJZ Alert API", version="2.0.0")

# 创建结构化日志记录器
structured_logger = get_structured_logger("rest_api")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录API请求的结构化日志"""
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response_time_ms = round(process_time * 1000, 2)

    # 记录API调用日志
    structured_logger.log_api_call(
        method=request.method,
        endpoint=str(request.url.path),
        status_code=response.status_code,
        response_time_ms=response_time_ms,
        extra_data={
            "query_params": dict(request.query_params),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": request.client.host if request.client else None
        }
    )

    return response


class QueryRequest(BaseModel):
    plates: List[str] = Field(..., min_items=1, description="车牌号列表，如 [\"京A12345\", \"津B67890\"]")


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
                "admin_notifications": len(app_config.global_config.admin.notifications)
            },
            "services": {}
        }

        # 检查Redis连接
        try:
            from config.redis.connection import redis_manager
            redis_health = await redis_manager.health_check()
            health_data["services"]["redis"] = {
                "status": redis_health.get("status", "unknown"),
                "ping_ms": redis_health.get("ping_ms", -1),
                "connected": redis_health.get("status") == "healthy"
            }
        except Exception as e:
            health_data["services"]["redis"] = {
                "status": "error",
                "error": str(e),
                "connected": False
            }

        # 检查缓存服务
        try:
            from service.cache.cache_service import CacheService
            cache_service = CacheService()
            cache_info = await cache_service.get_cache_info()
            cache_stats = await cache_service.get_cache_stats(days=1)

            health_data["services"]["cache"] = {
                "status": "ok",
                "total_keys": cache_info.get("key_counts", {}).get("total", 0),
                "jjz_keys": cache_info.get("key_counts", {}).get("jjz", 0),
                "traffic_keys": cache_info.get("key_counts", {}).get("traffic", 0),
                "hit_rate": cache_stats.get("overall", {}).get("hit_rate", 0)
            }
        except Exception as e:
            health_data["services"]["cache"] = {
                "status": "error",
                "error": str(e)
            }

        # 检查JJZ服务
        try:
            from service.jjz.jjz_service import jjz_service
            jjz_status = await jjz_service.get_service_status()
            health_data["services"]["jjz"] = {
                "status": jjz_status.get("status", "unknown"),
                "cached_plates": jjz_status.get("cached_plates_count", 0),
                "accounts_count": jjz_status.get("accounts_count", 0)
            }
        except Exception as e:
            health_data["services"]["jjz"] = {
                "status": "error",
                "error": str(e)
            }

        # 检查推送服务
        try:
            from service.notification.unified_pusher import unified_pusher
            push_status = await unified_pusher.get_service_status()
            health_data["services"]["notification"] = {
                "status": push_status.get("status", "unknown"),
                "channels_available": push_status.get("channels_available", 0)
            }
        except Exception as e:
            health_data["services"]["notification"] = {
                "status": "error",
                "error": str(e)
            }

        # 检查Home Assistant集成
        try:
            from service.homeassistant.ha_sync import get_ha_service_status
            ha_status = await get_ha_service_status()
            health_data["services"]["homeassistant"] = ha_status
        except Exception as e:
            health_data["services"]["homeassistant"] = {
                "status": "error",
                "error": str(e)
            }

        # 检查错误处理系统
        try:
            from utils.error_handler import get_error_handling_status
            error_handling_status = get_error_handling_status()
            health_data["error_handling"] = error_handling_status
        except Exception as e:
            health_data["error_handling"] = {
                "status": "error",
                "error": str(e)
            }

        # 计算总体健康状态
        service_statuses = [
            health_data["services"].get("redis", {}).get("status") == "healthy",
            health_data["services"].get("cache", {}).get("status") == "ok",
            health_data["services"].get("jjz", {}).get("status") == "healthy"
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
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
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
            "errors": {}
        }

        # 系统指标
        try:
            # Redis指标
            from config.redis.connection import redis_manager
            redis_health = await redis_manager.health_check()

            # 缓存指标
            from service.cache.cache_service import CacheService
            cache_service = CacheService()
            cache_info = await cache_service.get_cache_info()
            cache_stats = await cache_service.get_cache_stats(days=7)  # 过去7天统计

            metrics_data["system"] = {
                "redis": {
                    "status": redis_health.get("status", "unknown"),
                    "ping_ms": redis_health.get("ping_ms", -1),
                    "memory_used": redis_health.get("memory_used", 0),
                    "total_keys": cache_info.get("key_counts", {}).get("total", 0)
                },
                "cache": {
                    "jjz_keys": cache_info.get("key_counts", {}).get("jjz", 0),
                    "traffic_keys": cache_info.get("key_counts", {}).get("traffic", 0),
                    "push_history_keys": cache_info.get("key_counts", {}).get("push_history", 0),
                    "hit_rate_7d": cache_stats.get("overall", {}).get("hit_rate", 0),
                    "total_operations_7d": cache_stats.get("overall", {}).get("total_operations", 0)
                }
            }
        except Exception as e:
            metrics_data["system"]["error"] = str(e)

        # 性能指标
        try:
            # JJZ服务指标
            from service.jjz.jjz_service import jjz_service
            jjz_status = await jjz_service.get_service_status()

            # 推送服务指标
            from service.notification.unified_pusher import unified_pusher
            push_status = await unified_pusher.get_service_status()

            # Home Assistant指标
            from service.homeassistant.ha_sync import get_ha_service_status
            ha_status = await get_ha_service_status()

            metrics_data["performance"] = {
                "jjz_service": {
                    "cached_plates": jjz_status.get("cached_plates_count", 0),
                    "accounts_configured": jjz_status.get("accounts_count", 0),
                    "cache_hit_rate": jjz_status.get("cache_stats", {}).get("hit_rate", 0)
                },
                "notification_service": {
                    "total_channels": push_status.get("configuration", {}).get("total_channels", 0),
                    "apprise_channels": push_status.get("configuration", {}).get("apprise_channels", 0),
                    "supported_services": push_status.get("channels_available", 0)
                },
                "homeassistant": {
                    "enabled": ha_status.get("enabled", False),
                    "connection_ok": ha_status.get("connection", False),
                    "last_sync": ha_status.get("last_sync")
                }
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
                    "admin_notifications": len(app_config.global_config.admin.notifications)
                },
                "operations_24h": {
                    "estimated_queries": 0,  # 需要从日志或缓存中统计
                    "estimated_pushes": 0,  # 需要从推送历史中统计
                    "ha_syncs": 0  # 需要从HA同步历史中统计
                }
            }
        except Exception as e:
            metrics_data["business"]["error"] = str(e)

        # 错误指标
        try:
            from utils.error_handler import get_error_handling_status
            error_status = get_error_handling_status()

            metrics_data["errors"] = {
                "total_errors": error_status.get("error_collector", {}).get("total_errors", 0),
                "error_types": error_status.get("error_collector", {}).get("error_types", {}),
                "recent_errors": error_status.get("error_collector", {}).get("recent_errors", 0),
                "circuit_breakers": {
                    "total": error_status.get("recovery_manager", {}).get("circuit_breakers_count", 0),
                    "open": len(error_status.get("recovery_manager", {}).get("open_circuit_breakers", [])),
                    "open_list": error_status.get("recovery_manager", {}).get("open_circuit_breakers", [])
                },
                "admin_notifications": {
                    "interval_seconds": error_status.get("admin_notifier", {}).get("notification_interval", 0),
                    "recent_notifications": error_status.get("admin_notifier", {}).get("last_notifications", 0)
                }
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
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


@app.post("/query")
async def query_plates(request: QueryRequest):
    """Trigger query & push for one or multiple plate numbers"""
    input_plates = [p.strip().upper() for p in request.plates if p.strip()]
    if not input_plates:
        raise HTTPException(status_code=400, detail="plates 不能为空")

    # Check if API is enabled
    if not is_api_enabled():
        raise HTTPException(status_code=403, detail="REST API 已关闭，请在配置中启用后再试")

    # 获取v2.0配置
    try:
        app_config = config_manager.load_config()
        jjz_accounts = app_config.jjz_accounts
        if not jjz_accounts:
            raise HTTPException(status_code=500, detail="未配置任何进京证账户")

        # 获取车牌配置
        plate_configs = app_config.plates
        plate_dict = {p.plate.upper(): p for p in plate_configs}

    except Exception as e:
        logging.error(f"获取v2.0配置失败: {e}")
        raise HTTPException(status_code=500, detail="配置加载失败")

    missing = [p for p in input_plates if p not in plate_dict]
    if missing:
        raise HTTPException(status_code=404, detail=f"未找到车牌配置: {', '.join(missing)}")

    # Preload traffic-limiter cache to speed up check
    traffic_limiter.preload_cache()

    # Collect all jjz data
    jjz_service = JJZService()
    all_jjz_data: List[Dict[str, Any]] = []

    for account in jjz_accounts:
        data = jjz_service._check_jjz_status(account.jjz.url, account.jjz.token)
        if "error" in data:
            raise HTTPException(status_code=502, detail=f"账户 {account.name} 查询失败: {data['error']}")
        status_data = parse_status(data)
        all_jjz_data.extend(status_data)

    response_data: Dict[str, Any] = {}

    for plate_number in input_plates:
        target_records = [info for info in all_jjz_data if info["plate"].upper() == plate_number]
        plate_config = plate_dict[plate_number]

        if not target_records:
            response_data[plate_number] = {"records": 0, "push_results": []}
            continue

        # 选择最新的记录
        selected = max(target_records, key=lambda x: x.get("apply_time", ""))
        logging.info(f"REST API 推送，车牌 {plate_number} 选中记录: {selected}")

        # 使用与main.py完全相同的推送逻辑
        from service.notification.push_helpers import push_jjz_status

        # 将parse_status返回的数据转换为push_jjz_status期望的格式
        jjz_data = {
            "status": "valid",  # API推送默认为有效状态
            "jjzzlmc": selected.get("jjz_type", ""),
            "blztmc": selected.get("status", ""),
            "valid_start": selected.get("start_date", "未知"),
            "valid_end": selected.get("end_date", "未知"),
            "days_remaining": selected.get("days_left"),
            "sycs": selected.get("sycs", "")
        }

        # 执行推送 - 使用与main.py完全相同的函数
        try:
            push_result = await push_jjz_status(plate_config, jjz_data)

            response_data[plate_number] = {
                "records": len(target_records),
                "selected_record": selected,
                "push_results": push_result
            }

        except Exception as e:
            logging.error(f"推送失败: {e}")
            response_data[plate_number] = {
                "records": len(target_records),
                "selected_record": selected,
                "push_results": {
                    "success": False,
                    "error": str(e)
                }
            }

    return response_data


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
            app_config and app_config.global_config and app_config.global_config.remind
            and app_config.global_config.remind.api
        ):
            cfg_host = app_config.global_config.remind.api.host
            cfg_port = app_config.global_config.remind.api.port
    except Exception:
        pass

    final_host = host or cfg_host or "0.0.0.0"
    final_port = port or cfg_port or 8000

    uvicorn.run(app, host=final_host, port=final_port, log_level="warning", access_log=False)
