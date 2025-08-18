"""
Apprise多通道推送服务

支持80+推送服务，包括Bark、Telegram、微信、钉钉等
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import apprise


class ApprisePusher:
    """Apprise推送器"""

    def __init__(self):
        self.apprise_instance = None
        # 延迟初始化，不在构造函数中立即初始化

    def _init_apprise(self):
        """初始化Apprise实例"""
        try:
            self.apprise_instance = apprise.Apprise()

            # 验证实例是否真的可用（显式判断是否为None，避免Apprise实例因__len__==0被判定为False）
            if self.apprise_instance is not None:
                return True
            else:
                logging.error("apprise实例创建失败")
                return False

        except Exception as e:
            logging.error(f"Apprise实例初始化失败: {e}")
            self.apprise_instance = None
            return False

    async def send_notification(
            self,
            urls: List[str],
            title: str,
            body: str,
            **kwargs
    ) -> Dict[str, Any]:
        """
        发送多通道推送通知
        
        Args:
            urls: Apprise URL列表
            title: 推送标题
            body: 推送内容
            **kwargs: 其他参数
        
        Returns:
            推送结果
        """
        try:
            if self.apprise_instance is None:
                init_success = self._init_apprise()
                if not init_success:
                    logging.error("apprise_instance初始化失败")
                    return {
                        'success': False,
                        'error': 'Apprise实例初始化失败',
                        'valid_urls': 0,
                        'invalid_urls': len(urls),
                        'url_results': []
                    }

            # 使用传入的标题
            final_title = title

            # 清除之前的URL配置
            self.apprise_instance.clear()

            # 添加URL配置并记录结果
            valid_urls = []
            invalid_urls = []
            url_results = []

            for url in urls:
                if self.apprise_instance.add(url):
                    valid_urls.append(url)
                    url_results.append({
                        'url': self._mask_url(url),
                        'valid': True,
                        'success': None  # 将在推送后更新
                    })
                else:
                    invalid_urls.append(url)
                    url_results.append({
                        'url': self._mask_url(url),
                        'valid': False,
                        'success': False,
                        'error': 'URL格式无效'
                    })
                    logging.warning(f"Apprise URL无效: {self._mask_url(url)}")

            if not valid_urls:
                return {
                    'success': False,
                    'error': '没有有效的推送URL',
                    'valid_urls': 0,
                    'invalid_urls': len(invalid_urls),
                    'url_results': url_results
                }

            # 执行推送
            start_time = datetime.now()

            # 在线程池中执行同步的Apprise推送
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self.apprise_instance.notify,
                body,
                final_title
            )

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # 更新有效URL的推送结果
            for url_result in url_results:
                if url_result['valid']:
                    url_result['success'] = success

            result = {
                'success': success,
                'title': final_title,
                'body': body,
                'valid_urls': len(valid_urls),
                'invalid_urls': len(invalid_urls),
                'duration_ms': round(duration_ms, 2),
                'timestamp': end_time.isoformat(),
                'url_results': url_results
            }

            if success:
                logging.info(f"Apprise推送成功: {len(valid_urls)}个通道, 耗时{duration_ms:.0f}ms")
            else:
                logging.error(f"Apprise推送失败: {len(valid_urls)}个通道")
                result['error'] = 'Apprise推送执行失败'

            return result

        except Exception as e:
            logging.error(f"Apprise推送异常: {e}")
            return {
                'success': False,
                'error': str(e),
                'valid_urls': 0,
                'invalid_urls': len(urls),
                'url_results': []
            }

    def _mask_url(self, url: str) -> str:
        """遮蔽URL中的敏感信息"""
        try:
            # 简单的URL遮蔽，隐藏token等敏感信息
            if '://' in url:
                scheme, rest = url.split('://', 1)
                if '/' in rest:
                    host_part, path_part = rest.split('/', 1)
                    # 只显示前几个字符
                    if len(path_part) > 8:
                        masked_path = path_part[:4] + '****' + path_part[-4:]
                    else:
                        masked_path = '****'
                    return f"{scheme}://{host_part}/{masked_path}"
                else:
                    return f"{scheme}://****"
            else:
                return "****"
        except Exception:
            return "****"

    def validate_urls(self, urls: List[str]) -> Dict[str, List[str]]:
        """验证URL有效性"""
        try:
            if not self.apprise_instance:
                self._init_apprise()

            if not self.apprise_instance:
                return {
                    'valid': [],
                    'invalid': urls,
                    'error': 'Apprise实例初始化失败'
                }

            valid_urls = []
            invalid_urls = []

            # 使用已初始化的Apprise实例进行验证
            for url in urls:
                if self.apprise_instance.add(url):
                    valid_urls.append(url)
                else:
                    invalid_urls.append(url)
                    logging.warning(f"URL验证失败: {self._mask_url(url)}")

            return {
                'valid': valid_urls,
                'invalid': invalid_urls,
                'total': len(urls),
                'valid_count': len(valid_urls),
                'invalid_count': len(invalid_urls)
            }

        except Exception as e:
            logging.error(f"URL验证失败: {e}")
            return {
                'valid': [],
                'invalid': urls,
                'error': str(e)
            }

    def get_supported_services(self) -> List[str]:
        """获取支持的推送服务列表"""
        try:
            # Apprise支持的主要服务
            services = [
                'bark',  # Bark
                'tgram',  # Telegram
                'mailto',  # Email
                'wxwork',  # 企业微信
                'dingding',  # 钉钉
                'slack',  # Slack
                'discord',  # Discord
                'teams',  # Microsoft Teams
                'webhook',  # 通用Webhook
                'json',  # JSON Webhook
                'form',  # Form数据
                'fcm',  # Firebase云消息
                'gotify',  # Gotify
                'pushover',  # Pushover
                'prowl',  # Prowl
                'pushbullet',  # Pushbullet
                'join',  # Join
                'notifico',  # Notifico
                'pushsafer',  # Pushsafer
                'telegram'  # Telegram (兼容)
            ]
            return services
        except Exception as e:
            logging.error(f"获取支持服务列表失败: {e}")
            return []

    async def test_connection(self, urls: List[str]) -> Dict[str, Any]:
        """测试推送连接"""
        try:
            test_title = "JJZ-Alert 连接测试"
            test_body = f"这是一条测试消息，发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            result = await self.send_notification(
                urls=urls,
                title=test_title,
                body=test_body
            )

            result['test'] = True
            return result

        except Exception as e:
            logging.error(f"Apprise连接测试失败: {e}")
            return {
                'success': False,
                'test': True,
                'error': str(e)
            }


class AppriseConfig:
    """Apprise配置辅助类"""

    @staticmethod
    def bark_url(device_key: str, server: str = "api.day.app", **params) -> str:
        """生成Bark URL"""
        url = f"bark://{device_key}@{server}"
        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{param_str}"
        return url

    @staticmethod
    def telegram_url(bot_token: str, chat_id: str, **params) -> str:
        """生成Telegram URL"""
        url = f"tgram://{bot_token}/{chat_id}"
        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{param_str}"
        return url

    @staticmethod
    def email_url(
            user: str,
            password: str,
            smtp_server: str = "smtp.gmail.com",
            port: int = 587,
            to_email: Optional[str] = None,
            **params
    ) -> str:
        """生成Email URL"""
        if to_email:
            url = f"mailto://{user}:{password}@{smtp_server}:{port}/{to_email}"
        else:
            url = f"mailto://{user}:{password}@{smtp_server}:{port}"

        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{param_str}"
        return url

    @staticmethod
    def wxwork_url(key: str, **params) -> str:
        """生成企业微信URL"""
        url = f"wxwork://{key}"
        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{param_str}"
        return url

    @staticmethod
    def dingding_url(token: str, secret: Optional[str] = None, **params) -> str:
        """生成钉钉URL"""
        if secret:
            url = f"dingding://{token}/{secret}"
        else:
            url = f"dingding://{token}"

        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{param_str}"
        return url

    @staticmethod
    def webhook_url(url: str, method: str = "POST", **params) -> str:
        """生成Webhook URL"""
        webhook_url = f"json://{url}"
        if method.upper() != "POST":
            params['method'] = method.upper()

        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            webhook_url += f"?{param_str}"
        return webhook_url


# 全局Apprise推送器实例
apprise_pusher = ApprisePusher()
