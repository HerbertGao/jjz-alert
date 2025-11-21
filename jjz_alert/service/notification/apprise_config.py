"""
Apprise配置辅助类
"""

from typing import Optional


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
        **params,
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
            params["method"] = method.upper()

        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            webhook_url += f"?{param_str}"
        return webhook_url
