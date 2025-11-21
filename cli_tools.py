#!/usr/bin/env python3
"""
JJZ-Alert CLI工具

提供配置验证、推送测试、HA辅助等功能
"""

import argparse
import asyncio
import logging
import sys

# 设置基本日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def setup_path():
    """设置模块路径"""
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


setup_path()

from jjz_alert.config.validation import ConfigValidator
from jjz_alert.config import config_manager
from jjz_alert.service.notification.adapter import notification_adapter
from jjz_alert.service.homeassistant import ha_sync_service


async def cmd_validate(args):
    """配置验证命令"""
    print(f"🔍 验证配置文件: {args.config}")

    try:
        # 加载配置
        config_manager.config_file = args.config
        config = config_manager.load_config()

        # 验证配置
        validator = ConfigValidator()
        is_valid = validator.validate(config)

        # 显示验证结果
        summary = validator.get_validation_summary()

        print(f"📊 验证结果:")
        print(f"   有效性: {'✅ 通过' if summary['valid'] else '❌ 失败'}")
        print(f"   错误数: {summary['error_count']}")
        print(f"   警告数: {summary['warning_count']}")

        if summary["errors"]:
            print(f"\n❌ 错误列表:")
            for error in summary["errors"]:
                print(f"   - {error}")

        if summary["warnings"]:
            print(f"\n⚠️ 警告列表:")
            for warning in summary["warnings"]:
                print(f"   - {warning}")

        if summary["valid"]:
            print(f"\n✅ 配置文件验证通过!")
        else:
            print(f"\n❌ 配置文件验证失败，请修复上述错误")

    except Exception as e:
        print(f"❌ 验证过程出错: {e}")


async def cmd_test_push(args):
    """推送测试命令"""
    print(f"📱 测试推送功能")

    try:
        # 加载配置
        config_manager.config_file = args.config
        config_manager._config = None  # 重置缓存

        if args.plate:
            # 测试指定车牌
            print(f"🚗 测试车牌: {args.plate}")
            result = await notification_adapter.test_plate_notifications(args.plate)

            print(f"📊 测试结果:")
            print(f"   车牌: {result.get('plate', 'unknown')}")
            print(
                f"   成功: {'✅ 是' if result.get('success_count', 0) > 0 else '❌ 否'}"
            )
            print(
                f"   推送数: {result.get('success_count', 0)}/{result.get('total_count', 0)}"
            )

            if result.get("errors"):
                print(f"\n❌ 错误信息:")
                for error in result["errors"]:
                    print(f"   - {error}")
        else:
            # 测试所有车牌
            print(f"🚗 测试所有车牌推送配置")
            result = await notification_adapter.validate_all_plate_configs()

            print(f"📊 测试结果:")
            print(f"   总车牌数: {result.get('total_plates', 0)}")
            print(f"   有效配置: {result.get('valid_plates', 0)}")
            print(f"   无效配置: {result.get('invalid_plates', 0)}")
            print(f"   整体有效: {'✅ 是' if result.get('valid', False) else '❌ 否'}")

            if args.verbose and result.get("results"):
                print(f"\n📋 详细结果:")
                for plate_result in result["results"]:
                    status = "✅" if plate_result.get("valid", False) else "❌"
                    print(f"   {status} {plate_result.get('plate', 'unknown')}")

                    if not plate_result.get("valid", False) and plate_result.get(
                        "errors"
                    ):
                        for error in plate_result["errors"]:
                            print(f"      - {error}")

    except Exception as e:
        print(f"❌ 推送测试失败: {e}")


async def cmd_status(args):
    """状态查看命令"""
    print(f"📊 JJZ-Alert 状态信息")

    try:
        # 加载配置
        config_manager.config_file = args.config
        config_manager._config = None  # 重置缓存

        # 获取推送服务状态
        status = notification_adapter.get_notification_status()

        print(f"\n🔧 推送服务状态:")
        service_status = status.get("service_status", {})
        print(f"\n📋 配置统计:")
        config_info = status.get("configuration", {})
        print(f"   车牌数量: {config_info.get('total_plates', 0)}")

        print(f"   Apprise通道: {config_info.get('apprise_channels', 0)}")
        print(f"   总通道数: {config_info.get('total_channels', 0)}")

        if args.verbose:
            print(f"\n🛠️ 支持的Apprise服务:")
            supported_services = service_status.get("supported_apprise_services", [])
            for service in supported_services[:10]:  # 显示前10个
                print(f"   - {service}")
            if len(supported_services) > 10:
                print(f"   ... 还有{len(supported_services) - 10}个服务")

        # Home Assistant状态
        print(f"\n🏠 Home Assistant状态:")
        try:
            ha_status = await ha_sync_service.get_sync_status()
            if ha_status.get("enabled"):
                connection_status = ha_status.get("connection_status", {})
                if connection_status.get("success"):
                    print(f"   状态: ✅ 已连接")
                    print(f"   版本: {connection_status.get('version', 'unknown')}")
                else:
                    print(f"   状态: ❌ 连接失败")
                    print(f"   错误: {connection_status.get('error', 'unknown')}")

                config_info = ha_status.get("config", {})
                print(f"   URL: {config_info.get('url')}")
                print(f"   实体前缀: {config_info.get('entity_prefix')}")
                print(
                    f"   查询后同步: {'✅' if config_info.get('sync_after_query') else '❌'}"
                )
                print(
                    f"   车牌设备模式: {'✅' if config_info.get('create_device_per_plate') else '❌'}"
                )

                last_sync = ha_status.get("last_sync_time")
                if last_sync:
                    print(f"   最后同步: {last_sync}")
                else:
                    print(f"   最后同步: 从未同步")
            else:
                print(f"   状态: 未启用")
        except Exception as e:
            print(f"   状态: ❌ 获取失败: {e}")

    except Exception as e:
        print(f"❌ 获取状态失败: {e}")


async def cmd_ha_test(args):
    """测试Home Assistant连接"""
    print("🏠 测试Home Assistant连接...")

    try:
        config_manager.config_file = args.config
        config_manager._config = None  # 重置缓存

        result = await ha_sync_service.test_connection()

        if result["success"]:
            print(f"✅ 连接成功!")
            print(f"   版本: {result.get('version', 'unknown')}")
            print(f"   消息: {result.get('message', '')}")
        else:
            print(f"❌ 连接失败!")
            print(f"   错误: {result.get('error', 'unknown')}")

    except Exception as e:
        print(f"❌ 测试异常: {e}")


async def cmd_ha_sync(args):
    """手动同步数据到Home Assistant"""
    print("🏠 手动同步数据到Home Assistant...")

    try:
        config_manager.config_file = args.config
        config_manager._config = None  # 重置缓存

        # 检查HA是否启用
        from jjz_alert.config import get_homeassistant_config

        ha_config = get_homeassistant_config()

        if not ha_config.enabled:
            print("❌ Home Assistant集成未启用")
            return

        # 模拟主流程数据获取（简化版）
        from jjz_alert.service.jjz.jjz_service import jjz_service
        from jjz_alert.service.traffic.traffic_service import traffic_service
        from jjz_alert.config import get_plates

        print("📊 获取车牌数据...")
        plates_config = get_plates()

        if not plates_config:
            print("❌ 未配置任何车牌")
            return

        jjz_results = {}
        traffic_results = {}

        for plate_config in plates_config:
            plate = plate_config.plate
            print(f"   查询车牌: {plate}")

            try:
                # 获取进京证状态
                jjz_status = await jjz_service.get_jjz_status(plate)
                jjz_results[plate] = jjz_status

                # 获取限行状态
                traffic_status = await traffic_service.check_plate_limited(plate)
                traffic_results[plate] = traffic_status

            except Exception as e:
                print(f"   ⚠️ 车牌 {plate} 数据获取失败: {e}")

        if not jjz_results or not traffic_results:
            print("❌ 没有有效数据可同步")
            return

        print(f"🔄 同步 {len(jjz_results)} 个车牌数据到Home Assistant...")

        # 执行同步
        result = await ha_sync_service.sync_from_query_results(
            jjz_results, traffic_results
        )

        # 显示结果
        success_count = result.get("success_plates", 0)
        total_count = result.get("total_plates", 0)
        success_rate = result.get("success_rate", 0)

        if success_count > 0:
            print(
                f"✅ 同步完成: {success_count}/{total_count} 车牌成功 ({success_rate}%)"
            )

            if args.verbose:
                print(f"\n📋 详细结果:")
                for plate_result in result.get("plate_results", []):
                    plate = plate_result.get("plate_number")
                    success = plate_result.get("success")
                    entity_count = plate_result.get("entity_count", 0)

                    status_icon = "✅" if success else "❌"
                    print(f"   {status_icon} {plate}: {entity_count} 个实体")

                    if not success and plate_result.get("error"):
                        print(f"      错误: {plate_result['error']}")
        else:
            print(f"❌ 同步失败")
            for error in result.get("errors", []):
                print(f"   错误: {error}")

    except Exception as e:
        print(f"❌ 同步异常: {e}")


async def cmd_ha_cleanup(args):
    """清理Home Assistant过期实体"""
    print("🏠 清理Home Assistant过期实体...")

    try:
        config_manager.config_file = args.config
        config_manager._config = None  # 重置缓存

        if not args.force:
            confirm = input("⚠️ 这将删除不在当前配置中的HA实体，确认继续? (y/N): ")
            if confirm.lower() != "y":
                print("❌ 取消操作")
                return

        result = await ha_sync_service.cleanup_stale_entities()

        if result["success"]:
            deleted_count = result.get("deleted_count", 0)
            total_found = result.get("total_found", 0)

            print(f"✅ 清理完成!")
            print(f"   发现实体: {total_found} 个")
            print(f"   删除实体: {deleted_count} 个")

            if result.get("errors"):
                print(f"⚠️ 部分删除失败:")
                for error in result["errors"][:5]:  # 只显示前5个错误
                    print(f"   - {error}")
        else:
            print(f"❌ 清理失败: {result.get('error')}")

    except Exception as e:
        print(f"❌ 清理异常: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="JJZ-Alert CLI工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 验证配置文件
  python cli_tools.py validate
  
  # 测试所有车牌推送
  python cli_tools.py test-push
  
  # 测试指定车牌推送  
  python cli_tools.py test-push --plate 京A12345
  
  # 查看系统状态
  python cli_tools.py status -v
  
  # Home Assistant相关操作
  python cli_tools.py ha test          # 测试HA连接
  python cli_tools.py ha sync -v       # 手动同步数据到HA
  python cli_tools.py ha cleanup       # 清理HA过期实体
        """,
    )

    parser.add_argument(
        "--config", "-c", default="config.yaml", help="配置文件路径 (默认: config.yaml)"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 验证命令
    validate_parser = subparsers.add_parser("validate", help="验证配置文件")

    # 推送测试命令
    test_parser = subparsers.add_parser("test-push", help="测试推送功能")
    test_parser.add_argument("--plate", help="指定要测试的车牌号")

    # 状态查看命令
    status_parser = subparsers.add_parser("status", help="查看系统状态")

    # Home Assistant相关命令
    ha_parser = subparsers.add_parser("ha", help="Home Assistant相关操作")
    ha_subparsers = ha_parser.add_subparsers(dest="ha_command", help="HA子命令")

    # HA连接测试
    ha_test_parser = ha_subparsers.add_parser("test", help="测试HA连接")

    # HA手动同步
    ha_sync_parser = ha_subparsers.add_parser("sync", help="手动同步数据到HA")

    # HA实体清理
    ha_cleanup_parser = ha_subparsers.add_parser("cleanup", help="清理HA过期实体")
    ha_cleanup_parser.add_argument(
        "--force", action="store_true", help="强制执行，不询问确认"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 执行命令
    if args.command == "validate":
        asyncio.run(cmd_validate(args))
    elif args.command == "test-push":
        asyncio.run(cmd_test_push(args))
    elif args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "ha":
        if args.ha_command == "test":
            asyncio.run(cmd_ha_test(args))
        elif args.ha_command == "sync":
            asyncio.run(cmd_ha_sync(args))
        elif args.ha_command == "cleanup":
            asyncio.run(cmd_ha_cleanup(args))
        else:
            print(f"❌ 未知HA命令: {args.ha_command}")
            ha_parser.print_help()
    else:
        print(f"❌ 未知命令: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()
