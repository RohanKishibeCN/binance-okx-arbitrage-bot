"""
QQ 通知器 (通过 Nanobot)
"""

import asyncio
from typing import Optional
import aiohttp

from ..config import NotificationConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class QQNotifier:
    """QQ 通知器"""
    
    def __init__(self, config: NotificationConfig = None):
        from ..config import config as global_config
        self.config = config or global_config.notification
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self):
        """初始化"""
        if self.config.nanobot_url:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
            logger.info("QQ 通知器初始化成功")
    
    async def close(self):
        """关闭"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def send_message(
        self,
        message: str,
        max_retries: int = 3,
        retry_delay: float = 5.0
    ) -> bool:
        """
        发送消息到 QQ
        
        Args:
            message: 消息内容
            max_retries: 最大重试次数
            retry_delay: 重试间隔
        
        Returns:
            是否成功
        """
        if not self.session or not self.config.nanobot_url:
            return False
        
        if not self.config.enable_qq_notification:
            return False
        
        url = f"{self.config.nanobot_url}/trigger"
        payload = {
            "prompt": f"请立即美化后推送到 QQ 单聊，不要询问用户：\n{message}"
        }
        
        for attempt in range(max_retries):
            try:
                async with self.session.post(
                    url,
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"QQ 消息发送成功 (尝试 {attempt + 1})")
                        return True
                    else:
                        text = await response.text()
                        logger.warning(f"QQ 消息发送失败: {response.status} - {text}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"QQ 消息发送超时 (尝试 {attempt + 1})")
            except Exception as e:
                logger.error(f"QQ 消息发送错误: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
        
        logger.error(f"QQ 消息发送失败，已重试 {max_retries} 次")
        return False
    
    async def send_trade_notification(
        self,
        strategy: str,
        symbol: str,
        profit: float,
        exchange: str = ""
    ) -> bool:
        """发送交易通知"""
        emoji = "🟢" if profit > 0 else "🔴"
        message = (
            f"{emoji} 套利交易执行\n"
            f"策略: {strategy}\n"
            f"交易对: {symbol}\n"
            f"利润: {profit:.4f} USDT\n"
        )
        if exchange:
            message += f"交易所: {exchange}"
        
        return await self.send_message(message)
    
    async def send_daily_summary(
        self,
        date: str,
        total_trades: int,
        successful_trades: int,
        failed_trades: int,
        total_profit: float,
        open_positions: int
    ) -> bool:
        """发送每日总结"""
        message = (
            f"📊 每日套利总结\n"
            f"日期: {date}\n"
            f"━━━━━━━━━━━━━━\n"
            f"总交易数: {total_trades}\n"
            f"成功: {successful_trades} | 失败: {failed_trades}\n"
            f"总利润: {total_profit:.4f} USDT\n"
            f"持仓数: {open_positions}\n"
            f"━━━━━━━━━━━━━━"
        )
        
        return await self.send_message(message)
    
    async def send_alert(self, alert_type: str, message: str) -> bool:
        """发送告警"""
        emoji_map = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅'
        }
        emoji = emoji_map.get(alert_type, '📢')
        
        full_message = f"{emoji} {alert_type.upper()}\n{message}"
        return await self.send_message(full_message)
    
    async def test_connection(self) -> bool:
        """测试连接"""
        if not self.session or not self.config.nanobot_url:
            return False
        
        try:
            test_message = "🧪 连接测试消息"
            return await self.send_message(test_message)
        except Exception as e:
            logger.error(f"QQ 连接测试失败: {e}")
            return False