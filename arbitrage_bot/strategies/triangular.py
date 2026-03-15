"""
三角套利策略

路径: USDT -> BTC -> ETH -> USDT
计算: (ETH/USDT bid) / (BTC/USDT ask * ETH/BTC ask) - 1
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import uuid

from ..exchanges.base import BaseExchange, OrderBook
from ..config import TradingConfig
from ..risk.manager import RiskManager, TradeRecord
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TriangularOpportunity:
    """三角套利机会"""
    exchange: str
    path: List[str]  # 例如: ['USDT', 'BTC', 'ETH', 'USDT']
    profit_rate: float
    gross_profit: float
    net_profit: float  # 扣除手续费后
    required_amount: float
    order_books: Dict[str, OrderBook]
    timestamp: int
    
    def is_profitable(self, min_profit: float) -> bool:
        """检查是否有足够利润"""
        return self.net_profit > min_profit


class TriangularArbitrage:
    """三角套利策略"""
    
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
        
        # 三角套利路径
        self.path_symbols = ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']
        self.path_coins = ['USDT', 'BTC', 'ETH', 'USDT']
        
    async def run(self):
        """主循环"""
        logger.info(f"{self.exchange.name} 三角套利策略已启动")
        
        while True:
            try:
                opportunity = await self.find_opportunity()
                
                if opportunity and opportunity.is_profitable(self.config.min_profit_threshold):
                    logger.info(
                        f"发现三角套利机会: {self.exchange.name} "
                        f"利润率: {opportunity.profit_rate:.4%} "
                        f"净利润: {opportunity.net_profit:.4f} USDT"
                    )
                    
                    # 执行套利
                    if not self.config.dry_run:
                        await self.execute_arbitrage(opportunity)
                    else:
                        logger.info(f"[DRY RUN] 跳过执行: {opportunity}")
                
            except Exception as e:
                logger.error(f"三角套利循环错误: {e}", exc_info=True)
            
            await asyncio.sleep(self.config.check_interval)
    
    async def find_opportunity(self) -> Optional[TriangularOpportunity]:
        """寻找套利机会"""
        try:
            # 获取订单簿（而不是 ticker，因为需要深度信息）
            order_books = {}
            for symbol in self.path_symbols:
                ob = await self.exchange.fetch_order_book(symbol, limit=10)
                if not ob:
                    return None
                order_books[symbol] = ob
            
            # 计算套利利润
            return self._calculate_profit(order_books)
            
        except Exception as e:
            logger.error(f"寻找机会失败: {e}")
            return None
    
    def _calculate_profit(self, order_books: Dict[str, OrderBook]) -> Optional[TriangularOpportunity]:
        """
        计算三角套利利润
        
        路径: USDT -> BTC -> ETH -> USDT
        1. 用 USDT 买 BTC: 价格 = BTC/USDT ask
        2. 用 BTC 买 ETH: 价格 = ETH/BTC ask
        3. 卖 ETH 得 USDT: 价格 = ETH/USDT bid
        
        毛利润 = (ETH/USDT bid) / (BTC/USDT ask * ETH/BTC ask) - 1
        净利润 = 毛利润 - 3 * fee_rate - slippage_buffer
        """
        btc_usdt = order_books['BTC/USDT']
        eth_btc = order_books['ETH/BTC']
        eth_usdt = order_books['ETH/USDT']
        
        # 获取最优价格
        btc_ask_price, btc_ask_vol = btc_usdt.get_best_ask()
        eth_btc_ask_price, eth_btc_ask_vol = eth_btc.get_best_ask()
        eth_bid_price, eth_bid_vol = eth_usdt.get_best_bid()
        
        if not all([btc_ask_price, eth_btc_ask_price, eth_bid_price]):
            return None
        
        # 计算理论利润率
        gross_ratio = eth_bid_price / (btc_ask_price * eth_btc_ask_price)
        gross_profit = gross_ratio - 1
        
        # 计算净利润（扣除手续费）
        # 3 笔交易，每笔手续费 fee_rate
        total_fee = 3 * self.config.fee_rate
        net_profit = gross_profit - total_fee - self.config.slippage_buffer
        
        # 检查订单簿深度是否足够
        trade_amount = self.config.trade_amount_usdt
        
        # 计算每步需要的数量
        btc_amount = trade_amount / btc_ask_price
        eth_amount = btc_amount / eth_btc_ask_price
        
        # 检查深度
        if btc_ask_vol < btc_amount:
            logger.debug(f"BTC/USDT 深度不足: {btc_ask_vol} < {btc_amount}")
            return None
        if eth_btc_ask_vol < eth_amount:
            logger.debug(f"ETH/BTC 深度不足: {eth_btc_ask_vol} < {eth_amount}")
            return None
        if eth_bid_vol < eth_amount:
            logger.debug(f"ETH/USDT 深度不足: {eth_bid_vol} < {eth_amount}")
            return None
        
        # 计算实际可获得的 USDT
        actual_usdt = eth_amount * eth_bid_price * (1 - self.config.fee_rate)
        net_profit_usdt = actual_usdt - trade_amount
        
        return TriangularOpportunity(
            exchange=self.exchange.name,
            path=self.path_coins,
            profit_rate=net_profit,
            gross_profit=gross_profit,
            net_profit=net_profit_usdt,
            required_amount=trade_amount,
            order_books=order_books,
            timestamp=btc_usdt.timestamp
        )
    
    async def execute_arbitrage(self, opportunity: TriangularOpportunity) -> bool:
        """执行三角套利"""
        trade_id = str(uuid.uuid4())[:8]
        
        # 创建交易记录
        trade = TradeRecord(
            id=trade_id,
            strategy='triangular',
            symbol='BTC/ETH/USDT',
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
            logger.info(f"开始执行三角套利: {trade_id}")
            
            # 步骤 1: USDT -> BTC
            btc_amount = opportunity.required_amount / opportunity.order_books['BTC/USDT'].get_best_ask()[0]
            order1 = await self.exchange.create_market_order('BTC/USDT', 'buy', btc_amount)
            
            if not order1:
                raise Exception("第一步订单失败")
            
            # 等待成交
            await asyncio.sleep(0.5)
            
            # 步骤 2: BTC -> ETH
            eth_amount = btc_amount / opportunity.order_books['ETH/BTC'].get_best_ask()[0]
            order2 = await self.exchange.create_market_order('ETH/BTC', 'buy', eth_amount)
            
            if not order2:
                # 如果第二步失败，需要回滚第一步
                await self._rollback(order1, 'BTC/USDT')
                raise Exception("第二步订单失败，已回滚")
            
            await asyncio.sleep(0.5)
            
            # 步骤 3: ETH -> USDT
            order3 = await self.exchange.create_market_order('ETH/USDT', 'sell', eth_amount)
            
            if not order3:
                # 如果第三步失败，情况复杂，需要手动处理
                logger.error(f"第三步订单失败，需要手动处理: {trade_id}")
                if self.risk_manager:
                    self.risk_manager.record_trade_failure(trade_id, "第三步订单失败")
                return False
            
            # 计算实际利润
            actual_profit = self._calculate_actual_profit(order1, order2, order3)
            
            logger.info(f"三角套利执行成功: {trade_id}, 实际利润: {actual_profit:.4f} USDT")
            
            if self.risk_manager:
                self.risk_manager.record_trade_execution(trade_id, actual_profit)
            
            return True
            
        except Exception as e:
            logger.error(f"三角套利执行失败: {trade_id}, 错误: {e}")
            if self.risk_manager:
                self.risk_manager.record_trade_failure(trade_id, str(e))
            return False
    
    async def _rollback(self, order: Dict, symbol: str):
        """回滚操作"""
        try:
            # 反向操作平仓
            filled = order.get('filled', 0)
            if filled > 0:
                side = 'sell' if order['side'] == 'buy' else 'buy'
                await self.exchange.create_market_order(symbol, side, filled)
                logger.info(f"回滚成功: {symbol} {side} {filled}")
        except Exception as e:
            logger.error(f"回滚失败: {e}")
    
    def _calculate_actual_profit(self, order1: Dict, order2: Dict, order3: Dict) -> float:
        """计算实际利润"""
        try:
            # 计算 USDT 变化
            usdt_spent = float(order1.get('cost', 0))
            usdt_received = float(order3.get('cost', 0))
            return usdt_received - usdt_spent
        except:
            return 0.0