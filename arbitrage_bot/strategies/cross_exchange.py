# arbitrage_bot/strategies/cross_exchange_arbitrage.py

import asyncio
import time
import json
import os
from typing import Dict, Optional
from datetime import datetime
from ..utils.logger import get_logger

# 关键修复：导入 config
from ..config import config

logger = get_logger(__name__)

class CrossExchangeArbitrage:
    def __init__(self, binance, okx, risk_manager):
        self.binance = binance
        self.okx = okx
        self.risk_manager = risk_manager

        # 关键修复：正确访问配置
        self.config = config.trading
        self.ce_config = getattr(config, 'cross_exchange_config', {
            'min_profit_threshold': 0.0015,
            'max_spread_history': 100
        })
        
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
        base = self.ce_config.get('min_profit_threshold', 0.0015)
        
        # 根据历史价差调整
        history = self.spread_history.get(symbol, [])
        
        if len(history) >= 10:
            avg = sum(history) / len(history)
            if avg < 0.0005:
                return base * 1.5
            elif max(history) > 0.01:
                return base * 0.8
        
        return base

    async def _execute_arbitrage(self, symbol: str, direction: str, spread: float):
        """执行套利"""
        try:
            if not await self.risk_manager.can_trade():
                return
            
            amount = self.config.trade_amount_usdt
            
            if self.config.dry_run:
                profit = amount * spread - (amount * 0.001 * 2)
                logger.info(f"[DRY_RUN] 跨所套利 {symbol}: {direction}, 价差{spread:.4%}, 预估利润{profit:.2f}USDT")
                self._record_trade(symbol, direction, spread, profit, "simulated")
            else:
                logger.info(f"[LIVE] 执行套利 {symbol}: {direction}")
                # 实际执行逻辑...
                
        except Exception as e:
            logger.error(f"执行套利失败 {symbol}: {e}")

    async def _update_stats(self, symbol: str, spread_b2o: float, spread_o2b: float):
        """更新统计"""
        if symbol not in self.stats:
            self.stats[symbol] = {
                'count': 0, 'profitable_count': 0, 
                'max_diff': 0, 'total_spread': 0
            }
        
        stats = self.stats[symbol]
        stats['count'] += 1
        
        max_spread = max(abs(spread_b2o), abs(spread_o2b))
        if max_spread > stats['max_diff']:
            stats['max_diff'] = max_spread
        
        positive = max(spread_b2o, spread_o2b)
        if positive > 0:
            stats['profitable_count'] += 1
            stats['total_spread'] += positive
            
            if symbol not in self.spread_history:
                self.spread_history[symbol] = []
            self.spread_history[symbol].append(positive)
            
            max_hist = self.ce_config.get('max_spread_history', 100)
            if len(self.spread_history[symbol]) > max_hist:
                self.spread_history[symbol].pop(0)
        
        if stats['profitable_count'] > 0:
            stats['avg_diff'] = stats['total_spread'] / stats['profitable_count']
        
        # 实时保存统计
        with open('data/cross_exchange_stats.json', 'w') as f:
            json.dump(self.stats, f)

    def clean_old_stats(self):
        """清理旧统计"""
        current = set(config.cross_exchange_symbols)
        for k in list(self.stats.keys()):
            if k not in current:
                del self.stats[k]
                if k in self.spread_history:
                    del self.spread_history[k]

    def get_stats(self):
        return self.stats
