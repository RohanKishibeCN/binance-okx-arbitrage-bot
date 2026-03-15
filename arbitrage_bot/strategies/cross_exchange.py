"""
跨交易所套利策略

双边持仓模式：在两个交易所都持有资金和币种
当价差出现时，在低价所买入，同时在高价所卖出
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import uuid

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
    hedge_side: HedgeSide
    timestamp: int
    
    def is_profitable(self, min_profit: float) -> bool:
        """检查是否有足够利润"""
        return self.net_profit > min_profit


class CrossExchangeArbitrage:
    """跨交易所套利策略"""
    
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
        
        # 双边持仓模式
        self.positions: Dict[str, Dict] = {}  # 记录各交易所的持仓
        
    async def run(self, symbols: List[str] = None):
        """主循环"""
        from ..config import config as global_config
        symbols = symbols or global_config.cross_exchange_symbols
        
        logger.info(
            f"跨交易所套利策略已启动: {self.exchange1.name} <-> {self.exchange2.name}"
        )
        
        # 初始化持仓
        await self._initialize_positions()
        
        while True:
            try:
                for symbol in symbols:
                    opportunity = await self.find_opportunity(symbol)
                    
                    if opportunity and opportunity.is_profitable(self.config.min_profit_threshold):
                        logger.info(
                            f"发现跨所套利机会: {symbol} "
                            f"{opportunity.buy_exchange}@{opportunity.buy_price:.2f} -> "
                            f"{opportunity.sell_exchange}@{opportunity.sell_price:.2f} "
                            f"差价: {opportunity.price_diff_rate:.4%} "
                            f"净利润: {opportunity.net_profit:.4f} USDT"
                        )
                        
                        # 执行套利
                        if not self.config.dry_run:
                            await self.execute_arbitrage(opportunity)
                        else:
                            logger.info(f"[DRY RUN] 跳过执行: {symbol}")
                    
                    await asyncio.sleep(0.1)  # 避免过于频繁的请求
                    
            except Exception as e:
                logger.error(f"跨所套利循环错误: {e}", exc_info=True)
            
            await asyncio.sleep(self.config.check_interval)
    
    async def _initialize_positions(self):
        """初始化双边持仓"""
        try:
            # 获取两个交易所的余额
            balance1 = await self.exchange1.fetch_balance()
            balance2 = await self.exchange2.fetch_balance()
            
            logger.info(
                f"持仓初始化完成:\n"
                f"  {self.exchange1.name}: USDT={balance1.get('USDT', {}).free:.2f}, "
                f"BTC={balance1.get('BTC', {}).free:.4f}, ETH={balance1.get('ETH', {}).free:.4f}\n"
                f"  {self.exchange2.name}: USDT={balance2.get('USDT', {}).free:.2f}, "
                f"BTC={balance2.get('BTC', {}).free:.4f}, ETH={balance2.get('ETH', {}).free:.4f}"
            )
            
        except Exception as e:
            logger.error(f"持仓初始化失败: {e}")
    
    async def find_opportunity(self, symbol: str) -> Optional[CrossExchangeOpportunity]:
        """寻找套利机会"""
        try:
            # 获取两个交易所的行情
            ticker1 = await self.exchange1.fetch_ticker(symbol)
            ticker2 = await self.exchange2.fetch_ticker(symbol)
            
            if not ticker1 or not ticker2:
                return None
            
            return self._calculate_profit(symbol, ticker1, ticker2)
            
        except Exception as e:
            logger.error(f"寻找机会失败: {symbol}, {e}")
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
            buy_price = ticker1.ask  # 在低价的交易所买入（用 ask 价）
            sell_price = ticker2.bid  # 在高价的交易所卖出（用 bid 价）
        else:
            buy_exchange = self.exchange2.name
            sell_exchange = self.exchange1.name
            buy_price = ticker2.ask
            sell_price = ticker1.bid
        
        # 计算差价
        price_diff = sell_price - buy_price
        price_diff_rate = price_diff / buy_price
        
        # 计算毛利润
        trade_amount = self.config.trade_amount_usdt
        gross_profit = price_diff_rate * trade_amount
        
        # 计算净利润（扣除双边手续费）
        # 买入和卖出各一次手续费
        total_fee = 2 * self.config.fee_rate * trade_amount
        net_profit = gross_profit - total_fee - (self.config.slippage_buffer * trade_amount)
        
        # 检查深度是否足够
        if mid1 < mid2:
            buy_volume = ticker1.ask_volume
            sell_volume = ticker2.bid_volume
        else:
            buy_volume = ticker2.ask_volume
            sell_volume = ticker1.bid_volume
        
        amount = trade_amount / buy_price
        
        if buy_volume < amount:
            logger.debug(f"{buy_exchange} 深度不足: {buy_volume} < {amount}")
            return None
        if sell_volume < amount:
            logger.debug(f"{sell_exchange} 深度不足: {sell_volume} < {amount}")
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
            hedge_side=HedgeSide.BUY_LOW_SELL_HIGH,
            timestamp=ticker1.timestamp
        )
    
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
                f"开始执行跨所套利: {trade_id}, "
                f"{opportunity.symbol}, "
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
            
            # 等待两个订单完成
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
                # 如果卖出失败但买入成功，需要处理多出来的持仓
                if buy_order:
                    logger.warning(f"买入成功但卖出失败，持仓增加: {opportunity.symbol}")
                if self.risk_manager:
                    self.risk_manager.record_trade_failure(trade_id, f"卖出失败: {sell_order}")
                return False
            
            # 计算实际利润
            actual_profit = self._calculate_actual_profit(buy_order, sell_order)
            
            logger.info(
                f"跨所套利执行成功: {trade_id}, "
                f"实际利润: {actual_profit:.4f} USDT"
            )
            
            if self.risk_manager:
                self.risk_manager.record_trade_execution(trade_id, actual_profit)
            
            return True
            
        except Exception as e:
            logger.error(f"跨所套利执行失败: {trade_id}, 错误: {e}")
            if self.risk_manager:
                self.risk_manager.record_trade_failure(trade_id, str(e))
            return False
    
    def _calculate_actual_profit(self, buy_order: Dict, sell_order: Dict) -> float:
        """计算实际利润"""
        try:
            buy_cost = float(buy_order.get('cost', 0))
            sell_revenue = float(sell_order.get('cost', 0))
            
            # 扣除手续费
            buy_fee = float(buy_order.get('fee', {}).get('cost', 0))
            sell_fee = float(sell_order.get('fee', {}).get('cost', 0))
            
            return sell_revenue - buy_cost - buy_fee - sell_fee
        except Exception as e:
            logger.error(f"计算利润失败: {e}")
            return 0.0