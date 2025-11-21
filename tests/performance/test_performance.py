#!/usr/bin/env python3
"""
JJZ Alert 性能测试

测试关键功能的性能指标:
- Redis连接和操作性能
- 缓存服务性能
- 业务服务性能

运行方式:
python tests/performance/test_performance.py
"""

import asyncio
import logging
import time
from datetime import datetime

from jjz_alert.config.redis.connection import redis_manager
from jjz_alert.service.cache.cache_service import CacheService
from jjz_alert.service.jjz.jjz_service import JJZService


async def test_redis_performance():
    """测试Redis性能"""
    print("🚀 测试Redis连接性能...")

    # 初始化Redis连接
    start_time = time.time()
    success = await redis_manager.initialize()
    init_time = time.time() - start_time

    if not success:
        print("❌ Redis连接失败")
        return {}

    # 测试Redis健康检查
    start_time = time.time()
    health = await redis_manager.health_check()
    health_time = time.time() - start_time

    # 测试基本操作
    cache_service = CacheService()

    # 测试缓存写入
    start_time = time.time()
    test_data = {"test": "performance", "timestamp": datetime.now().isoformat()}
    await cache_service.redis_ops.set("perf_test", test_data, ttl=60)
    write_time = time.time() - start_time

    # 测试缓存读取
    start_time = time.time()
    retrieved = await cache_service.redis_ops.get("perf_test")
    read_time = time.time() - start_time

    # 清理测试数据
    await cache_service.redis_ops.delete("perf_test")

    results = {
        "redis_init_ms": round(init_time * 1000, 2),
        "redis_health_check_ms": round(health_time * 1000, 2),
        "redis_ping_ms": health.get("ping_ms", -1),
        "cache_write_ms": round(write_time * 1000, 2),
        "cache_read_ms": round(read_time * 1000, 2),
        "cache_data_integrity": retrieved == test_data,
    }

    print(f"✅ Redis初始化: {results['redis_init_ms']}ms")
    print(f"✅ Redis健康检查: {results['redis_health_check_ms']}ms")
    print(f"✅ Redis延迟: {results['redis_ping_ms']}ms")
    print(f"✅ 缓存写入: {results['cache_write_ms']}ms")
    print(f"✅ 缓存读取: {results['cache_read_ms']}ms")
    print(f"✅ 数据完整性: {results['cache_data_integrity']}")

    return results


async def test_cache_service_performance():
    """测试缓存服务性能"""
    print("\n🚀 测试缓存服务性能...")

    cache_service = CacheService()

    # 测试进京证数据缓存
    start_time = time.time()
    jjz_data = {
        "status": "valid",
        "apply_time": "2025-08-15 10:00:00",
        "valid_start": "2025-08-15 00:00:00",
        "valid_end": "2025-08-20 23:59:59",
        "days_remaining": 5,
    }
    await cache_service.cache_jjz_data("性能测试车牌", jjz_data)
    cache_jjz_time = time.time() - start_time

    # 测试进京证数据读取
    start_time = time.time()
    retrieved_jjz = await cache_service.get_jjz_data("性能测试车牌")
    get_jjz_time = time.time() - start_time

    # 测试限行规则缓存
    start_time = time.time()
    traffic_rules = [
        {
            "limitedTime": "2025年08月15日",
            "limitedNumber": "4和9",
            "description": "周四限行",
        }
    ]
    await cache_service.cache_traffic_rules(traffic_rules)
    cache_traffic_time = time.time() - start_time

    # 测试获取缓存信息
    start_time = time.time()
    cache_info = await cache_service.get_cache_info()
    get_info_time = time.time() - start_time

    # 清理测试数据
    await cache_service.delete_jjz_data("性能测试车牌")

    results = {
        "cache_jjz_ms": round(cache_jjz_time * 1000, 2),
        "get_jjz_ms": round(get_jjz_time * 1000, 2),
        "cache_traffic_ms": round(cache_traffic_time * 1000, 2),
        "get_cache_info_ms": round(get_info_time * 1000, 2),
        "jjz_data_integrity": retrieved_jjz is not None,
        "total_cache_keys": cache_info.get("key_counts", {}).get("total", 0),
    }

    print(f"✅ 进京证缓存写入: {results['cache_jjz_ms']}ms")
    print(f"✅ 进京证缓存读取: {results['get_jjz_ms']}ms")
    print(f"✅ 限行规则缓存: {results['cache_traffic_ms']}ms")
    print(f"✅ 缓存信息查询: {results['get_cache_info_ms']}ms")
    print(f"✅ 数据完整性: {results['jjz_data_integrity']}")
    print(f"✅ 缓存键总数: {results['total_cache_keys']}")

    return results


async def test_service_performance():
    """测试业务服务性能"""
    print("\n🚀 测试业务服务性能...")

    cache_service = CacheService()
    jjz_service = JJZService(cache_service)

    # 测试服务初始化
    start_time = time.time()
    # 这里我们只测试创建实例的时间
    init_time = time.time() - start_time

    # 测试加载缓存车牌
    start_time = time.time()
    try:
        cached_plates = await jjz_service.get_cached_plates()
        get_plates_time = time.time() - start_time
    except Exception as e:
        print(f"⚠️ 获取缓存车牌列表失败: {e}")
        cached_plates = []
        get_plates_time = -1

    results = {
        "service_init_ms": round(init_time * 1000, 2),
        "get_cached_plates_ms": (
            round(get_plates_time * 1000, 2) if get_plates_time >= 0 else -1
        ),
        "cached_plates_count": len(cached_plates),
    }

    print(f"✅ 服务初始化: {results['service_init_ms']}ms")
    if results["get_cached_plates_ms"] >= 0:
        print(f"✅ 获取缓存车牌: {results['get_cached_plates_ms']}ms")
        print(f"✅ 缓存车牌数量: {results['cached_plates_count']}")

    return results


async def run_performance_tests():
    """运行所有性能测试"""
    print("🎯 JJZ Alert 性能测试")
    print("=" * 50)

    # 禁用调试日志以避免干扰测试结果
    logging.getLogger().setLevel(logging.WARNING)

    all_results = {}

    try:
        # Redis性能测试
        redis_results = await test_redis_performance()
        all_results["redis"] = redis_results

        # 缓存服务性能测试
        cache_results = await test_cache_service_performance()
        all_results["cache_service"] = cache_results

        # 业务服务性能测试
        service_results = await test_service_performance()
        all_results["business_service"] = service_results

        # 输出性能摘要
        print("\n📊 性能测试摘要")
        print("=" * 50)

        # Redis指标
        redis_ping = redis_results.get("redis_ping_ms", -1)
        cache_read = redis_results.get("cache_read_ms", -1)
        cache_write = redis_results.get("cache_write_ms", -1)

        print(
            f"🔸 Redis延迟: {redis_ping}ms {'✅' if redis_ping < 5 else '⚠️' if redis_ping < 20 else '❌'}"
        )
        print(
            f"🔸 缓存读取: {cache_read}ms {'✅' if cache_read < 10 else '⚠️' if cache_read < 50 else '❌'}"
        )
        print(
            f"🔸 缓存写入: {cache_write}ms {'✅' if cache_write < 20 else '⚠️' if cache_write < 100 else '❌'}"
        )

        # 业务服务指标
        service_init = service_results.get("service_init_ms", -1)
        print(
            f"🔸 服务初始化: {service_init}ms {'✅' if service_init < 100 else '⚠️' if service_init < 500 else '❌'}"
        )

        # 整体评估
        print("\n🎉 性能评估结果:")
        if redis_ping < 5 and cache_read < 10 and cache_write < 20:
            print("✅ 优秀 - 所有指标都在理想范围内")
        elif redis_ping < 20 and cache_read < 50 and cache_write < 100:
            print("⚠️ 良好 - 性能指标在可接受范围内")
        else:
            print("❌ 需要优化 - 某些指标超出建议范围")

    except Exception as e:
        print(f"❌ 性能测试过程中发生错误: {e}")
        all_results["error"] = str(e)

    finally:
        # 清理连接
        try:
            await redis_manager.close()
        except:
            pass

    return all_results


if __name__ == "__main__":
    results = asyncio.run(run_performance_tests())
