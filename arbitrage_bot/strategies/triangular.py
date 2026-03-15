"""
三角套利策略 - 多路径版本

支持多种三角套利路径，自动选择最优路径
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import uuid
import json
import os

from ..exchanges.base import BaseExchange, OrderBook
from ..config import TradingConfig
from ..risk.manager import RiskManager, TradeRecord
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TriangularOpportunity:
    """三角套利机会"""
    exchange: str
    path_name: str  # 路径名称，如 "BTC-ETH-USDT"
    path: List[str]  # 例如: ['USDT', 'BTC', 'ETH', 'USDT']
    symbols: List[str]  # 交易对列表
    profit_rate: float
    gross_profit: float
    net_profit: float
    required_amount: float
    order_books: Dict[str, OrderBook]
    timestamp: int
    
    def is_profitable(self, min_profit: float) -> bool:
        return self.net_profit > min_profit
    
    def to_dict(self) -> dict:
        return {
            'exchange': self.exchange,
            'path_name': self.path_name,
            'path': self.path,
            'profit_rate': self.profit_rate,
            'net_profit': self.net_profit,
            'timestamp': self.timestamp
        }


@dataclass
class SpreadStats:
    """价差统计"""
    path_name: str
    count: int = 0
    profitable_count: int = 0
    max_profit: float = 0
    avg_profit: float = 0
    last_profit: float = 0
    history: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def update(self, profit: float, is_profitable: bool):
        self.count += 1
        self.last_profit = profit
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'profit': profit
        })
        
        if is_profitable:
            self.profitable_count += 1
        
        self.max_profit = max(self.max_profit, profit)
        self.avg_profit = sum(h['profit'] for h in self.history) / len(self.history)
    
    def get_stats(self) -> dict:
        return {
            'path': self.path_name,
            'checks': self.count,
            'opportunities': self.profitable_count,
            'opportunity_rate': f"{self.profitable_count / self.count * 100:.2f}%" if self.count > 0 else "0%",
            'max_profit': f"{self.max_profit:.4%}",
            'avg_profit': f"{self.avg_profit:.4%}",
            'last_profit': f"{self.last_profit:.4%}"
        }


class TriangularArbitrage:
    """三角套利策略 - 多路径版本"""
    
    # 预定义的三角套利路径
    TRIANGULAR_PATHS = [
        {
            'name': 'BTC-ETH-USDT',
            'symbols': ['BTC/USDT', 'ETH/BTC', 'ETH/USDT'],
            'coins': ['USDT', 'BTC', 'ETH', 'USDT']
        },
        {
            'name': 'BTC-SOL-USDT',
            'symbols': ['BTC/USDT', 'SOL/BTC', 'SOL/USDT'],
            'coins': ['USDT', 'BTC', 'SOL', 'USDT']
        },
        {
            'name': 'ETH-SOL-USDT',
            'symbols': ['ETH/USDT', 'SOL/ETH', 'SOL/USDT'],
            'coins': ['USDT', 'ETH', 'SOL', 'USDT']
        },
        {
            'name': 'BTC-BNB-USDT',
            'symbols': ['BTC/USDT', 'BNB/BTC', 'BNB/USDT'],
            'coins': ['USDT', 'BTC', 'BNB', 'USDT']
        },
        {
            'name': 'ETH-BNB-USDT',
            'symbols': ['ETH/USDT', 'BNB/ETH', 'BNB/USDT'],
            'coins': ['USDT', 'ETH', 'BNB', 'USDT']
        },
        {
            'name': 'BTC-XRP-USDT',
            'symbols': ['BTC/USDT', 'XRP/BTC', 'XRP/USDT'],
            'coins': ['USDT', 'BTC', 'XRP', 'USDT']
        },
        {
            'name': 'ETH-XRP-USDT',
            'symbols': ['ETH/USDT', 'XRP/ETH', 'XRP/USDT'],
            'coins': ['USDT', 'ETH', 'XRP', 'USDT']
        },
        {
            'name': 'BTC-DOGE-USDT',
            'symbols': ['BTC/USDT', 'DOGE/BTC', 'DOGE/USDT'],
            'coins': ['USDT', 'BTC', 'DOGE', 'USDT']
        },
        {
            'name': 'BTC-ADA-USDT',
            'symbols': ['BTC/USDT', 'ADA/BTC', 'ADA/USDT'],
            'coins': ['USDT', 'BTC', 'ADA', 'USDT']
        },
        {
            'name': 'ETH-ADA-USDT',
            'symbols': ['ETH/USDT', 'ADA/ETH', 'ADA/USDT'],
            'coins': ['USDT', 'ETH', 'ADA', 'USDT']
        }
    ]
    
    def __init__(
        self,
        exchange: BaseExchange,
        risk_manager: RiskManager = None,
        config: TradingConfig = None
    ):
        from ..config import config as global_config
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.config = config or global_config.trading
        
        # 统计信息
        self.spread_stats: Dict[str, SpreadStats] = {}
        self.simulated_trades: List[dict] = []
        self.last_stats_print = datetime.now()
        
        # 加载历史统计
        self._load_stats()
        
    def _load_stats(self):
        """加载历史统计"""
        stats_file = f"data/triangular_stats_{self.exchange.name.lower()}.json"
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                    for path_name, stats_data in data.items():
                        self.spread_stats[path_name] = SpreadStats(
                            path_name=path_name,
                            count=stats_data.get('count', 0),
                            profitable_count=stats_data.get('profitable_count', 0),
                            max_profit=stats_data.get('max_profit', 0),
                            avg_profit=stats_data.get('avg_profit', 0)
                        )
                logger.info(f"加载历史统计: {len(self.spread_stats)} 条路径")
            except Exception as e:
                logger.error(f"加载统计失败: {e}")
    
    def _save_stats(self):
        """保存统计信息"""
        try:
            os.makedirs('data', exist_ok=True)
            stats_file = f"data/triangular_stats_{self.exchange.name.lower()}.json"
            data = {}
            for path_name, stats in self.spread_stats.items():
                data[path_name] = {
                    'count': stats.count,
                    'profitable_count': stats.profitable_count,
                    'max_profit': stats.max_profit,
                    'avg_profit': stats.avg_profit
                }
            with open(stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"保存统计失败: {e}")
    
    async def run(self):
        """主循环"""
        logger.info(f"{self.exchange.name} 三角套利策略已启动")
        logger.info(f"监控路径数: {len(self.TRIANGULAR_PATHS)}")
        
        # 打印监控的路径
        for path in self.TRIANGULAR_PATHS:
            logger.info(f"  - {path['name']}: {path['symbols']}")
        
        while True:
            try:
                # 收集所有路径的机会
                opportunities = []
                
                for path_config in self.TRIANGULAR_PATHS:
                    opportunity = await self._check_path(path_config)
                    
                    if opportunity:
                        # 更新统计
                        if opportunity.path_name not in self.spread_stats:
                            self.spread_stats[opportunity.path_name] = SpreadStats(
                                path_name=opportunity.path_name
                            )
                        
                        is_profitable = opportunity.is_profitable(self.config.min_profit_threshold)
                        self.spread_stats[opportunity.path_name].update(
                            opportunity.profit_rate,
                            is_profitable
                        )
                        
                        if is_profitable:
                            opportunities.append(opportunity)
                
                # 如果有多个机会，选择利润最高的
                if opportunities:
                    best_opportunity = max(opportunities, key=lambda x: x.net_profit)
                    
                    logger.info(
                        f"🎯 发现三角套利机会: {self.exchange.name} | "
                        f"路径: {best_opportunity.path_name} | "
                        f"利润率: {best_opportunity.profit_rate:.4%} | "
                        f"净利润: {best_opportunity.net_profit:.4f} USDT"
                    )
                    
                    # 执行套利
                    if not self.config.dry_run:
                        await self.execute_arbitrage(best_opportunity)
                    else:
                        await self._simulate_trade(best_opportunity)
                
                # 定期打印统计
                if (datetime.now() - self.last_stats_print).seconds > 300:  # 每5分钟
                    self._print_stats()
                    self._save_stats()
                    self.last_stats_print = datetime.now()
                
            except Exception as e:
                logger.error(f"三角套利循环错误: {e}", exc_info=True)
            
            await asyncio.sleep(self.config.check_interval)
    
    async def _check_path(self, path_config: dict) -> Optional[TriangularOpportunity]:
        """检查单个路径的套利机会"""
        try:
            symbols = path_config['symbols']
            
            # 获取订单簿
            order_books = {}
            for symbol in symbols:
                ob = await self.exchange.fetch_order_book(symbol, limit=5)
                if not ob:
                    return None
                order_books[symbol] = ob
            
            # 计算利润
            return self._calculate_profit(path_config, order_books)
            
        except Exception as e:
            logger.debug(f"检查路径失败 {path_config['name']}: {e}")
            return None
    
    def _calculate_profit(
        self,
        path_config: dict,
        order_books: Dict[str, OrderBook]
    ) -> Optional[TriangularOpportunity]:
        """计算三角套利利润"""
        symbols = path_config['symbols']
        coins = path_config['coins']
        
        # 获取价格
        # 路径: USDT -> A -> B -> USDT
        # 1. 用 USDT 买 A: ask
        # 2. 用 A 买 B: ask
        # 3. 卖 B 得 USDT: bid
        
        symbol1, symbol2, symbol3 = symbols
        ob1 = order_books[symbol1]
        ob2 = order_books[symbol2]
        ob3 = order_books[symbol3]
        
        price1, vol1 = ob1.get_best_ask()  # A/USDT ask
        price2, vol2 = ob2.get_best_ask()  # B/A ask
        price3, vol3 = ob3.get_best_bid()  # B/USDT bid
        
        if not all([price1, price2, price3]):
            return None
        
        # 计算理论利润率
        # 最终 USDT = (amount / price1 / price2) * price3
        gross_ratio = price3 / (price1 * price2)
        gross_profit = gross_ratio - 1
        
        # 计算净利润（扣除手续费）
        total_fee = 3 * self.config.fee_rate
        net_profit_rate = gross_profit - total_fee - self.config.slippage_buffer
        
        # 计算实际利润（USDT）
        trade_amount = self.config.trade_amount_usdt
        amount_a = trade_amount / price1
        amount_b = amount_a / price2
        actual_usdt = amount_b * price3 * (1 - self.config.fee_rate)
        net_profit_usdt = actual_usdt - trade_amount
        
        # 检查深度
        if vol1 < amount_a:
            return None
        if vol2 < amount_b:
            return None
        if vol3 < amount_b:
            return None
        
        return TriangularOpportunity(
            exchange=self.exchange.name,
            path_name=path_config['name'],
            path=coins,
            symbols=symbols,
            profit_rate=net_profit_rate,
            gross_profit=gross_profit,
            net_profit=net_profit_usdt,
            required_amount=trade_amount,
            order_books=order_books,
            timestamp=ob1.timestamp
        )
    
    async def execute_arbitrage(self, opportunity: TriangularOpportunity) -> bool:
        """执行三角套利"""
        trade_id = str(uuid.uuid4())[:8]
        symbols = opportunity.symbols
        
        # 创建交易记录
        trade = TradeRecord(
            id=trade_id,
            strategy=f"triangular_{opportunity.path_name}",
            symbol=opportunity.path_name,
            side='arbitrage',
            amount=opportunity.required_amount,
            price=1.0,
            expected_profit=opportunity.net_profit
        )
        
        # 风控检查
        if self.risk_manager:
            if not self.risk_manager.record_trade_attempt(trade):
                return False
        
        try:
            logger.info(f"开始执行三角套利: {trade_id} | 路径: {opportunity.path_name}")
            
            # 步骤 1: USDT -> A
            price1 = opportunity.order_books[symbols[0]].get_best_ask()[0]
            amount_a = opportunity.required_amount / price1
            order1 = await self.exchange.create_market_order(symbols[0], 'buy', amount_a)
            
            if not order1:
                raise Exception("第一步订单失败")
            
            actual_amount_a = float(order1.get('filled', amount_a))
            await asyncio.sleep(0.3)
            
            # 步骤 2: A -> B
            price2 = opportunity.order_books[symbols[1]].get_best_ask()[0]
            amount_b = actual_amount_a / price2
            order2 = await self.exchange.create_market_order(symbols[1], 'buy', amount_b)
            
            if not order2:
                await self._rollback(order1, symbols[0])
                raise Exception("第二步订单失败，已回滚")
            
            actual_amount_b = float(order2.get('filled', amount_b))
            await asyncio.sleep(0.3)
            
            # 步骤 3: B -> USDT
            order3 = await self.exchange.create_market_order(symbols[2], 'sell', actual_amount_b)
            
            if not order3:
                logger.error(f"第三步订单失败，需要手动处理: {trade_id}")
                if self.risk_manager:
                    self.risk_manager.record_trade_failure(trade_id, "第三步订单失败")
                return False
            
            # 计算实际利润
            actual_profit = self._calculate_actual_profit(order1, order3)
            
            logger.info(
                f"✅ 三角套利执行成功: {trade_id} | "
                f"路径: {opportunity.path_name} | "
                f"实际利润: {actual_profit:.4f} USDT"
            )
            
            if self.risk_manager:
                self.risk_manager.record_trade_execution(trade_id, actual_profit)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 三角套利执行失败: {trade_id}, 错误: {e}")
            if self.risk_manager:
                self.risk_manager.record_trade_failure(trade_id, str(e))
            return False
    
    async def _simulate_trade(self, opportunity: TriangularOpportunity):
        """模拟交易（DRY_RUN 模式）"""
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'exchange': self.exchange.name,
            'path': opportunity.path_name,
            'expected_profit': opportunity.net_profit,
            'profit_rate': opportunity.profit_rate,
            'amount': opportunity.required_amount
        }
        
        self.simulated_trades.append(trade_record)
        
        # 保存模拟交易记录
        try:
            os.makedirs('data', exist_ok=True)
            sim_file = f"data/simulated_trades_{self.exchange.name.lower()}.json"
            with open(sim_file, 'w') as f:
                json.dump(self.simulated_trades, f, indent=2)
        except Exception as e:
            logger.error(f"保存模拟交易失败: {e}")
        
        logger.info(
            f"[DRY RUN] 模拟三角套利: {opportunity.path_name} | "
            f"预期利润: {opportunity.net_profit:.4f} USDT | "
            f"累计模拟交易: {len(self.simulated_trades)}"
        )
    
    async def _rollback(self, order: dict, symbol: str):
        """回滚操作"""
        try:
            filled = order.get('filled', 0)
            if filled > 0:
                side = 'sell' if order['side'] == 'buy' else 'buy'
                await self.exchange.create_market_order(symbol, side, filled)
                logger.info(f"回滚成功: {symbol} {side} {filled}")
        except Exception as e:
            logger.error(f"回滚失败: {e}")
    
    def _calculate_actual_profit(self, first_order: dict, last_order: dict) -> float:
        """计算实际利润"""
        try:
            usdt_spent = float(first_order.get('cost', 0))
            usdt_received = float(last_order.get('cost', 0))
            fee1 = float(first_order.get('fee', {}).get('cost', 0))
            fee2 = float(last_order.get('fee', {}).get('cost', 0))
            return usdt_received - usdt_spent - fee1 - fee2
        except:
            return 0.0
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("=" * 60)
        logger.info(f"📊 {self.exchange.name} 三角套利统计")
        logger.info("=" * 60)
        
        total_checks = 0
        total_opportunities = 0
        
        for path_name, stats in sorted(self.spread_stats.items()):
            total_checks += stats.count
            total_opportunities += stats.profitable_count
            
            if stats.count > 0:
                rate = stats.profitable_count / stats.count * 100
                logger.info(
                    f"  {path_name:15} | "
                    f"检查: {stats.count:5} | "
                    f"机会: {stats.profitable_count:4} ({rate:5.2f}%) | "
                    f"最大: {stats.max_profit:8.4%} | "
                    f"平均: {stats.avg_profit:8.4%}"
                )
        
        if total_checks > 0:
            overall_rate = total_opportunities / total_checks * 100
            logger.info("-" * 60)
            logger.info(
                f"  {'总计':15} | "
                f"检查: {total_checks:5} | "
                f"机会: {total_opportunities:4} ({overall_rate:5.2f}%)"
            )
        
        logger.info("=" * 60)
    
    def get_best_path(self) -> Optional[str]:
        """获取最佳路径（机会最多的）"""
        if not self.spread_stats:
            return None
        
        best_path = max(
            self.spread_stats.items(),
            key=lambda x: x[1].profitable_count
        )
        return best_path[0]