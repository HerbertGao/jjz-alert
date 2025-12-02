"""
Apprise多通道推送服务

支持80+推送服务，包括Bark、Telegram、微信、钉钉等
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any

import apprise


class ApprisePusher:
    """Apprise推送器"""

    def __init__(self):
        self.apprise_instance = None
        # 兼容旧逻辑的属性占位；实际发送时改为每次调用使用独立实例，避免并发污染

    def _init_apprise(self):
        """（保留以兼容）初始化Apprise实例。注意：发送时不复用该实例。"""
        try:
            self.apprise_instance = apprise.Apprise()
            return self.apprise_instance is not None
        except Exception as e:
            logging.error(f"Apprise实例初始化失败: {e}")
            self.apprise_instance = None
            return False

    async def send_notification(
        self, urls: List[str], title: str, body: str, **kwargs
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
            # 使用传入的标题
            final_title = title

            # 为本次发送创建独立的Apprise实例，避免并发时共享实例被clear()/add()互相影响
            apobj = apprise.Apprise()

            # 添加URL配置并记录结果（基于本地实例）
            valid_urls = []
            invalid_urls = []
            url_results = []

            for url in urls:
                if apobj.add(url):
                    valid_urls.append(url)
                    url_results.append(
                        {
                            "url": self._mask_url(url),
                            "valid": True,
                            "success": None,  # 将在推送后更新
                        }
                    )
                else:
                    invalid_urls.append(url)
                    url_results.append(
                        {
                            "url": self._mask_url(url),
                            "valid": False,
                            "success": False,
                            "error": "URL格式无效",
                        }
                    )
                    logging.warning(f"Apprise URL无效: {self._mask_url(url)}")

            if not valid_urls:
                return {
                    "success": False,
                    "error": "没有有效的推送URL",
                    "valid_urls": 0,
                    "invalid_urls": len(invalid_urls),
                    "url_results": url_results,
                }

            # 执行推送
            start_time = datetime.now()

            # 添加详细的推送参数日志
            logging.debug(f"[APPRISE_DEBUG] 准备推送 - 标题: {final_title}")
            logging.debug(
                f"[APPRISE_DEBUG] 推送内容: {body[:100]}..."
            )  # 只显示前100字符
            logging.debug(f"[APPRISE_DEBUG] 推送参数: {kwargs}")
            logging.debug(f"[APPRISE_DEBUG] 有效URL数量: {len(valid_urls)}")

            # 在线程池中执行同步的Apprise推送
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, apobj.notify, body, final_title)

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # 更新有效URL的推送结果
            for url_result in url_results:
                if url_result["valid"]:
                    url_result["success"] = success

            result = {
                "success": success,
                "title": final_title,
                "body": body,
                "valid_urls": len(valid_urls),
                "invalid_urls": len(invalid_urls),
                "duration_ms": round(duration_ms, 2),
                "timestamp": end_time.isoformat(),
                "url_results": url_results,
            }

            if success:
                logging.info(
                    f"Apprise推送成功: {len(valid_urls)}个通道, 耗时{duration_ms:.0f}ms"
                )
            else:
                logging.error(f"Apprise推送失败: {len(valid_urls)}个通道")
                result["error"] = "Apprise推送执行失败"

            return result

        except Exception as e:
            logging.error(f"Apprise推送异常: {e}")
            return {
                "success": False,
                "error": str(e),
                "valid_urls": 0,
                "invalid_urls": len(urls),
                "url_results": [],
            }

    def _mask_url(self, url: str) -> str:
        """遮蔽URL中的敏感信息"""
        try:
            # 简单的URL遮蔽，隐藏token等敏感信息
            if "://" in url:
                scheme, rest = url.split("://", 1)
                if "/" in rest:
                    host_part, path_part = rest.split("/", 1)
                    # 只显示前几个字符
                    if len(path_part) > 8:
                        masked_path = path_part[:4] + "****" + path_part[-4:]
                    else:
                        masked_path = "****"
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
                return {"valid": [], "invalid": urls, "error": "Apprise实例初始化失败"}

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
                "valid": valid_urls,
                "invalid": invalid_urls,
                "total": len(urls),
                "valid_count": len(valid_urls),
                "invalid_count": len(invalid_urls),
            }

        except Exception as e:
            logging.error(f"URL验证失败: {e}")
            return {"valid": [], "invalid": urls, "error": str(e)}

    async def test_connection(self, urls: List[str]) -> Dict[str, Any]:
        """测试推送连接"""
        try:
            test_title = "JJZ-Alert 连接测试"
            test_body = f"这是一条测试消息，发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            result = await self.send_notification(
                urls=urls, title=test_title, body=test_body
            )

            result["test"] = True
            return result

        except Exception as e:
            logging.error(f"Apprise连接测试失败: {e}")
            return {"success": False, "test": True, "error": str(e)}


# 全局Apprise推送器实例
apprise_pusher = ApprisePusher()
