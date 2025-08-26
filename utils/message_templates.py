"""
消息模板管理模块

提供进京证提示内容的模板化配置和管理功能
"""

import logging
from typing import Dict, Any, Optional
from string import Template


class MessageTemplateManager:
    """消息模板管理器"""
    
    def __init__(self, template_config: Optional[Dict[str, str]] = None):
        """
        初始化模板管理器
        
        Args:
            template_config: 模板配置字典，如果为None则使用默认模板
        """
        self.templates = template_config or self._get_default_templates()
        self.logger = logging.getLogger(__name__)
    
    def _get_default_templates(self) -> Dict[str, str]:
        """获取默认模板配置"""
        return {
            # 有效状态模板
            "valid_status": (
                "车牌${display_name}的进京证(${jjz_type})状态：${status_text}，"
                "有效期 ${valid_start} 至 ${valid_end}，剩余 ${days_remaining} 天。"
                "${sycs_part}"
            ),
            
            # 过期状态模板
            "expired_status": (
                "车牌 ${display_name} 的进京证 已过期，请及时续办。"
                "${sycs_part}"
            ),
            
            # 审核中状态模板
            "pending_status": (
                "车牌${display_name}的进京证(${jjz_type})状态：审核中，"
                "申请时间 ${apply_time}。请关注审核进度。"
            ),
            
            # 错误状态模板
            "error_status": (
                "车牌${display_name}的进京证(${jjz_type})状态：${status}。${error_msg}"
            ),
            
            # 限行提醒前缀模板
            "traffic_reminder_prefix": "【⚠️${reminder_text}】",
            
            # 六环内剩余次数部分模板
            "sycs_part": "六环内进京证剩余 ${sycs} 次。",
            "sycs_part_empty": "",
        }
    
    def format_valid_status(
        self,
        display_name: str,
        jjz_type: str,
        status_text: str,
        valid_start: str,
        valid_end: str,
        days_remaining: Optional[int],
        sycs: str,
    ) -> str:
        """
        格式化有效状态消息
        
        Args:
            display_name: 显示名称
            jjz_type: 进京证类型
            status_text: 状态文本
            valid_start: 有效期开始
            valid_end: 有效期结束
            days_remaining: 剩余天数
            sycs: 六环内剩余次数
            
        Returns:
            格式化的消息内容
        """
        try:
            # 处理六环内剩余次数部分
            if sycs:
                sycs_part = Template(self.templates["sycs_part"]).safe_substitute(sycs=sycs)
            else:
                sycs_part = self.templates["sycs_part_empty"]
            
            # 使用模板格式化完整消息
            template = Template(self.templates["valid_status"])
            return template.safe_substitute(
                display_name=display_name,
                jjz_type=jjz_type,
                status_text=status_text,
                valid_start=valid_start,
                valid_end=valid_end,
                days_remaining=days_remaining or 0,  # 如果为None则使用0
                sycs_part=sycs_part,
            )
        except Exception as e:
            self.logger.error(f"格式化有效状态消息失败: {e}")
            # 返回备用格式
            return f"车牌{display_name}的进京证({jjz_type})状态：{status_text}，有效期 {valid_start} 至 {valid_end}"
    
    def format_expired_status(self, display_name: str, sycs: str) -> str:
        """
        格式化过期状态消息
        
        Args:
            display_name: 显示名称
            sycs: 六环内剩余次数
            
        Returns:
            格式化的消息内容
        """
        try:
            # 处理六环内剩余次数部分
            if sycs:
                sycs_part = Template(self.templates["sycs_part"]).safe_substitute(sycs=sycs)
            else:
                sycs_part = self.templates["sycs_part_empty"]
            
            template = Template(self.templates["expired_status"])
            return template.safe_substitute(
                display_name=display_name,
                sycs_part=sycs_part,
            )
        except Exception as e:
            self.logger.error(f"格式化过期状态消息失败: {e}")
            # 返回备用格式
            return f"车牌 {display_name} 的进京证 已过期，请及时续办。"
    
    def format_pending_status(self, display_name: str, jjz_type: str, apply_time: str) -> str:
        """
        格式化审核中状态消息
        
        Args:
            display_name: 显示名称
            jjz_type: 进京证类型
            apply_time: 申请时间
            
        Returns:
            格式化的消息内容
        """
        try:
            template = Template(self.templates["pending_status"])
            return template.safe_substitute(
                display_name=display_name,
                jjz_type=jjz_type,
                apply_time=apply_time,
            )
        except Exception as e:
            self.logger.error(f"格式化审核中状态消息失败: {e}")
            # 返回备用格式
            return f"车牌{display_name}的进京证({jjz_type})状态：审核中，申请时间 {apply_time}。请关注审核进度。"
    
    def format_error_status(self, display_name: str, jjz_type: str, status: str, error_msg: str) -> str:
        """
        格式化错误状态消息
        
        Args:
            display_name: 显示名称
            jjz_type: 进京证类型
            status: 状态码
            error_msg: 错误信息
            
        Returns:
            格式化的消息内容
        """
        try:
            template = Template(self.templates["error_status"])
            return template.safe_substitute(
                display_name=display_name,
                jjz_type=jjz_type,
                status=status,
                error_msg=error_msg,
            )
        except Exception as e:
            self.logger.error(f"格式化错误状态消息失败: {e}")
            # 返回备用格式
            return f"车牌{display_name}的进京证({jjz_type})状态：{status}。{error_msg}"
    
    def format_traffic_reminder(self, reminder_text: str) -> str:
        """
        格式化限行提醒前缀
        
        Args:
            reminder_text: 提醒文本
            
        Returns:
            格式化的提醒前缀
        """
        try:
            template = Template(self.templates["traffic_reminder_prefix"])
            return template.safe_substitute(reminder_text=reminder_text)
        except Exception as e:
            self.logger.error(f"格式化限行提醒失败: {e}")
            # 返回备用格式
            return f"【⚠️{reminder_text}】"
    
    def update_templates(self, new_templates: Dict[str, str]) -> None:
        """
        更新模板配置
        
        Args:
            new_templates: 新的模板配置字典
        """
        self.templates.update(new_templates)
        self.logger.info("模板配置已更新")
    
    def get_template(self, template_name: str) -> Optional[str]:
        """
        获取指定模板
        
        Args:
            template_name: 模板名称
            
        Returns:
            模板内容，如果不存在则返回None
        """
        return self.templates.get(template_name)
    
    def list_templates(self) -> Dict[str, str]:
        """
        列出所有可用模板
        
        Returns:
            模板字典
        """
        return self.templates.copy()


# 全局模板管理器实例
template_manager = MessageTemplateManager()


def initialize_templates_from_config(config_manager=None):
    """
    从配置文件初始化模板配置
    
    Args:
        config_manager: 配置管理器实例，如果为None则自动创建
    """
    try:
        if config_manager is None:
            from config.config_v2 import config_manager as cm
            config_manager = cm
        
        app_config = config_manager.load_config()
        template_config = app_config.global_config.message_templates
        
        # 收集所有非None的模板配置
        new_templates = {}
        for field_name in [
            "valid_status", "expired_status", "pending_status", "error_status",
            "traffic_reminder_prefix", "sycs_part"
        ]:
            value = getattr(template_config, field_name, None)
            if value is not None:
                new_templates[field_name] = value
        
        # 更新模板管理器
        if new_templates:
            template_manager.update_templates(new_templates)
            logging.getLogger(__name__).info(f"已从配置文件加载 {len(new_templates)} 个自定义模板")
        else:
            logging.getLogger(__name__).info("未找到自定义模板配置，使用默认模板")
            
    except Exception as e:
        logging.getLogger(__name__).warning(f"加载模板配置失败，使用默认模板: {e}")
