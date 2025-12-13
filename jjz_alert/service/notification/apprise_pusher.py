"""
Apprise多通道推送服务

支持80+推送服务，包括Bark、Telegram、微信、钉钉等
"""

import asyncio
import logging
import re
from datetime import datetime
from functools import partial
from typing import List, Dict, Any, Tuple, Optional

import apprise

# 预编译正则表达式以提高性能
# 用于识别可能是token/key的长字符串的最小长度阈值
TOKEN_MIN_LENGTH = 20
_TOKEN_PATTERN = re.compile(rf"\b[a-zA-Z0-9_-]{{{TOKEN_MIN_LENGTH},}}\b")


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
            推送结果字典，包含以下字段：
            - success (bool): 整体是否成功（至少一个通道成功则为True）
            - partial_success (bool): 是否部分成功（有成功但不是全部成功）
            - title (str): 推送标题
            - body (str): 推送内容
            - valid_urls (int): 有效URL数量
            - invalid_urls (int): 无效URL数量
            - duration_ms (float): 推送耗时（毫秒）
            - timestamp (str): 完成时间（ISO格式）
            - url_results (List[Dict]): 每个URL的推送结果详情
            - error (str, optional): 错误信息（如果有）
        """
        try:
            # 使用传入的标题
            final_title = title

            # 为本次发送创建独立的Apprise实例，避免并发时共享实例被clear()/add()互相影响
            apobj = apprise.Apprise()

            # 添加URL配置并记录结果（基于本地实例）
            # 存储 (url, masked_url) 元组以避免重复调用 _mask_url()
            valid_url_data = []  # List[(str, str)]
            invalid_urls = []
            url_results = []

            for url in urls:
                # 添加输入验证：跳过 None 或空字符串
                if not url or not isinstance(url, str):
                    logging.warning(f"跳过无效URL类型: {type(url).__name__}")
                    invalid_urls.append(url if url else "<empty>")
                    url_results.append(
                        {
                            "url": "****",
                            "valid": False,
                            "success": False,
                            "error": "URL为空或类型无效",
                        }
                    )
                    continue

                # 预计算遮蔽后的URL，避免多次调用 _mask_url()
                masked_url = self._mask_url(url)
                if apobj.add(url):
                    valid_url_data.append((url, masked_url))
                    url_results.append(
                        {
                            "url": masked_url,
                            "valid": True,
                            "success": None,  # 将在推送后更新
                        }
                    )
                else:
                    invalid_urls.append(url)
                    url_results.append(
                        {
                            "url": masked_url,
                            "valid": False,
                            "success": False,
                            "error": "URL格式无效",
                        }
                    )
                    logging.warning(f"Apprise URL无效: {masked_url}")

            if not valid_url_data:
                return {
                    "success": False,
                    "partial_success": False,
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
            logging.debug(f"[APPRISE_DEBUG] 有效URL数量: {len(valid_url_data)}")

            # 为了获取每个URL的详细推送结果，我们需要单独发送每个URL
            # Apprise的notify()和async_notify()都只返回全局布尔值，无法区分每个URL的状态
            # 使用 asyncio.gather() 并行发送所有URL，保持性能的同时获取准确结果
            loop = asyncio.get_running_loop()

            # 为每个有效URL创建推送任务
            async def send_single_url(
                url: str, masked_url: str, msg_body: str, msg_title: str
            ) -> Tuple[bool, Optional[str]]:
                """
                发送单个URL的推送

                Args:
                    url: 原始URL
                    masked_url: 遮蔽后的URL（用于日志）
                    msg_body: 推送内容
                    msg_title: 推送标题

                Returns:
                    Tuple[bool, Optional[str]]: (是否成功, 错误信息)
                """
                try:
                    # 为每个URL创建独立的Apprise实例
                    # 原因：Apprise的notify()只返回全局布尔值，无法区分每个URL的推送状态
                    # 通过为每个URL创建独立实例，我们可以获取准确的单个URL推送结果
                    # 权衡：虽然会有一定资源开销，但换来了准确的错误追踪和部分成功处理能力
                    # 注：目前功能并发量不会超过10，未来遇到性能瓶颈再优化
                    single_apobj = apprise.Apprise()
                    single_apobj.add(url)

                    # 在线程池中执行推送（notify是同步方法）
                    # 使用 functools.partial 避免lambda闭包问题
                    push_result = await loop.run_in_executor(
                        None,
                        partial(single_apobj.notify, msg_body, title=msg_title),
                    )
                    return (push_result, None)
                except Exception as exc:
                    # 记录异常类型和详细信息，包含堆栈跟踪便于调试
                    error_msg = f"推送异常: {type(exc).__name__}: {str(exc)}"
                    # 清理日志中的敏感信息（URL已经遮蔽，但异常信息可能包含敏感数据）
                    sanitized_log_msg = self._sanitize_error_message(error_msg, url)
                    logging.warning(
                        f"URL {masked_url} {sanitized_log_msg}", exc_info=True
                    )
                    return (False, error_msg)

            # 为每个有效URL创建推送任务，使用缓存的 masked_url
            push_tasks = [
                send_single_url(url, masked_url, body, final_title)
                for url, masked_url in valid_url_data
            ]
            # 使用 return_exceptions=True 确保一个URL失败不会影响其他URL
            push_results = await asyncio.gather(*push_tasks, return_exceptions=True)

            # 验证结果数量与URL数量匹配（防御性编程）
            # 使用 RuntimeError 而不是 assert，确保在 Python -O 模式下也能捕获错误
            if len(push_results) != len(valid_url_data):
                raise RuntimeError(
                    f"推送结果数量({len(push_results)})与有效URL数量({len(valid_url_data)})不匹配"
                )

            # 更新url_results中有效URL的推送结果
            # 由于url_results和valid_url_data都保持了原始URLs的顺序，可以用索引直接对应
            success_count = 0
            valid_index = 0
            for url_result in url_results:
                if url_result["valid"]:
                    # 从valid_url_data和push_results中获取对应的结果
                    orig_url, cached_masked_url = valid_url_data[valid_index]
                    result = push_results[valid_index]
                    valid_index += 1

                    # 处理 gather() 的 return_exceptions=True 可能返回的 Exception 实例
                    if isinstance(result, Exception):
                        url_result["success"] = False
                        error_msg = f"推送异常: {type(result).__name__}: {str(result)}"
                        sanitized_error = self._sanitize_error_message(
                            error_msg, orig_url
                        )
                        url_result["error"] = sanitized_error
                        # 清理日志中的敏感信息
                        logging.error(
                            f"URL {cached_masked_url} 推送失败: {sanitized_error}"
                        )
                    else:
                        push_success, error_msg = result
                        url_result["success"] = push_success
                        if error_msg:
                            # 清理错误消息中的敏感信息
                            url_result["error"] = self._sanitize_error_message(
                                error_msg, orig_url
                            )
                        if push_success:
                            success_count += 1

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # 整体成功标志：至少有一个URL推送成功
            success = success_count > 0
            # 部分成功标志：有成功但不是全部成功
            partial_success = 0 < success_count < len(valid_url_data)

            result = {
                "success": success,
                "partial_success": partial_success,
                "title": final_title,
                "body": body,
                "valid_urls": len(valid_url_data),
                "invalid_urls": len(invalid_urls),
                "duration_ms": round(duration_ms, 2),
                "timestamp": end_time.isoformat(),
                "url_results": url_results,
            }

            if success:
                logging.info(
                    f"Apprise推送完成: {success_count}/{len(valid_url_data)}个通道成功, 耗时{duration_ms:.0f}ms"
                )
            else:
                logging.error(
                    f"Apprise推送失败: 0/{len(valid_url_data)}个通道成功, 耗时{duration_ms:.0f}ms"
                )
                result["error"] = "Apprise推送执行失败"

            return result

        except Exception as e:
            # 清理顶层异常消息中的敏感信息
            sanitized_error = self._sanitize_error_message(str(e), "")
            logging.error(f"Apprise推送异常: {sanitized_error}")
            return {
                "success": False,
                "partial_success": False,
                "error": sanitized_error,
                "valid_urls": 0,
                "invalid_urls": len(urls),
                "url_results": [],
            }

    def _mask_url(self, url: str) -> str:
        """
        遮蔽URL中的敏感信息

        策略：
        1. scheme (://之前) 保持完整
        2. 其余部分用 @ 和 / 分隔，对每个部分：
           - 长度 >= 3：显示前3字符 + "****"
           - 长度 < 3：全部显示为 "****"

        Examples:
            "bark://token@api.day.app/device" -> "bark://tok****@api****/dev****"
            "smtp://ab@x/y" -> "smtp://****@****/****"
        """
        try:
            if not url or not isinstance(url, str):
                return "****"

            # 提取 scheme
            if "://" in url:
                scheme, rest = url.split("://", 1)
                scheme_part = scheme + "://"
            else:
                # 没有 scheme，整个URL遮蔽
                rest = url
                scheme_part = ""

            # 使用正则分割 rest，保留分隔符 @ 和 /
            # 分割并保留分隔符
            parts = re.split(r"([@/])", rest)

            # 遮蔽每个非分隔符部分
            masked_parts = []
            for part in parts:
                if part in ["@", "/"]:  # 分隔符保持原样
                    masked_parts.append(part)
                elif part:  # 非空部分需要遮蔽
                    if len(part) >= 3:
                        masked_parts.append(part[:3] + "****")
                    else:
                        masked_parts.append("****")

            return scheme_part + "".join(masked_parts)
        except Exception:
            return "****"

    def _sanitize_error_message(self, error_msg: str, url: str) -> str:
        """
        清理错误消息中可能包含的敏感信息

        Args:
            error_msg: 原始错误消息
            url: 相关的URL（用于识别需要遮蔽的部分）

        Returns:
            清理后的错误消息
        """
        try:
            # 处理None和空字符串
            if error_msg is None:
                return "推送异常（错误详情已隐藏）"
            if not error_msg:
                return error_msg  # 返回空字符串

            sanitized = error_msg

            # 遮蔽URL中的敏感部分（如果错误消息包含URL）
            # 注意：必须检查url非空，否则空字符串会匹配所有字符导致消息损坏
            if url and url in sanitized:
                sanitized = sanitized.replace(url, self._mask_url(url))

            # 尝试遮蔽可能的token/key（通常是长字符串）
            # 匹配可能是token的长字符串（20+字符的字母数字组合）
            sanitized = _TOKEN_PATTERN.sub(lambda m: m.group(0)[:4] + "****", sanitized)

            return sanitized
        except Exception:
            # 如果清理失败，返回通用错误消息
            return "推送异常（错误详情已隐藏）"

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
