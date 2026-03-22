# arbitrage_bot/main.py

import asyncio
import signal
import sys
import os
import json
from notion_client import Client
from datetime import datetime, timedelta
from typing import List, Dict

from .config import config
from .exchanges import BinanceExchange, OKXExchange
from .strategies import CrossExchangeArbitrage
from .risk import RiskManager
from .notifications import NotificationManager
from .utils.logger import setup_logger, get_logger

setup_logger()
logger = get_logger(__name__)


class ArbitrageBot:
    def __init__(self):
        self.binance = None
        self.okx = None
        self.risk_manager = None
        self.notification_manager = None
        self.notion_client = Client(auth=os.getenv('NOTION_TOKEN'))
        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.daily_records_sent: datetime = None
        os.makedirs('data', exist_ok=True)

    async def initialize(self):
        """初始化"""
        logger.info("=" * 70)
        logger.info("🚀 套利机器人启动中...")
        logger.info("=" * 70)

        self._print_config()

        # 初始化交易所 - 带重试逻辑
        logger.info("\n📡 初始化交易所连接...")

        max_retries = 5
        retry_delay = 10  # 从10秒开始

        for attempt in range(max_retries):
            try:
        
                self.binance = BinanceExchange()
                self.okx = OKXExchange()
                
                await self.binance.initialize()
                await self.okx.initialize()

                logger.info("\n🛡️ 初始化风控...")
                break

            except Exception as e:
                if "418" in str(e) or "DDoS" in str(e):
                    logger.error(f"⚠️ 交易所限流/IP被封，等待 {retry_delay} 秒后重试... (第{attempt+1}/{max_retries}次)")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避：10s -> 20s -> 40s -> 80s
                else:
                    raise e

        else:
            raise Exception("交易所初始化失败，已达到最大重试次数")

        
        self.risk_manager = RiskManager()
        await self.risk_manager.start()

        logger.info("\n📢 初始化通知...")
        self.notification_manager = NotificationManager(notion_client=self.notion_client)
        await self.notification_manager.initialize()

        logger.info("\n✅ 初始化完成")
        logger.info("=" * 70)

    def _print_config(self):
        """打印配置"""
        cfg = config.print_config()
        logger.info("\n⚙️ 配置信息:")
        logger.info(f" DRY_RUN: {cfg['dry_run']}")
        logger.info(f" 最小利润率: {cfg['min_profit']:.4%}")
        logger.info(f" 交易金额: {cfg['trade_amount']} USDT")
        logger.info(f" Binance: {'✓' if cfg['binance_api_configured'] else '✗'}")
        logger.info(f" OKX: {'✓' if cfg['okx_api_configured'] else '✗'}")
        logger.info(f" Notion: {'✓' if cfg['notion_configured'] else '✗'}")

    async def run(self):
        """运行机器人 - 只保留跨所套利"""
        self.running = True
        cross_exchange = CrossExchangeArbitrage(self.binance, self.okx, self.risk_manager)

        logger.info("\n🤖 启动策略 [跨所套利优先]...")
        self.tasks = [
            asyncio.create_task(cross_exchange.run(), name="Cross-Exchange"),
            asyncio.create_task(self._daily_report_loop(), name="Daily-Report"),
            asyncio.create_task(self._health_check_loop(), name="Health-Check"),
        ]

        logger.info(" ✓ 跨所套利 (20+币种，分层监控)")
        logger.info(" ✗ 三角套利 (已禁用，资源占用高且机会少)")
        logger.info("\n🎯 机器人运行中...")

        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("任务被取消")
        except Exception as e:
            logger.error(f"运行错误: {e}", exc_info=True)

    async def stop(self):
        """停止"""
        logger.info("\n🛑 停止机器人...")
        self.running = False

        for task in self.tasks:
            if not task.done():
                task.cancel()

        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        if self.risk_manager:
            await self.risk_manager.stop()
        if self.notification_manager:
            await self.notification_manager.close()
        if self.binance:
            await self.binance.close()
        if self.okx:
            await self.okx.close()

        logger.info("✅ 已停止")

    async def _daily_report_loop(self):
        """每日报告循环 - UTC时间对应北京时间8点（UTC 00:00）"""
        while self.running:
            try:
                # 获取UTC时间（Railway默认）
                now = datetime.utcnow()
                today = now.date()

                # 早上 8:00 推送交易记录到 Notion
                if now.hour == 0 and now.minute < 5:
                    if self.daily_records_sent != today:
                        self.daily_records_sent = today
                        logger.info("📋 开始生成每日交易记录（北京时间8点）...")
                        try:
                            await self._send_daily_records()
                            logger.info("✅ 每日交易记录已发送")
                        except Exception as e:
                            logger.error(f"❌ 发送失败: {e}", exc_info=True)
                            # 失败时重置标记，允许重试
                            self.daily_records_sent = None

                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"每日报告循环错误: {e}")
                await asyncio.sleep(60)

    async def _send_daily_records(self):
        """发送交易记录到 Notion（nanobot 会独立读取并推送到 Lark）"""
        try:
            yesterday = (datetime.now() - timedelta(days=1)).date()
            date_str = str(yesterday)

            records = self._collect_trade_records(date_str)
            content = self._format_trade_records(records, yesterday)

            # 只写入 Notion，nanobot 会独立读取并推送到 Lark
            await self.notification_manager.notion.write_trade(
                trade_type="每日交易记录",
                content=content,
                profit=records['total_profit'],
                exchange="Summary",
                extra_data={'date': date_str}
            )

            logger.info(f"✅ 交易记录已写入 Notion ({yesterday}) - 等待 nanobot 推送分析")

        except Exception as e:
            logger.error(f"写入交易记录失败: {e}")

    def _collect_trade_records(self, date_str: str) -> Dict:
        """收集交易记录"""
        records = {
            'date': date_str,
            'total_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit': 0.0,
            'trades': [],
            'cross_stats': {}
        }

        # 读取风控记录
        if self.risk_manager:
            for trade in self.risk_manager.trades:
                trade_date = trade.created_at.date()
                if str(trade_date) == date_str:
                    records['total_trades'] += 1
                    if trade.status.value == 'executed':
                        records['successful_trades'] += 1
                        records['total_profit'] += trade.actual_profit
                    elif trade.status.value == 'failed':
                        records['failed_trades'] += 1

        # 读取跨所套利统计
        stats_file = 'data/cross_exchange_stats.json'
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'r') as f:
                    records['cross_stats'] = json.load(f)
            except Exception as e:
                logger.error(f"读取统计失败: {e}")

        return records

    def _format_trade_records(self, records: Dict, date) -> str:
        """格式化记录"""
        lines = [
            f"📋 每日交易记录 ({date})",
            "=" * 50,
            "",
            f"总交易: {records['total_trades']} | 成功: {records['successful_trades']} | 利润: {records['total_profit']:.4f} USDT",
            "",
            "📈 跨所套利统计:",
        ]

        # 按机会次数排序
        sorted_stats = sorted(
            records.get('cross_stats', {}).items(),
            key=lambda x: x[1].get('profitable_count', 0),
            reverse=True
        )

        for symbol, stats in sorted_stats[:10]:
            count = stats.get('count', 0)
            profitable = stats.get('profitable_count', 0)
            max_diff = stats.get('max_diff', 0)
            rate = (profitable / count * 100) if count > 0 else 0
            marker = "🔥" if profitable > 5 else "  "
            lines.append(f"{marker} {symbol}: 检查{count}次 | 机会{profitable}次({rate:.1f}%) | 最大价差{max_diff:.4%}")

        return "\n".join(lines)

    async def _health_check_loop(self):
        """健康检查"""
        check_count = 0
        while self.running:
            try:
                check_count += 1

                if not self.binance.is_connected():
                    await self.binance.initialize()
                if not self.okx.is_connected():
                    await self.okx.initialize()

                if check_count % 5 == 0:
                    stats = self.risk_manager.get_stats()
                    logger.info(f"💓 健康检查 | 盈亏: {stats['daily_pnl']:.4f} | 交易: {stats['daily_trades']}")

                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"健康检查错误: {e}")
                await asyncio.sleep(60)


async def main():
    """主函数"""
    bot = ArbitrageBot()

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
