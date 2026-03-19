"""
套利机器人主入口 - 优化版本
"""

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
        # 添加这一行（初始化 Notion client）
        self.notion_client = Client(auth=os.getenv('NOTION_TOKEN'))
        self.tasks: List[asyncio.Task] = []
        self.running = False
        
        
        # 记录推送状态
        self.daily_records_sent: datetime = None  # 8点交易记录
        self.daily_analysis_sent: datetime = None  # 9点分析总结
        
        # 创建数据目录
        os.makedirs('data', exist_ok=True)
        
    async def initialize(self):
        """初始化机器人"""
        logger.info("=" * 70)
        logger.info("🚀 套利机器人启动中...")
        logger.info("=" * 70)
        
        # 打印配置
        self._print_config()
        
        # 初始化交易所
        logger.info("\n📡 初始化交易所连接...")
        self.binance = BinanceExchange()
        self.okx = OKXExchange()
        
        await self.binance.initialize()
        await self.okx.initialize()
        
        # 初始化风控
        logger.info("\n🛡️  初始化风控系统...")
        self.risk_manager = RiskManager()
        await self.risk_manager.start()
        
        # 初始化通知
        logger.info("\n📢 初始化通知系统...")
        self.notification_manager = NotificationManager(notion_client=self.notion_client)
        await self.notification_manager.initialize()
        
        # 测试通知连接
        connection_results = await self.notification_manager.test_connections()
        logger.info(f"通知连接状态: {connection_results}")
        
        logger.info("\n✅ 套利机器人初始化完成")
        logger.info("=" * 70)
        
    def _print_config(self):
        """打印配置信息"""
        cfg = config.print_config()
        logger.info("\n⚙️  配置信息:")
        logger.info(f"  DRY_RUN: {cfg['dry_run']}")
        logger.info(f"  最小利润率: {cfg['min_profit']:.4%}")
        logger.info(f"  交易金额: {cfg['trade_amount']} USDT")
        logger.info(f"  Binance API: {'✓' if cfg['binance_api_configured'] else '✗'}")
        logger.info(f"  OKX API: {'✓' if cfg['okx_api_configured'] else '✗'}")
        logger.info(f"  Notion: {'✓' if cfg['notion_configured'] else '✗'}")
        logger.info(f"  Nanobot: {'✓' if cfg['nanobot_configured'] else '✗'}")
        
    async def run(self):
        """运行机器人"""
        self.running = True
        
        # 创建策略实例
        binance_triangular = TriangularArbitrage(self.binance, self.risk_manager)
        okx_triangular = TriangularArbitrage(self.okx, self.risk_manager)
        cross_exchange = CrossExchangeArbitrage(self.binance, self.okx, self.risk_manager)
        
        # 启动所有策略
        logger.info("\n🤖 启动套利策略...")
        self.tasks = [
            asyncio.create_task(binance_triangular.run(), name="Binance-Triangular"),
            asyncio.create_task(okx_triangular.run(), name="OKX-Triangular"),
            asyncio.create_task(cross_exchange.run(), name="Cross-Exchange"),
            asyncio.create_task(self._daily_report_loop(), name="Daily-Report"),
            asyncio.create_task(self._health_check_loop(), name="Health-Check"),
        ]
        
        logger.info("  ✓ Binance 三角套利")
        logger.info("  ✓ OKX 三角套利")
        logger.info("  ✓ 跨交易所套利")
        logger.info("\n🎯 机器人运行中...")
        logger.info("=" * 70)
        
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("任务被取消")
        except Exception as e:
            logger.error(f"运行错误: {e}", exc_info=True)
    
    async def stop(self):
        """停止机器人"""
        logger.info("\n🛑 正在停止套利机器人...")
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
        
        logger.info("✅ 套利机器人已停止")
    
    async def _daily_report_loop(self):
        """每日报告循环 - 8点推送记录，9点推送分析"""
        while self.running:
            try:
                now = datetime.now()
                today = now.date()
                
                # 早上 8:00 推送交易记录
                if now.hour == 8 and now.minute == 0:
                    if self.daily_records_sent != today:
                        self.daily_records_sent = today
                        logger.info("📋 开始生成每日交易记录...")
                        await self._send_daily_records()
                
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"每日报告循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _send_daily_records(self):
        """发送每日交易记录（8点）- 只写入 Notion，不推 Lark"""
        try:
            yesterday = (datetime.now() - timedelta(days=1)).date()
            date_str = str(yesterday)
            
            # 收集所有交易记录
            records = self._collect_trade_records(date_str)
            
            # 生成记录内容
            content = self._format_trade_records(records, yesterday)

            # 只写入 Notion（8点任务完成）
            success = await self.notification_manager.write_trade(
                trade_type="每日交易记录",
                content=content,
                profit=records['total_profit'],
                exchange="Summary",
                extra_data={'date': date_str, 'trades_count': records['total_trades']}
            )

            if success:
                logger.info(f"✅ 每日交易记录已写入 Notion ({yesterday})")
            else:
                logger.error(f"❌ 写入 Notion 失败 ({yesterday})")
            
        except Exception as e:
            logger.error(f"发送每日交易记录失败: {e}")
    
    
    def _collect_trade_records(self, date_str: str) -> Dict:
        """收集指定日期的交易记录"""
        records = {
            'date': date_str,
            'total_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit': 0.0,
            'trades': [],
            'triangular_stats': {},
            'cross_stats': {}
        }
        
        # 读取风控系统的交易记录
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
                    
                    records['trades'].append({
                        'id': trade.id,
                        'strategy': trade.strategy,
                        'symbol': trade.symbol,
                        'amount': trade.amount,
                        'expected_profit': trade.expected_profit,
                        'actual_profit': trade.actual_profit,
                        'status': trade.status.value,
                        'time': trade.created_at.isoformat()
                    })
        
        # 读取模拟交易记录
        for filename in ['simulated_trades_binance.json', 'simulated_trades_okx.json', 'simulated_trades_cross.json']:
            filepath = f"data/{filename}"
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        trades = json.load(f)
                        for trade in trades:
                            if trade['timestamp'].startswith(date_str):
                                records['trades'].append(trade)
                                if 'expected_profit' in trade:
                                    records['total_profit'] += trade['expected_profit']
                except Exception as e:
                    logger.error(f"读取模拟交易记录失败: {e}")
        
        # 读取价差统计
        for stats_file in ['triangular_stats_binance.json', 'triangular_stats_okx.json', 'cross_exchange_stats.json']:
            filepath = f"data/{stats_file}"
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        stats = json.load(f)
                        if 'triangular' in stats_file:
                            records['triangular_stats'].update(stats)
                        else:
                            records['cross_stats'].update(stats)
                except Exception as e:
                    logger.error(f"读取统计失败: {e}")
        
        return records
    
    def _format_trade_records(self, records: Dict, date) -> str:
        """格式化交易记录"""
        lines = [
            f"📋 每日交易记录 ({date})",
            "=" * 50,
            "",
            "📊 交易统计:",
            f"  总交易数: {records['total_trades']}",
            f"  成功: {records['successful_trades']}",
            f"  失败: {records['failed_trades']}",
            f"  总利润: {records['total_profit']:.4f} USDT",
            "",
        ]
        
        # 交易明细
        if records['trades']:
            lines.append("📜 交易明细:")
            for trade in records['trades'][:20]:  # 最多显示20条
                strategy = trade.get('strategy', 'unknown')
                symbol = trade.get('symbol', 'unknown')
                profit = trade.get('actual_profit', trade.get('expected_profit', 0))
                status = trade.get('status', 'unknown')
                lines.append(f"  [{status}] {strategy} - {symbol}: {profit:.4f} USDT")
            
            if len(records['trades']) > 20:
                lines.append(f"  ... 还有 {len(records['trades']) - 20} 条记录")
        
        # 价差统计
        if records['triangular_stats']:
            lines.extend(["", "📈 三角套利统计:"])
            for path, stats in records['triangular_stats'].items():
                lines.append(f"  {path}: 检查{stats.get('count', 0)}次, 机会{stats.get('profitable_count', 0)}次")
        
        if records['cross_stats']:
            lines.extend(["", "📈 跨所套利统计:"])
            for symbol, stats in records['cross_stats'].items():
                lines.append(f"  {symbol}: 检查{stats.get('count', 0)}次, 机会{stats.get('profitable_count', 0)}次")
        
        lines.extend(["", "=" * 50])
        
        return "\n".join(lines)
    
    def _generate_analysis_prompt(self, records: Dict, date) -> str:
        """生成分析提示词"""
        
        # 构建交易数据摘要
        trade_summary = f"""
日期: {date}
总交易数: {records['total_trades']}
成功: {records['successful_trades']}
失败: {records['failed_trades']}
总利润: {records['total_profit']:.4f} USDT

交易明细:
"""
        
        for trade in records['trades'][:10]:
            strategy = trade.get('strategy', 'unknown')
            symbol = trade.get('symbol', 'unknown')
            profit = trade.get('actual_profit', trade.get('expected_profit', 0))
            status = trade.get('status', 'unknown')
            trade_summary += f"- [{status}] {strategy} - {symbol}: {profit:.4f} USDT\n"
        
        # 价差统计摘要
        stats_summary = "\n价差统计:\n"
        
        if records['triangular_stats']:
            stats_summary += "三角套利:\n"
            for path, stats in list(records['triangular_stats'].items())[:5]:
                count = stats.get('count', 0)
                profitable = stats.get('profitable_count', 0)
                max_profit = stats.get('max_profit', 0)
                avg_profit = stats.get('avg_profit', 0)
                rate = (profitable / count * 100) if count > 0 else 0
                stats_summary += f"  {path}: {count}次检查, {profitable}次机会({rate:.1f}%), 最大{max_profit:.4%}, 平均{avg_profit:.4%}\n"
        
        if records['cross_stats']:
            stats_summary += "\n跨所套利:\n"
            for symbol, stats in list(records['cross_stats'].items())[:5]:
                count = stats.get('count', 0)
                profitable = stats.get('profitable_count', 0)
                max_diff = stats.get('max_diff', 0)
                avg_diff = stats.get('avg_diff', 0)
                rate = (profitable / count * 100) if count > 0 else 0
                stats_summary += f"  {symbol}: {count}次检查, {profitable}次机会({rate:.1f}%), 最大{max_diff:.4%}, 平均{avg_diff:.4%}\n"
        
        prompt = f"""请基于以下套利机器人交易数据，生成一份详细的分析报告和优化建议，然后推送到 Notion 数据库。

## 交易数据
{trade_summary}
{stats_summary}

## 请生成以下内容：

1. **交易表现分析**
   - 当日盈亏情况
   - 交易成功率分析
   - 各策略表现对比

2. **市场机会分析**
   - 哪些币种/路径机会最多
   - 价差分布情况
   - 最佳交易时段（如有数据）

3. **问题诊断**
   - 失败交易原因分析
   - 执行效率评估
   - 风控触发情况

4. **优化建议**
   - 参数调整建议（MIN_PROFIT、交易金额等）
   - 币种/路径增减建议
   - 策略改进方向

5. **明日操作计划**
   - 建议关注的币种
   - 建议调整的参数
   - 风险提示

请用中文生成专业的分析报告，包含具体的数据支撑。"""
        
        return prompt
    
    async def _call_nanobot_for_analysis(self, prompt: str, date):
        """调用 nanobot 生成分析"""
        try:
            import aiohttp
            
            nanobot_url = config.notification.nanobot_url
            if not nanobot_url:
                logger.warning("Nanobot URL 未配置，跳过分析生成")
                return
            
            # 构建请求
            payload = {
                "prompt": prompt,
                "action": "generate_and_save_to_notion",
                "notion_db_id": config.notification.notion_db_id,
                "title": f"📊 每日套利分析总结 ({date})",
                "type": "每日分析总结"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{nanobot_url}/analyze",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Nanobot 分析生成成功: {result}")
                    else:
                        text = await response.text()
                        logger.error(f"Nanobot 分析生成失败: {response.status} - {text}")
                        
        except Exception as e:
            logger.error(f"调用 nanobot 失败: {e}")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        check_count = 0
        while self.running:
            try:
                check_count += 1
                
                # 检查交易所连接
                if not self.binance.is_connected():
                    logger.warning("⚠️  Binance 连接断开，尝试重连...")
                    await self.binance.initialize()
                
                if not self.okx.is_connected():
                    logger.warning("⚠️  OKX 连接断开，尝试重连...")
                    await self.okx.initialize()
                
                # 每5次检查打印一次统计
                if check_count % 5 == 0:
                    stats = self.risk_manager.get_stats()
                    logger.info(
                        f"💓 健康检查 | "
                        f"当日盈亏: {stats['daily_pnl']:.4f} USDT | "
                        f"交易: {stats['daily_trades']} | "
                        f"持仓: {stats['open_positions']}"
                    )
                
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
