"""
Notion 通知器
"""

from datetime import datetime
from typing import Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from ..config import NotificationConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NotionNotifier:
    """Notion 通知器"""
    
    def __init__(self, config: NotificationConfig = None):
        from ..config import config as global_config
        self.config = config or global_config.notification
        
        self.client: Optional[Client] = None
        if self.config.notion_token and self.config.notion_db_id:
            try:
                self.client = Client(auth=self.config.notion_token)
                logger.info("Notion 客户端初始化成功")
            except Exception as e:
                logger.error(f"Notion 客户端初始化失败: {e}")
    
    async def write_trade(
        self,
        trade_type: str,
        content: str,
        profit: float = 0,
        exchange: str = "Summary",
        extra_data: dict = None
    ) -> bool:
        """
        写入交易记录
        
        Args:
            trade_type: 交易类型 (交易明细, 每日总结, 错误日志等)
            content: 内容
            profit: 利润
            exchange: 交易所
            extra_data: 额外数据
        
        Returns:
            是否成功
        """
        if not self.client or not self.config.enable_notion_logging:
            return False
        
        try:
            properties = {
                "Date": {
                    "date": {
                        "start": datetime.now().isoformat()
                    }
                },
                "Type": {
                    "select": {
                        "name": trade_type
                    }
                },
                "Content": {
                    "rich_text": [{
                        "text": {
                            "content": content[:2000]
                        }
                    }]
                },
                "Profit": {
                    "number": round(float(profit), 4)
                },
                "Exchange": {
                    "select": {
                        "name": exchange
                    }
                }
            }
            
            # 添加额外字段
            if extra_data:
                if 'symbol' in extra_data:
                    properties["Symbol"] = {
                        "rich_text": [{
                            "text": {
                                "content": extra_data['symbol']
                            }
                        }]
                    }
                
                if 'strategy' in extra_data:
                    properties["Strategy"] = {
                        "select": {
                            "name": extra_data['strategy']
                        }
                    }
            
            self.client.pages.create(
                parent={"database_id": self.config.notion_db_id},
                properties=properties
            )
            
            logger.debug(f"Notion 写入成功: {trade_type} ({exchange})")
            return True
            
        except APIResponseError as e:
            logger.error(f"Notion API 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"Notion 写入失败: {e}")
            return False
    
    async def write_daily_summary(
        self,
        date: datetime,
        total_trades: int,
        successful_trades: int,
        total_profit: float,
        details: str
    ) -> bool:
        """写入每日总结"""
        content = (
            f"📊 每日套利总结\n"
            f"日期: {date.date()}\n"
            f"总交易数: {total_trades}\n"
            f"成功交易: {successful_trades}\n"
            f"总利润: {total_profit:.4f} USDT\n"
            f"\n详情:\n{details}"
        )
        
        return await self.write_trade(
            trade_type="每日总结",
            content=content,
            profit=total_profit,
            exchange="Summary"
        )
    
    async def write_error(self, error_type: str, error_message: str, context: str = "") -> bool:
        """写入错误日志"""
        content = f"错误类型: {error_type}\n"
        if context:
            content += f"上下文: {context}\n"
        content += f"错误信息: {error_message}"
        
        return await self.write_trade(
            trade_type="错误日志",
            content=content,
            exchange="System"
        )
    
    async def test_connection(self) -> bool:
        """测试连接"""
        if not self.client:
            return False
        
        try:
            # 尝试获取数据库信息
            self.client.databases.retrieve(self.config.notion_db_id)
            return True
        except Exception as e:
            logger.error(f"Notion 连接测试失败: {e}")
            return False