import os
import logging
import requests
from typing import Dict
from datetime import datetime
# manager.py 文件顶部添加
from notion_client import Client

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, notion_client=None):
        self.nanobot_url = os.getenv('NANOBOT_URL')
        self.notion = Client(auth=os.getenv('NOTION_TOKEN'))  # 自己初始化 Notion
        logger.info("通知管理器初始化完成（Lark + Notion）")

    async def initialize(self):
        logger.info("NotificationManager 初始化完成")
        return True

    async def close(self):
        logger.info("NotificationManager 已关闭")
        return True

    async def send_to_nanobot(self, prompt: str):
        """发送给 nanobot 处理（生成总结并推 Lark）"""
        if not self.nanobot_url:
            logger.warning("NANOBOT_URL 未配置")
            return None

        try:
            response = requests.post(
                f"{self.nanobot_url}/trigger",
                json={"prompt": prompt},
                timeout=15
            )
            response.raise_for_status()
            logger.info("✅ 已成功发送给 nanobot")
            return response.json() if response.headers.get('content-type') == 'application/json' else response.text
        except Exception as e:
            logger.error(f"发送给 nanobot 失败: {e}")
            return None

    async def write_summary_to_notion(self, summary_text: str, date_str: str):
        """把 nanobot 生成的总结回写到 Notion"""
        if not self.notion:
            logger.warning("Notion client 未传入，无法回写总结")
            return

        try:
            self.notion.pages.create(
                parent={"database_id": os.getenv('NOTION_DB_ID')},
                properties={
                    "Date": {"date": {"start": date_str}},
                    "Type": {"select": {"name": "每日总结"}},
                    "Content": {"rich_text": [{"text": {"content": summary_text}}]},
                    "Profit": {"number": 0},  # 可后续填充
                    "Exchange": {"select": {"name": "Summary"}}
                }
            )
            logger.info("每日总结已回写到 Notion")
        except Exception as e:
            logger.error(f"回写 Notion 总结失败: {e}")
