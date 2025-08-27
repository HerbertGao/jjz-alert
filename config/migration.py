"""
配置文件迁移工具

用于将v1.x配置文件迁移到v2.0格式
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import yaml

from config.config_v2 import ConfigManager


class ConfigMigration:
    """配置迁移工具"""

    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.backup_file = f"{config_file}.v1.backup"

    def need_migration(self) -> bool:
        """检查是否需要迁移"""
        if not Path(self.config_file).exists():
            return False

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 检查是否为v1格式
            return 'plate_configs' in config
        except Exception as e:
            logging.error(f"检查配置文件失败: {e}")
            return False

    def migrate(self, backup: bool = True) -> bool:
        """执行迁移"""
        try:
            if not self.need_migration():
                logging.info("配置文件无需迁移")
                return True

            # 备份原配置
            if backup:
                self._backup_config()

            # 加载v1配置并转换为v2格式
            manager = ConfigManager(self.config_file)
            v2_config = manager.load_config()

            # 转换为YAML格式并保存
            v2_yaml = self._convert_to_yaml(v2_config)

            # 写入新配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(v2_yaml)

            logging.info("配置文件迁移成功")
            return True

        except Exception as e:
            logging.error(f"配置文件迁移失败: {e}")
            return False

    def _backup_config(self):
        """备份原配置文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{self.config_file}.v1.{timestamp}.backup"

        shutil.copy2(self.config_file, backup_file)
        shutil.copy2(self.config_file, self.backup_file)  # 创建通用备份

        logging.info(f"原配置文件已备份至: {backup_file}")

    def _convert_to_yaml(self, config) -> str:
        """将配置对象转换为YAML格式"""
        # 构建v2格式的配置字典
        config_dict = {
            'global': {
                'log': {
                    'level': config.global_config.log.level
                },
                'remind': {
                    'enable': config.global_config.remind.enable,
                    'times': config.global_config.remind.times,
                    'api': {
                        'enable': config.global_config.remind.api.enable,
                        'host': config.global_config.remind.api.host,
                        'port': config.global_config.remind.api.port
                    }
                },
                'redis': {
                    'host': config.global_config.redis.host,
                    'port': config.global_config.redis.port,
                    'db': config.global_config.redis.db
                },
                'cache': {
                    'push_history_ttl': config.global_config.cache.push_history_ttl
                }
            }
        }

        # 添加Redis密码（如果有）
        if config.global_config.redis.password:
            config_dict['global']['redis']['password'] = config.global_config.redis.password

        # 添加Home Assistant配置（如果启用）
        if config.global_config.homeassistant.enabled:
            config_dict['global']['homeassistant'] = {
                'enabled': True,
                'url': config.global_config.homeassistant.url,
                'token': config.global_config.homeassistant.token,
                'entity_prefix': config.global_config.homeassistant.entity_prefix
            }

        # 添加进京证账户配置
        if config.jjz_accounts:
            config_dict['jjz_accounts'] = []
            for account in config.jjz_accounts:
                config_dict['jjz_accounts'].append({
                    'name': account.name,
                    'jjz': {
                        'token': account.jjz.token,
                        'url': account.jjz.url
                    }
                })

        # 添加车牌配置
        if config.plates:
            config_dict['plates'] = []
            for plate in config.plates:
                plate_dict = {
                    'plate': plate.plate,
                    'notifications': []
                }

                # 添加显示名称（如果有）
                if plate.display_name:
                    plate_dict['display_name'] = plate.display_name

                # 添加图标（如果有）
                if plate.icon:
                    plate_dict['icon'] = plate.icon

                # 添加推送配置
                for notification in plate.notifications:
                    notif_dict = {'type': notification.type}

                    if notification.type == 'apprise':
                        notif_dict.update({
                            'urls': notification.urls
                        })

                    plate_dict['notifications'].append(notif_dict)

                config_dict['plates'].append(plate_dict)

        # 添加管理员配置
        if config.global_config.admin.notifications:
            config_dict['global']['admin'] = {
                'notifications': []
            }

            for notification in config.global_config.admin.notifications:
                notif_dict = {'type': notification.type}

                if notification.type == 'apprise':
                    notif_dict.update({
                        'urls': notification.urls
                    })

                config_dict['global']['admin']['notifications'].append(notif_dict)

        # 生成YAML字符串
        yaml_content = self._generate_yaml_with_comments(config_dict)
        return yaml_content

    def _generate_yaml_with_comments(self, config_dict: Dict[str, Any]) -> str:
        """生成带注释的YAML内容"""
        lines = [
            "# JJZ-Alert v2.0 配置文件",
            "# 自动从v1.x配置迁移生成",
            f"# 迁移时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "# =============================================================================",
            "# 全局配置",
            "# =============================================================================",
        ]

        # 自定义YAML representer，确保times数组使用内联格式
        def represent_times_list(dumper, data):
            if len(data) <= 6:  # 对于较短的列表使用内联格式
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
            return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)

        # 为特定路径的列表使用内联格式
        class CustomDumper(yaml.Dumper):
            def write_line_break(self, data=None):
                super().write_line_break(data)

        # 手动构建YAML内容以保持格式
        yaml_str = yaml.dump(config_dict, allow_unicode=True, default_flow_style=False, sort_keys=False,
                             Dumper=CustomDumper)

        # 后处理：将times数组格式化为内联形式
        import re
        yaml_str = re.sub(
            r'times:\s*\n(\s+- [^\n]+\n)+',
            lambda m: self._format_times_inline(m.group(0)),
            yaml_str
        )

        # 添加注释
        yaml_lines = yaml_str.split('\n')
        result_lines = lines + yaml_lines

        return '\n'.join(result_lines)

    def _format_times_inline(self, times_block: str) -> str:
        """将times数组格式化为内联形式"""
        import re
        # 提取所有时间值
        times = re.findall(r'- ([^\n]+)', times_block)
        # 清理引号并格式化为内联数组
        cleaned_times = []
        for time in times:
            time = time.strip().strip("'\"")  # 移除已有的引号
            cleaned_times.append(f'"{time}"')
        formatted_times = '[' + ', '.join(cleaned_times) + ']'
        return f'times: {formatted_times}\n'

    def rollback(self) -> bool:
        """回滚到v1配置"""
        try:
            if not Path(self.backup_file).exists():
                logging.error("备份文件不存在，无法回滚")
                return False

            shutil.copy2(self.backup_file, self.config_file)
            logging.info("配置文件已回滚到v1版本")
            return True

        except Exception as e:
            logging.error(f"配置回滚失败: {e}")
            return False

    def get_migration_info(self) -> Dict[str, Any]:
        """获取迁移信息"""
        return {
            'config_file': self.config_file,
            'backup_file': self.backup_file,
            'config_exists': Path(self.config_file).exists(),
            'backup_exists': Path(self.backup_file).exists(),
            'need_migration': self.need_migration()
        }


def auto_migrate_if_needed(config_file: str = "config.yaml") -> bool:
    """自动迁移配置文件（如果需要）"""
    migration = ConfigMigration(config_file)

    if migration.need_migration():
        logging.info("检测到v1.x配置格式，开始自动迁移...")
        return migration.migrate()

    return True


def create_migration_tool() -> ConfigMigration:
    """创建迁移工具实例"""
    return ConfigMigration()
