# 初始化日志（需在其他自定义模块之前导入）
import jjz_alert.base.logger  # noqa: F401

import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


async def cleanup_resources():
    """清理应用资源"""
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


def signal_handler(signum, frame):
    """信号处理器"""
    logging.info(f"接收到信号 {signum}，开始清理资源...")
    try:
        # 创建新的事件循环来运行清理函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup_resources())
        loop.close()
    except Exception as e:
        logging.error(f"清理资源时出错: {e}")
    finally:
        sys.exit(0)


async def main():
    """
    主函数 - 使用统一的推送服务处理进京证查询和推送
    """
    logging.info("开始执行进京证查询和推送任务")

    # 初始化消息模板配置
    from jjz_alert.base.message_templates import initialize_templates_from_config
    from jjz_alert.config.config import config_manager

    initialize_templates_from_config(config_manager)

    # 使用统一的推送服务
    from jjz_alert.service.notification.jjz_push_service import jjz_push_service

    try:
        # 执行完整的推送工作流
        result = await jjz_push_service.push_all_plates()

        # 记录执行结果
        if result["success"]:
            logging.info(
                f"推送任务执行成功: {result['success_plates']}/{result['total_plates']} 个车牌推送成功"
            )
        else:
            logging.error(
                f"推送任务执行失败: {result['failed_plates']}/{result['total_plates']} 个车牌推送失败"
            )

        # 记录错误信息
        if result["errors"]:
            for error in result["errors"]:
                logging.error(f"推送过程中的错误: {error}")

        # 记录HA同步结果
        if result["ha_sync_result"]:
            ha_result = result["ha_sync_result"]
            success_count = ha_result.get("success_plates", 0)
            total_count = ha_result.get("total_plates", 0)
            if success_count > 0:
                logging.info(
                    f"Home Assistant同步完成: {success_count}/{total_count} 车牌成功"
                )
            else:
                logging.warning(
                    f"Home Assistant同步失败: {ha_result.get('errors', [])}"
                )

        logging.info("所有任务执行完成")

    except Exception as e:
        logging.error(f"主函数执行异常: {e}")
        raise


def schedule_jobs():
    # 在主线程中注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 配置作业默认行为：允许最多 2 个并发实例，并开启合并以避免错过时段累积触发
    scheduler = BlockingScheduler(
        job_defaults={
            "max_instances": 2,
            "coalesce": True,
        }
    )
    # 使用全局配置管理器实例
    from jjz_alert.config.config import config_manager

    app_config = config_manager.load_config()
    remind_times = (
        app_config.global_config.remind.times
        if app_config.global_config.remind
        else ["08:00", "12:30", "19:00", "23:55"]
    )

    def async_main_wrapper():
        """Wrapper to run async main function in sync scheduler with event loop isolation"""
        # 创建新的事件循环来避免循环冲突
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 在独立的事件循环中执行任务
            loop.run_until_complete(main())
        except Exception as e:
            logging.error(f"定时任务执行失败: {e}")
        finally:
            # 清理事件循环
            try:
                # 确保所有任务完成
                pending = asyncio.all_tasks(loop)
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception as e:
                logging.warning(f"清理待处理任务时出错: {e}")
            finally:
                loop.close()

    for time_str in remind_times:
        hour, minute = map(int, time_str.split(":"))
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(
            async_main_wrapper,
            trigger,
            misfire_grace_time=None,
            max_instances=2,
        )
        logging.info(f"已添加定时任务: 每天 {hour:02d}:{minute:02d}")
    logging.info("定时任务调度器启动")
    scheduler.start()


if __name__ == "__main__":
    from threading import Thread

    # 获取配置
    from jjz_alert.config.config import config_manager

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

    # 若提醒功能开启，同时满足 API 开关，则后台启动 REST API
    if remind_enabled and api_enabled:
        try:
            from rest_api import run_api

            api_thread = Thread(target=run_api, daemon=True)
            api_thread.start()
            logging.info("已在后台启动 REST API 服务")
        except ImportError:
            logging.warning("REST API 模块不可用，跳过API服务启动")

    if remind_enabled:
        # 启动定时任务（阻塞）
        schedule_jobs()
    else:
        # 仅执行一次查询
        asyncio.run(main())
