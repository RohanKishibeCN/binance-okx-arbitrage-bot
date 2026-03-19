import os
import logging
import requests
from typing import Dict, Optional
from datetime import datetime
from notion_client import Client

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, notion_client=None):
        self.nanobot_url = os.getenv('NANOBOT_URL')
        self.notion_db_id = os.getenv('NOTION_DB_ID')
        
        # 创建 Notion 客户端
        if notion_client:
            self.notion = notion_client
        else:
            token = os.getenv('NOTION_TOKEN')
            if token:
                self.notion = Client(auth=token)
            else:
                self.notion = None
                logger.warning("NOTION_TOKEN 未设置")
        
        logger.info("通知管理器初始化完成（Lark + Notion）")

    async def initialize(self):
        """初始化"""
        logger.info("NotificationManager 初始化完成")
        return True

    async def close(self):
        """关闭"""
        logger.info("NotificationManager 已关闭")
        return True

    async def test_connections(self):
        """测试所有通知连接"""
        results = {'notion': False, 'nanobot': False}
        
        # 测试 Notion
        try:
            if self.notion:
                self.notion.users.me()
                results['notion'] = True
                logger.info("✅ Notion 连接测试通过")
        except Exception as e:
            logger.error(f"❌ Notion 连接测试失败: {e}")
        
        # 测试 Nanobot
        try:
            if self.nanobot_url:
                response = requests.get(f"{self.nanobot_url}/health", timeout=5)
                if response.status_code == 200:
                    results['nanobot'] = True
                    logger.info("✅ Nanobot 连接测试通过")
        except Exception as e:
            logger.error(f"❌ Nanobot 连接测试失败: {e}")
            
        return results

    async def write_trade(self, trade_type: str, content: str, profit: float = 0, 
                         exchange: str = "", extra_data: Optional[Dict] = None):
        """
        写入交易记录到 Notion（8点任务用）
        """
        if not self.notion or not self.notion_db_id:
            logger.warning("Notion 未配置，跳过写入")
            return False
            
        try:
            # 构建 properties
            properties = {
                "Type": {"select": {"name": trade_type}},
                "Content": {"rich_text": [{"text": {"content": content[:2000]}}]},
                "Profit": {"number": float(profit)},
                "Exchange": {"select": {"name": exchange or "Unknown"}},
                "Date": {"date": {"start": datetime.now().isoformat()}}
            }
            
            # 如果有额外数据，加到 Content
            if extra_data:
                extra_str = "\n".join([f"{k}: {v}" for k, v in extra_data.items()])
                properties["Content"]["rich_text"][0]["text"]["content"] += f"\n\n{extra_str}"
            
            # 创建页面
            self.notion.pages.create(
                parent={"database_id": self.notion_db_id},
                properties=properties
            )
            logger.info(f"✅ 交易记录已写入 Notion: {trade_type}")
            return True
            
        except Exception as e:
            logger.error(f"写入 Notion 交易记录失败: {e}")
            return False

    async def send_to_nanobot(self, prompt: str):
        """发送给 nanobot（备用，如需要即时推送时用）"""
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
