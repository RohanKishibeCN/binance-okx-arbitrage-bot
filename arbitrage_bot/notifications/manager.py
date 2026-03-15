"""
通知管理器
统一管理所有通知渠道
"""

import asyncio
from typing import List, Optional
from datetime import datetime

from .notion import NotionNotifier
from .qq import QQNotifier
from ..config import NotificationConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NotificationManager:
    """通知管理器"""
    
    def __init__(self, config: NotificationConfig = None):
        from ..config import config as global_config
        self.config = config or global_config.notification
        
        self.notion = NotionNotifier(self.config)
        self.qq = QQNotifier(self.config)
        
    async def initialize(self):
        """初始化所有通知渠道"""
        await self.qq.initialize()
        logger.info("通知管理器初始化完成")
    
    async def close(self):
        """关闭所有通知渠道"""
        await self.qq.close()
        logger.info("通知管理器已关闭")
    
    async def notify_trade(
        self,
        strategy: str,
        symbol: str,
        profit: float,
        exchange: str = "",
        details: str = "",
        notify_qq: bool = True,
        notify_notion: bool = True
    ):
        """发送交易通知"""
        tasks = []
        
        if notify_qq:
            tasks.append(
                self.qq.send_trade_notification(strategy, symbol, profit, exchange)
            )
        
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
        
        # 发送到 QQ
        await self.qq.send_daily_summary(
            date=date_str,
            total_trades=total_trades,
            successful_trades=successful_trades,
            failed_trades=failed_trades,
            total_profit=total_profit,
            open_positions=open_positions
        )
    
    async def notify_error(
        self,
        error_type: str,
        error_message: str,
        context: str = "",
        notify_qq: bool = True,
        notify_notion: bool = True
    ):
        """发送错误通知"""
        if notify_notion:
            await self.notion.write_error(error_type, error_message, context)
        
        if notify_qq:
            full_message = f"错误类型: {error_type}\n"
            if context:
                full_message += f"上下文: {context}\n"
            full_message += f"错误信息: {error_message}"
            await self.qq.send_alert('error', full_message)
    
    async def notify_alert(
        self,
        alert_type: str,
        message: str,
        notify_qq: bool = True
    ):
        """发送告警"""
        if notify_qq:
            await self.qq.send_alert(alert_type, message)
    
    async def test_connections(self) -> dict:
        """测试所有通知连接"""
        results = {
            'notion': await self.notion.test_connection(),
            'qq': await self.qq.test_connection()
        }
        return results