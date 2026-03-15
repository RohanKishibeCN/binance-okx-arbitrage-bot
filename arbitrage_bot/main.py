"""
套利机器人主入口
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import List

from .config import config
from .exchanges import BinanceExchange, OKXExchange
from .strategies import TriangularArbitrage, CrossExchangeArbitrage
from .risk import RiskManager
from .notifications import NotificationManager
from .utils.logger import setup_logger, get_logger

# 设置日志
setup_logger()
logger = get_logger(__name__)


class ArbitrageBot:
    """套利机器人"""
    
    def __init__(self):
        self.binance: BinanceExchange = None
        self.okx: OKXExchange = None
        self.risk_manager: RiskManager = None
        self.notification_manager: NotificationManager = None
        
        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.last_summary_date: datetime = None
        
    async def initialize(self):
        """初始化机器人"""
        logger.info("=" * 50)
        logger.info("🚀 套利机器人启动中...")
        logger.info("=" * 50)
        
        # 打印配置
        logger.info(f"DRY_RUN: {config.trading.dry_run}")
        logger.info(f"最小利润率: {config.trading.min_profit_threshold:.4%}")
        logger.info(f"交易金额: {config.trading.trade_amount_usdt} USDT")
        logger.info(f"手续费率: {config.trading.fee_rate:.4%}")
        
        # 初始化交易所
        self.binance = BinanceExchange()
        self.okx = OKXExchange()
        
        await self.binance.initialize()
        await self.okx.initialize()
        
        # 初始化风控
        self.risk_manager = RiskManager()
        await self.risk_manager.start()
        
        # 初始化通知
        self.notification_manager = NotificationManager()
        await self.notification_manager.initialize()
        
        # 测试通知连接
        connection_results = await self.notification_manager.test_connections()
        logger.info(f"通知连接状态: {connection_results}")
        
        logger.info("✅ 套利机器人初始化完成")
        
    async def run(self):
        """运行机器人"""
        self.running = True
        
        # 创建策略任务
        # 1. Binance 三角套利
        binance_triangular = TriangularArbitrage(
            self.binance,
            self.risk_manager
        )
        
        # 2. OKX 三角套利
        okx_triangular = TriangularArbitrage(
            self.okx,
            self.risk_manager
        )
        
        # 3. 跨交易所套利
        cross_exchange = CrossExchangeArbitrage(
            self.binance,
            self.okx,
            self.risk_manager
        )
        
        # 启动所有策略
        self.tasks = [
            asyncio.create_task(binance_triangular.run()),
            asyncio.create_task(okx_triangular.run()),
            asyncio.create_task(cross_exchange.run()),
            asyncio.create_task(self._daily_summary_loop()),
            asyncio.create_task(self._health_check_loop()),
        ]
        
        logger.info("🤖 所有策略已启动")
        
        # 等待所有任务
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("任务被取消")
        except Exception as e:
            logger.error(f"运行错误: {e}", exc_info=True)
    
    async def stop(self):
        """停止机器人"""
        logger.info("🛑 正在停止套利机器人...")
        self.running = False
        
        # 取消所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务完成
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # 关闭组件
        if self.risk_manager:
            await self.risk_manager.stop()
        
        if self.notification_manager:
            await self.notification_manager.close()
        
        if self.binance:
            await self.binance.close()
        
        if self.okx:
            await self.okx.close()
        
        logger.info("✅ 套利机器人已停止")
    
    async def _daily_summary_loop(self):
        """每日总结循环"""
        while self.running:
            try:
                now = datetime.now()
                
                # 每天 23:00 发送总结
                if now.hour == 23 and now.minute == 0:
                    if self.last_summary_date != now.date():
                        self.last_summary_date = now.date()
                        await self._send_daily_summary()
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"每日总结循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _send_daily_summary(self):
        """发送每日总结"""
        try:
            stats = self.risk_manager.get_stats()
            
            await self.notification_manager.notify_daily_summary(
                date=datetime.now(),
                total_trades=stats['total_trades'],
                successful_trades=stats['successful_trades'],
                failed_trades=stats['failed_trades'],
                total_profit=stats['daily_pnl'],
                open_positions=stats['open_positions']
            )
            
            logger.info("每日总结已发送")
            
        except Exception as e:
            logger.error(f"发送每日总结失败: {e}")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.running:
            try:
                # 检查交易所连接
                if not self.binance.is_connected():
                    logger.warning("Binance 连接断开，尝试重连...")
                    await self.binance.initialize()
                
                if not self.okx.is_connected():
                    logger.warning("OKX 连接断开，尝试重连...")
                    await self.okx.initialize()
                
                # 打印风控统计
                stats = self.risk_manager.get_stats()
                logger.info(
                    f"风控状态: 当日盈亏={stats['daily_pnl']:.4f} USDT, "
                    f"交易数={stats['daily_trades']}, "
                    f"持仓={stats['open_positions']}"
                )
                
                await asyncio.sleep(300)  # 每5分钟检查一次
                
            except Exception as e:
                logger.error(f"健康检查错误: {e}")
                await asyncio.sleep(300)


async def main():
    """主函数"""
    bot = ArbitrageBot()
    
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("收到终止信号")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"程序错误: {e}", exc_info=True)
        await bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())