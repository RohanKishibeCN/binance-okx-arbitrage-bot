"""
跨交易所套利策略 - 优化版本

支持双边持仓模式和价差统计分析
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque
from enum import Enum
import uuid
import json
import os

from ..exchanges.base import BaseExchange, Ticker
from ..config import TradingConfig
from ..risk.manager import RiskManager, TradeRecord
from ..utils.logger import get_logger

logger = get_logger(__name__)


class HedgeSide(Enum):
    """对冲方向"""
    BUY_LOW_SELL_HIGH = "buy_low_sell_high"
    BUY_HIGH_SELL_LOW = "buy_high_sell_low"


@dataclass
class CrossExchangeOpportunity:
    """跨交易所套利机会"""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    price_diff: float
    price_diff_rate: float
    gross_profit: float
    net_profit: float
    amount: float
    timestamp: int
    
    def is_profitable(self, min_profit: float) -> bool:
        return self.net_profit > min_profit


@dataclass
class SymbolSpreadStats:
    """币种价差统计"""
    symbol: str
    count: int = 0
    profitable_count: int = 0
    max_diff: float = 0
    avg_diff: float = 0
    last_diff: float = 0
    history: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def update(self, diff: float, is_profitable: bool):
        self.count += 1
        self.last_diff = diff
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'diff': diff
        })
        
        if is_profitable:
            self.profitable_count += 1
        
        self.max_diff = max(self.max_diff, diff)
        if self.history:
            self.avg_diff = sum(h['diff'] for h in self.history) / len(self.history)
    
    def get_stats(self) -> dict:
        return {
            'symbol': self.symbol,
            'checks': self.count,
            'opportunities': self.profitable_count,
            'opportunity_rate': f"{self.profitable_count / self.count * 100:.2f}%" if self.count > 0 else "0%",
            'max_diff': f"{self.max_diff:.4%}",
            'avg_diff': f"{self.avg_diff:.4%}",
            'last_diff': f"{self.last_diff:.4%}"
        }


class CrossExchangeArbitrage:
    """跨交易所套利策略 - 优化版本"""
    
    def __init__(
        self,
        exchange1: BaseExchange,
        exchange2: BaseExchange,
        risk_manager: RiskManager = None,
        config: TradingConfig = None
    ):
        from ..config import config as global_config
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.risk_manager = risk_manager
        self.config = config or global_config.trading
        
        # 统计信息
        self.spread_stats: Dict[str, SymbolSpreadStats] = {}
        self.simulated_trades: List[dict] = []
        self.last_stats_print = datetime.now()
        
        # 动态阈值
        self.dynamic_thresholds: Dict[str, float] = {}
        
        # 加载历史统计
        self._load_stats()
        
    def _load_stats(self):
        """加载历史统计"""
        stats_file = "data/cross_exchange_stats.json"
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                    for symbol, stats_data in data.items():
                        self.spread_stats[symbol] = SymbolSpreadStats(
                            symbol=symbol,
                            count=stats_data.get('count', 0),
                            profitable_count=stats_data.get('profitable_count', 0),
                            max_diff=stats_data.get('max_diff', 0),
                            avg_diff=stats_data.get('avg_diff', 0)
                        )
                logger.info(f"加载跨所价差统计: {len(self.spread_stats)} 个币种")
            except Exception as e:
                logger.error(f"加载统计失败: {e}")
    
    def _save_stats(self):
        """保存统计信息"""
        try:
            os.makedirs('data', exist_ok=True)
            stats_file = "data/cross_exchange_stats.json"
            data = {}
            for symbol, stats in self.spread_stats.items():
                data[symbol] = {
                    'count': stats.count,
                    'profitable_count': stats.profitable_count,
                    'max_diff': stats.max_diff,
                    'avg_diff': stats.avg_diff
                }
            with open(stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"保存统计失败: {e}")
    
    async def run(self, symbols: List[str] = None):
        """主循环"""
        from ..config import config as global_config
        symbols = symbols or global_config.cross_exchange_symbols
        
        logger.info(
            f"跨交易所套利策略已启动: {self.exchange1.name} <-> {self.exchange2.name}"
        )
        logger.info(f"监控币种数: {len(symbols)}")
        logger.info(f"监控币种: {', '.join(symbols)}")
        
        # 初始化持仓
        await self._initialize_positions()
        
        while True:
            try:
                opportunities = []
                
                for symbol in symbols:
                    opportunity = await self.find_opportunity(symbol)
                    
                    if opportunity:
                        # 更新统计
                        if symbol not in self.spread_stats:
                            self.spread_stats[symbol] = SymbolSpreadStats(symbol=symbol)
                        
                        is_profitable = opportunity.is_profitable(self.config.min_profit_threshold)
                        self.spread_stats[symbol].update(
                            opportunity.price_diff_rate,
                            is_profitable
                        )
                        
                        # 更新动态阈值
                        self._update_dynamic_threshold(symbol)
                        
                        if is_profitable:
                            opportunities.append(opportunity)
                    
                    await asyncio.sleep(0.05)  # 避免过于频繁的请求
                
                # 如果有多个机会，选择利润最高的
                if opportunities:
                    best_opportunity = max(opportunities, key=lambda x: x.net_profit)
                    
                    logger.info(
                        f"🎯 发现跨所套利机会: {best_opportunity.symbol} | "
                        f"{best_opportunity.buy_exchange}@{best_opportunity.buy_price:.2f} -> "
                        f"{best_opportunity.sell_exchange}@{best_opportunity.sell_price:.2f} | "
                        f"差价: {best_opportunity.price_diff_rate:.4%} | "
                        f"净利润: {best_opportunity.net_profit:.4f} USDT"
                    )
                    
                    # 执行套利
                    if not self.config.dry_run:
                        await self.execute_arbitrage(best_opportunity)
                    else:
                        await self._simulate_trade(best_opportunity)
                
                # 定期打印统计
                if (datetime.now() - self.last_stats_print).seconds > 300:
                    self._print_stats()
                    self._save_stats()
                    self.last_stats_print = datetime.now()
                
            except Exception as e:
                logger.error(f"跨所套利循环错误: {e}", exc_info=True)
            
            await asyncio.sleep(self.config.check_interval)
    
    async def _initialize_positions(self):
        """初始化双边持仓"""
        try:
            # 获取两个交易所的余额
            balance1 = await self.exchange1.fetch_balance()
            balance2 = await self.exchange2.fetch_balance()
            
            # 计算总持仓价值
            usdt1 = balance1.get('USDT')
            usdt2 = balance2.get('USDT')
            
            usdt1_free = usdt1.free if usdt1 else 0
            usdt2_free = usdt2.free if usdt2 else 0
            
            btc1 = balance1.get('BTC')
            btc2 = balance2.get('BTC')
            eth1 = balance1.get('ETH')
            eth2 = balance2.get('ETH')
            sol1 = balance1.get('SOL')
            sol2 = balance2.get('SOL')
            
            logger.info(
                f"持仓初始化完成:\n"
                f"  {self.exchange1.name}: USDT={usdt1_free:.2f}, "
                f"BTC={btc1.free if btc1 else 0:.4f}, "
                f"ETH={eth1.free if eth1 else 0:.4f}, "
                f"SOL={sol1.free if sol1 else 0:.4f}\n"
                f"  {self.exchange2.name}: USDT={usdt2_free:.2f}, "
                f"BTC={btc2.free if btc2 else 0:.4f}, "
                f"ETH={eth2.free if eth2 else 0:.4f}, "
                f"SOL={sol2.free if sol2 else 0:.4f}\n"
                f"  总 USDT: {usdt1_free + usdt2_free:.2f}"
            )
            
        except Exception as e:
            logger.error(f"持仓初始化失败: {e}")
    
    async def find_opportunity(self, symbol: str) -> Optional[CrossExchangeOpportunity]:
        """寻找套利机会"""
        try:
            # 并发获取两个交易所的行情
            ticker1_task = self.exchange1.fetch_ticker(symbol)
            ticker2_task = self.exchange2.fetch_ticker(symbol)
            
            ticker1, ticker2 = await asyncio.gather(
                ticker1_task,
                ticker2_task,
                return_exceptions=True
            )
            
            if isinstance(ticker1, Exception) or isinstance(ticker2, Exception):
                return None
            
            if not ticker1 or not ticker2:
                return None
            
            return self._calculate_profit(symbol, ticker1, ticker2)
            
        except Exception as e:
            logger.debug(f"寻找机会失败: {symbol}, {e}")
            return None
    
    def _calculate_profit(
        self,
        symbol: str,
        ticker1: Ticker,
        ticker2: Ticker
    ) -> Optional[CrossExchangeOpportunity]:
        """计算跨交易所套利利润"""
        
        # 计算中间价
        mid1 = (ticker1.bid + ticker1.ask) / 2
        mid2 = (ticker2.bid + ticker2.ask) / 2
        
        # 确定哪个交易所价格更低
        if mid1 < mid2:
            buy_exchange = self.exchange1.name
            sell_exchange = self.exchange2.name
            buy_price = ticker1.ask
            sell_price = ticker2.bid
            buy_volume = ticker1.ask_volume
            sell_volume = ticker2.bid_volume
        else:
            buy_exchange = self.exchange2.name
            sell_exchange = self.exchange1.name
            buy_price = ticker2.ask
            sell_price = ticker1.bid
            buy_volume = ticker2.ask_volume
            sell_volume = ticker1.bid_volume
        
        # 计算差价
        price_diff = sell_price - buy_price
        price_diff_rate = price_diff / buy_price
        
        # 计算毛利润
        trade_amount = self.config.trade_amount_usdt
        gross_profit = price_diff_rate * trade_amount
        
        # 计算净利润（扣除双边手续费）
        total_fee = 2 * self.config.fee_rate * trade_amount
        net_profit = gross_profit - total_fee - (self.config.slippage_buffer * trade_amount)
        
        # 检查深度
        amount = trade_amount / buy_price
        
        if buy_volume < amount or sell_volume < amount:
            return None
        
        return CrossExchangeOpportunity(
            symbol=symbol,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            price_diff=price_diff,
            price_diff_rate=price_diff_rate,
            gross_profit=gross_profit,
            net_profit=net_profit,
            amount=amount,
            timestamp=ticker1.timestamp
        )
    
    def _update_dynamic_threshold(self, symbol: str):
        """更新动态阈值"""
        stats = self.spread_stats.get(symbol)
        if not stats or stats.count < 100:
            return
        
        # 动态阈值 = 平均价差 + 1个标准差
        if len(stats.history) >= 100:
            diffs = [h['diff'] for h in list(stats.history)[-100:]]
            avg = sum(diffs) / len(diffs)
            variance = sum((d - avg) ** 2 for d in diffs) / len(diffs)
            std = variance ** 0.5
            
            # 阈值 = 平均值 + 1个标准差，但不超过最大价差的80%
            threshold = min(avg + std, stats.max_diff * 0.8)
            self.dynamic_thresholds[symbol] = threshold
    
    async def execute_arbitrage(self, opportunity: CrossExchangeOpportunity) -> bool:
        """执行跨交易所套利"""
        trade_id = str(uuid.uuid4())[:8]
        
        # 创建交易记录
        trade = TradeRecord(
            id=trade_id,
            strategy='cross_exchange',
            symbol=opportunity.symbol,
            side='hedge',
            amount=opportunity.amount,
            price=opportunity.buy_price,
            expected_profit=opportunity.net_profit
        )
        
        # 风控检查
        if self.risk_manager:
            if not self.risk_manager.record_trade_attempt(trade):
                return False
        
        try:
            logger.info(
                f"开始执行跨所套利: {trade_id} | "
                f"{opportunity.symbol} | "
                f"{opportunity.buy_exchange} -> {opportunity.sell_exchange}"
            )
            
            # 确定交易所
            if opportunity.buy_exchange == self.exchange1.name:
                buy_ex = self.exchange1
                sell_ex = self.exchange2
            else:
                buy_ex = self.exchange2
                sell_ex = self.exchange1
            
            # 同时执行买入和卖出
            buy_task = buy_ex.create_market_order(
                opportunity.symbol,
                'buy',
                opportunity.amount
            )
            sell_task = sell_ex.create_market_order(
                opportunity.symbol,
                'sell',
                opportunity.amount
            )
            
            buy_order, sell_order = await asyncio.gather(
                buy_task,
                sell_task,
                return_exceptions=True
            )
            
            # 检查订单结果
            if isinstance(buy_order, Exception):
                logger.error(f"买入订单失败: {buy_order}")
                if self.risk_manager:
                    self.risk_manager.record_trade_failure(trade_id, f"买入失败: {buy_order}")
                return False
            
            if isinstance(sell_order, Exception):
                logger.error(f"卖出订单失败: {sell_order}")
                if buy_order and not isinstance(buy_order, Exception):
                    logger.warning(f"买入成功但卖出失败，持仓增加: {opportunity.symbol}")
                if self.risk_manager:
                    self.risk_manager.record_trade_failure(trade_id, f"卖出失败: {sell_order}")
                return False
            
            # 计算实际利润
            actual_profit = self._calculate_actual_profit(buy_order, sell_order)
            
            logger.info(
                f"✅ 跨所套利执行成功: {trade_id} | "
                f"实际利润: {actual_profit:.4f} USDT"
            )
            
            if self.risk_manager:
                self.risk_manager.record_trade_execution(trade_id, actual_profit)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 跨所套利执行失败: {trade_id}, 错误: {e}")
            if self.risk_manager:
                self.risk_manager.record_trade_failure(trade_id, str(e))
            return False
    
    async def _simulate_trade(self, opportunity: CrossExchangeOpportunity):
        """模拟交易（DRY RUN 模式）"""
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'symbol': opportunity.symbol,
            'buy_exchange': opportunity.buy_exchange,
            'sell_exchange': opportunity.sell_exchange,
            'buy_price': opportunity.buy_price,
            'sell_price': opportunity.sell_price,
            'diff_rate': opportunity.price_diff_rate,
            'expected_profit': opportunity.net_profit,
            'amount': opportunity.amount
        }
        
        self.simulated_trades.append(trade_record)
        
        # 保存模拟交易记录
        try:
            os.makedirs('data', exist_ok=True)
            sim_file = "data/simulated_trades_cross.json"
            with open(sim_file, 'w') as f:
                json.dump(self.simulated_trades, f, indent=2)
        except Exception as e:
            logger.error(f"保存模拟交易失败: {e}")
        
        logger.info(
            f"[DRY RUN] 模拟跨所套利: {opportunity.symbol} | "
            f"{opportunity.buy_exchange}@{opportunity.buy_price:.2f} -> "
            f"{opportunity.sell_exchange}@{opportunity.sell_price:.2f} | "
            f"预期利润: {opportunity.net_profit:.4f} USDT | "
            f"累计模拟: {len(self.simulated_trades)}"
        )
    
    def _calculate_actual_profit(self, buy_order: dict, sell_order: dict) -> float:
        """计算实际利润"""
        try:
            buy_cost = float(buy_order.get('cost', 0))
            sell_revenue = float(sell_order.get('cost', 0))
            buy_fee = float(buy_order.get('fee', {}).get('cost', 0))
            sell_fee = float(sell_order.get('fee', {}).get('cost', 0))
            return sell_revenue - buy_cost - buy_fee - sell_fee
        except Exception as e:
            logger.error(f"计算利润失败: {e}")
            return 0.0
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("=" * 80)
        logger.info(f"📊 跨所套利统计 ({self.exchange1.name} <-> {self.exchange2.name})")
        logger.info("=" * 80)
        
        total_checks = 0
        total_opportunities = 0
        
        # 按机会数量排序
        sorted_stats = sorted(
            self.spread_stats.items(),
            key=lambda x: x[1].profitable_count,
            reverse=True
        )
        
        for symbol, stats in sorted_stats:
            total_checks += stats.count
            total_opportunities += stats.profitable_count
            
            if stats.count > 0:
                rate = stats.profitable_count / stats.count * 100
                dynamic_threshold = self.dynamic_thresholds.get(symbol, self.config.min_profit_threshold)
                logger.info(
                    f"  {symbol:12} | "
                    f"检查: {stats.count:5} | "
                    f"机会: {stats.profitable_count:4} ({rate:5.2f}%) | "
                    f"最大: {stats.max_diff:8.4%} | "
                    f"平均: {stats.avg_diff:8.4%} | "
                    f"动态阈值: {dynamic_threshold:8.4%}"
                )
        
        if total_checks > 0:
            overall_rate = total_opportunities / total_checks * 100
            logger.info("-" * 80)
            logger.info(
                f"  {'总计':12} | "
                f"检查: {total_checks:5} | "
                f"机会: {total_opportunities:4} ({overall_rate:5.2f}%)"
            )
        
        # 计算模拟总收益
        if self.simulated_trades:
            total_simulated_profit = sum(t['expected_profit'] for t in self.simulated_trades)
            logger.info(f"  模拟总收益: {total_simulated_profit:.4f} USDT ({len(self.simulated_trades)} 笔)")
        
        logger.info("=" * 80)
    
    def get_best_symbols(self, top_n: int = 5) -> List[str]:
        """获取最佳币种（机会最多的）"""
        sorted_stats = sorted(
            self.spread_stats.items(),
            key=lambda x: x[1].profitable_count,
            reverse=True
        )
        return [s[0] for s in sorted_stats[:top_n]]