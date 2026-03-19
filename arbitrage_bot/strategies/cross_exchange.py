# arbitrage_bot/strategies/cross_exchange_arbitrage.py

import asyncio
import time
from typing import Dict, Optional
from datetime import datetime

class CrossExchangeArbitrage:
    def __init__(self, binance, okx, risk_manager):
        self.binance = binance
        self.okx = okx
        self.risk_manager = risk_manager
        self.config = config.trading
        self.ce_config = config.cross_exchange_config
        
        # 统计信息
        self.stats = {}
        self.spread_history = {}  # 保存价差历史用于动态阈值
        
    async def check_opportunity(self, symbol: str):
        """检查跨所套利机会（优化版）"""
        try:
            # 并行获取两个交易所的数据（加快速度）
            binance_data, okx_data = await asyncio.gather(
                self._get_exchange_data(self.binance, symbol),
                self._get_exchange_data(self.okx, symbol),
                return_exceptions=True
            )
            
            if isinstance(binance_data, Exception) or isinstance(okx_data, Exception):
                return
            
            # 计算价差（考虑深度的真实价格）
            binance_price = self._calculate_real_price(binance_data, 'buy')
            okx_price = self._calculate_real_price(okx_data, 'sell')
            
            if not binance_price or not okx_price:
                return
            
            # 计算价差方向
            spread_b2o = (okx_price - binance_price) / binance_price  # Binance买, OKX卖
            spread_o2b = (binance_price - okx_price) / okx_price      # OKX买, Binance卖
            
            # 更新统计
            await self._update_stats(symbol, spread_b2o, spread_o2b)
            
            # 动态阈值判断
            min_profit = self._get_dynamic_threshold(symbol)
            
            # 检查机会
            if spread_b2o > min_profit:
                await self._execute_arbitrage(symbol, 'binance_buy_okx_sell', spread_b2o)
            elif spread_o2b > min_profit:
                await self._execute_arbitrage(symbol, 'okx_buy_binance_sell', spread_o2b)
                
        except Exception as e:
            logger.error(f"检查跨所套利失败 {symbol}: {e}")

    async def _get_exchange_data(self, exchange, symbol: str):
        """获取交易所订单簿数据"""
        try:
            # 使用最佳实践：先检查ticker快速筛选，再获取深度
            ticker = await exchange.fetch_ticker(symbol)
            orderbook = await exchange.fetch_order_book(symbol, limit=20)
            
            return {
                'ticker': ticker,
                'bids': orderbook['bids'],  # [price, amount]
                'asks': orderbook['asks'],
                'timestamp': orderbook['timestamp']
            }
        except Exception as e:
            raise e

    def _calculate_real_price(self, data: Dict, side: str) -> Optional[float]:
        """计算考虑深度的真实成交价格（防止滑点）"""
        try:
            amount_usdt = self.config.trade_amount_usdt
            
            if side == 'buy':
                # 计算实际买入成本（从asks累积）
                asks = data['asks']
                total_cost = 0
                total_qty = 0
                
                for price, qty in asks:
                    available = price * qty
                    if total_cost + available >= amount_usdt:
                        remaining = amount_usdt - total_cost
                        total_qty += remaining / price
                        total_cost = amount_usdt
                        break
                    total_cost += available
                    total_qty += qty
                
                return amount_usdt / total_qty if total_qty > 0 else None
                
            else:  # sell
                # 计算实际卖出可得（从bids累积）
                bids = data['bids']
                total_received = 0
                remaining_qty = amount_usdt / bids[0][0] if bids else 0  # 估算需要的币量
                
                for price, qty in bids:
                    if remaining_qty <= 0:
                        break
                    qty_to_sell = min(qty, remaining_qty)
                    total_received += qty_to_sell * price
                    remaining_qty -= qty_to_sell
                
                return total_received / (amount_usdt / bids[0][0]) if total_received > 0 else None
                
        except Exception:
            return None

    def _get_dynamic_threshold(self, symbol: str) -> float:
        """获取动态利润阈值"""
        base_threshold = self.ce_config['min_profit_threshold']  # 0.15%
        
        # 根据历史价差调整
        history = self.spread_history.get(symbol, [])
        if len(history) >= 10:
            avg_spread = sum(history) / len(history)
            max_spread = max(history)
            
            # 如果历史价差很小，提高门槛避免频繁触发亏损
            if avg_spread < 0.0005:  # 平均<0.05%
                return base_threshold * 1.5
            # 如果历史价差波动大，降低门槛抓住机会
            elif max_spread > 0.01:  # 最大>1%
                return base_threshold * 0.8
        
        return base_threshold

    async def _execute_arbitrage(self, symbol: str, direction: str, spread: float):
        """执行套利"""
        try:
            # 检查风控
            if not await self.risk_manager.can_trade():
                return
            
            # 解析方向
            if direction == 'binance_buy_okx_sell':
                buy_exchange, sell_exchange = self.binance, self.okx
                buy_name, sell_name = 'Binance', 'OKX'
            else:
                buy_exchange, sell_exchange = self.okx, self.binance
                buy_name, sell_name = 'OKX', 'Binance'
            
            # 双边持仓模式（无需提币）
            # 在buy_exchange买入，同时在sell_exchange卖出
            amount = self.config.trade_amount_usdt
            
            # 模拟模式或实盘
            if self.config.dry_run:
                profit = amount * spread - (amount * 0.001 * 2)  # 扣除两边手续费
                logger.info(f"[DRY_RUN] 跨所套利 {symbol}: {direction}, 价差{spread:.4%}, 预估利润{profit:.2f}USDT")
                await self._record_simulated_trade(symbol, direction, spread, profit)
            else:
                # 实际执行（需实现）
                pass
                
        except Exception as e:
            logger.error(f"执行套利失败 {symbol}: {e}")

    async def _update_stats(self, symbol: str, spread_b2o: float, spread_o2b: float):
        """更新统计信息"""
        if symbol not in self.stats:
            self.stats[symbol] = {
                'count': 0,
                'profitable_count': 0,
                'max_diff': 0,
                'avg_diff': 0,
                'total_spread': 0
            }
        
        stats = self.stats[symbol]
        stats['count'] += 1
        
        # 记录最大价差（绝对值）
        max_spread = max(abs(spread_b2o), abs(spread_o2b))
        if max_spread > stats['max_diff']:
            stats['max_diff'] = max_spread
        
        # 记录正价差（机会）
        if spread_b2o > 0 or spread_o2b > 0:
            positive_spread = max(spread_b2o, spread_o2b)
            stats['profitable_count'] += 1
            stats['total_spread'] += positive_spread
            
            # 保存到历史
            if symbol not in self.spread_history:
                self.spread_history[symbol] = []
            self.spread_history[symbol].append(positive_spread)
            
            # 限制历史长度
            if len(self.spread_history[symbol]) > self.ce_config['max_spread_history']:
                self.spread_history[symbol].pop(0)
        
        # 计算平均值
        if stats['profitable_count'] > 0:
            stats['avg_diff'] = stats['total_spread'] / stats['profitable_count']

    def clean_old_stats(self):
        """清理旧统计，防止内存泄漏"""
        # 只保留最近活跃的币种统计
        current_symbols = set(config.cross_exchange_symbols)
        keys_to_remove = [k for k in self.stats.keys() if k not in current_symbols]
        for k in keys_to_remove:
            del self.stats[k]
            if k in self.spread_history:
                del self.spread_history[k]

    def get_stats(self):
        return self.stats
