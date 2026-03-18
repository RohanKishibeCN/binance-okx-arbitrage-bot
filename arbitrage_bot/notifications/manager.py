"""
通知管理器
统一管理所有通知渠道
"""

import asyncio
from typing import List, Optional
from datetime import datetime

from .notion import NotionNotifier
# from .qq import QQNotifier
from ..config import NotificationConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NotificationManager:
    """通知管理器"""
    
    def __init__(self):
        """初始化通知管理器（只保留 Lark/nanobot）"""
        self.nanobot_url = os.getenv('NANOBOT_URL')
        logger.info("通知管理器初始化完成（已切换到 Lark）")
        
    async def initialize(self):
        """初始化所有通知渠道"""
        # await self.qq.initialize()
        logger.info("通知管理器初始化完成")
    
    async def close(self):
        """关闭所有通知渠道"""
        # await self.qq.close()
        logger.info("通知管理器已关闭")
    
    async def notify_trade(
        self,
        strategy: str,
        symbol: str,
        profit: float,
        exchange: str = "",
        details: str = "",
        notify_notion: bool = True
    ):
        """发送交易通知"""
        tasks = []
        
        if notify_notion:
            tasks.append(
                self.notion.write_trade(
                    trade_type="交易明细",
                    content=details or f"{strategy} - {symbol}",
                    profit=profit,
                    exchange=exchange,
                    extra_data={
                        'symbol': symbol,
                        'strategy': strategy
                    }
                )
            )
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"通知发送失败: {result}")
    
    async def notify_daily_summary(
        self,
        date: datetime,
        total_trades: int,
        successful_trades: int,
        failed_trades: int,
        total_profit: float,
        open_positions: int,
        details: str = ""
    ):
        """发送每日总结"""
        date_str = date.strftime("%Y-%m-%d")
        
        # 发送到 Notion
        await self.notion.write_daily_summary(
            date=date,
            total_trades=total_trades,
            successful_trades=successful_trades,
            total_profit=total_profit,
            details=details
        )
        
    
    async def notify_error(
        self,
        error_type: str,
        error_message: str,
        context: str = "",
        notify_notion: bool = True
    ):
        """发送错误通知"""
        if notify_notion:
            await self.notion.write_error(error_type, error_message, context)
        
    
    async def notify_alert(
        self,
        alert_type: str,
        message: str,
    ):
    
    async def test_connections(self) -> dict:
        """测试所有通知连接"""
        results = {
            'notion': await self.notion.test_connection(),
        }
        return results
