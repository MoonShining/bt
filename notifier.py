"""
通知模块
支持通过 Server酱 发送微信通知
"""

import os
import requests
from typing import Optional, List


class Notifier:
    """通知器基类"""

    def send(self, title: str, content: str) -> bool:
        raise NotImplementedError


class ServerChan(Notifier):
    """
    Server酱 (https://sct.ftqq.com)
    用于发送微信通知
    """

    def __init__(self, send_key: str):
        """
        Args:
            send_key: Server酱的 Send Key，从环境变量获取
        """
        self.send_key = send_key
        self.api_url = f"https://sctapi.ftqq.com/{self.send_key}.send"

    def send(self, title: str, content: str) -> bool:
        """
        发送微信通知
        Args:
            title: 通知标题
            content: 通知内容（支持 Markdown）
        """
        if not self.send_key:
            print("未配置 Server酱 Send Key，跳过通知")
            return False

        try:
            response = requests.get(
                self.api_url,
                params={"title": title, "desp": content},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    print(f"微信通知发送成功: {title}")
                    return True
                else:
                    print(f"Server酱返回错误: {result}")
                    return False
            else:
                print(f"Server酱 HTTP 错误: {response.status_code}")
                return False
        except Exception as e:
            print(f"微信通知发送失败: {e}")
            return False


class ConsoleNotifier(Notifier):
    """控制台通知器（用于测试和调试）"""

    def send(self, title: str, content: str) -> bool:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}\n")
        return True

def create_notifier(send_key: Optional[str] = None) -> Notifier:
    """
    根据环境变量自动创建通知器
    优先使用 Server酱，未配置则使用控制台
    Args:
        send_key: Server酱的 Send Key（可选，未提供则从环境变量读取）
    """
    if send_key:
        return ServerChan(send_key)
    else:
        print("未配置 WECHAT_SEND_KEY 环境变量，使用控制台通知")
        return ConsoleNotifier()
