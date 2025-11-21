#!/usr/bin/env python3
"""
JJZ Alert 测试运行器

提供不同级别的测试运行选项:
- 单元测试 (--unit)
- 集成测试 (--integration)
- Redis测试 (--redis)
- 性能测试 (--performance)
- 覆盖率报告 (--coverage)

使用方式:
python tests/tools/run_tests.py [选项]
"""

import argparse
import subprocess
import sys


def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n{'=' * 60}")
    print(f"🔧 {description}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 命令失败: {e}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="JJZ-Alert 测试运行器")
    parser.add_argument("--unit", action="store_true", help="只运行单元测试")
    parser.add_argument("--integration", action="store_true", help="只运行集成测试")
    parser.add_argument("--redis", action="store_true", help="运行需要Redis的测试")
    parser.add_argument("--performance", action="store_true", help="运行性能测试")
    parser.add_argument("--coverage", action="store_true", help="生成覆盖率报告")
    parser.add_argument("--fast", action="store_true", help="快速测试（跳过慢速测试）")

    args = parser.parse_args()

    # 检查pytest是否安装
    try:
        subprocess.run(
            ["python", "-m", "pytest", "--version"], check=True, capture_output=True
        )
    except subprocess.CalledProcessError:
        print("❌ pytest未安装，请运行: pip install pytest pytest-asyncio")
        return False

    # 构建测试命令
    base_cmd = "python -m pytest"

    if args.unit:
        base_cmd += " -m unit"
    elif args.integration:
        base_cmd += " -m integration"
    elif args.redis:
        base_cmd += " -m redis"

    if args.fast:
        base_cmd += " -m 'not slow'"

    if args.coverage:
        base_cmd += (
            " --cov=jjz_alert.base --cov=jjz_alert.service --cov=jjz_alert.config"
        )
        base_cmd += " --cov-report=term-missing --cov-report=html"

    base_cmd += " -v"

    # 运行测试
    success = True

    if args.unit or not any([args.integration, args.redis]):
        success &= run_command(f"{base_cmd} tests/unit/", "运行单元测试")

    if args.integration:
        success &= run_command(f"{base_cmd} tests/integration/", "运行集成测试")

    if args.performance:
        success &= run_command(
            "python tests/performance/test_performance.py", "运行性能测试"
        )

    if not any([args.unit, args.integration, args.redis, args.performance]):
        # 运行所有测试
        success &= run_command(base_cmd, "运行所有测试")

    # 显示结果
    print(f"\n{'=' * 60}")
    if success:
        print("✅ 所有测试通过！")
        if args.coverage:
            print("📊 覆盖率报告已生成到 htmlcov/ 目录")
    else:
        print("❌ 部分测试失败")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
