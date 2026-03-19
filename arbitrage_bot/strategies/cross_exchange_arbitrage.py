# arbitrage_bot/strategies/cross_exchange_arbitrage.py

import asyncio
import json
import os
from typing import Dict, Optional
from datetime import datetime
from ..config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CrossExchangeArbitrage:
    """跨交易所套利策略（双边持仓模式）"""
    
    def __init__(self, binance, okx, risk_manager):
        self.binance = binance
        self.okx = okx
        self.risk_manager = risk_manager
        self.config = config.trading
        self.ce_config = getattr(config, 'cross_exchange_config', {
            'min_profit_threshold': 0.0015,
            'max_spread_history': 100
        })
        
        self.stats = {}
        self.spread_history = {}
        self.running = False

    async def run(self):
        """主运行循环 - 分层监控所有币种"""
        self.running = True
        logger.info("🔥 跨所套利策略启动...")
        
        # 分层币种列表
        tier1_symbols = ['SOL/USDT', 'AVAX/USDT', 'FET/USDT', 'MATIC/USDT', 'LINK/USDT']
        # tier2_symbols = ['UNI/USDT', 'DOT/USDT', 'ATOM/USDT', 'ARB/USDT', 'OP/USDT']
        # tier3_symbols = ['NEAR/USDT', 'APT/USDT', 'SUI/USDT', 'SEI/USDT', 'PYTH/USDT', 'JTO/USDT', 'WLD/USDT']
        
        iteration = 0
        
        while self.running:
            try:
                iteration += 1
                logger.info(f"🔄 第 {iteration} 轮检查开始...")
                
                # Tier 1: 高频检查（每轮都查）
                for symbol in tier1_symbols:
                    if not self.running:
                        break
                    logger.info(f"  检查 {symbol}...")
                    
                    # 添加5秒超时，防止卡住
                    try:
                        await asyncio.wait_for(
                            self.check_opportunity(symbol), 
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"  {symbol} 检查超时，跳过")
                        continue
                        
                    await asyncio.sleep(0.1)
                
                logger.info(f"✅ 第 {iteration} 轮完成，等待下一轮...")
                await asyncio.sleep(1)  # 每轮间隔1秒
                
                # Tier 2: 中频检查（每2轮）
                if iteration % 2 == 0:
                    for symbol in tier2_symbols:
                        if not self.running:
                            break
                        await self.check_opportunity(symbol)
                        await asyncio.sleep(0.15)
                
                # Tier 3: 低频检查（每5轮）
                if iteration % 5 == 0:
                    for symbol in tier3_symbols:
                        if not self.running:
                            break
                        await self.check_opportunity(symbol)
                        await asyncio.sleep(0.2)
                    
                    # 清理旧统计
                    self._clean_old_stats()
                
                # 防止CPU过载
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ 跨所套利循环错误: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def check_opportunity(self, symbol: str):
        """检查套利机会 - 增强日志"""
        try:
            logger.debug(f"开始获取 {symbol} 订单簿...")
            
            # 并行获取两个交易所数据
            binance_data, okx_data = await asyncio.gather(
                self._get_exchange_data(self.binance, symbol),
                self._get_exchange_data(self.okx, symbol),
                return_exceptions=True
            )
            
            if isinstance(binance_data, Exception):
                logger.warning(f"Binance {symbol} 数据获取失败: {binance_data}")
                return
            if isinstance(okx_data, Exception):
                logger.warning(f"OKX {symbol} 数据获取失败: {okx_data}")
                return
                
            logger.debug(f"{symbol} 数据获取成功，计算价差...")
            
            # 计算真实价格（考虑深度）
            binance_buy = self._calculate_real_price(binance_data, 'buy')
            okx_sell = self._calculate_real_price(okx_data, 'sell')
            binance_sell = self._calculate_real_price(binance_data, 'sell')
            okx_buy = self._calculate_real_price(okx_data, 'buy')
            
            if not all([binance_buy, okx_sell, binance_sell, okx_buy]):
                return
            
            # 计算两个方向的价差
            # 方向1: Binance买 -> OKX卖
            spread_b2o = (okx_sell - binance_buy) / binance_buy
            
            # 方向2: OKX买 -> Binance卖  
            spread_o2b = (binance_sell - okx_buy) / okx_buy
            
            # 更新统计
            max_spread = max(spread_b2o, spread_o2b)
            await self._update_stats(symbol, spread_b2o, spread_o2b)
            
            # 动态阈值判断
            min_profit = self._get_dynamic_threshold(symbol)
            
            # 执行套利
            if spread_b2o > min_profit:
                await self._execute_arbitrage(symbol, 'binance_buy_okx_sell', spread_b2o)
            elif spread_o2b > min_profit:
                await self._execute_arbitrage(symbol, 'okx_buy_binance_sell', spread_o2b)
                
        except Exception as e:
            logger.debug(f"检查机会失败 {symbol}: {e}")

    async def _get_exchange_data(self, exchange, symbol: str):
        """获取交易所订单簿数据"""
        try:
            orderbook = await exchange.fetch_order_book(symbol, limit=20)
            return {
                'bids': orderbook['bids'],  # [price, amount]
                'asks': orderbook['asks'],
                'timestamp': orderbook['timestamp']
            }
        except Exception as e:
            raise e

    def _calculate_real_price(self, data: Dict, side: str) -> Optional[float]:
        """计算考虑深度的真实成交价格"""
        try:
            amount_usdt = self.config.trade_amount_usdt
            
            if side == 'buy':
                # 从asks累积计算买入成本
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
                # 从bids累积计算卖出所得
                bids = data['bids']
                total_received = 0
                target_qty = amount_usdt / bids[0][0] if bids else 0
                
                for price, qty in bids:
                    if target_qty <= 0:
                        break
                    qty_to_sell = min(qty, target_qty)
                    total_received += qty_to_sell * price
                    target_qty -= qty_to_sell
                
                original_qty = amount_usdt / bids[0][0] if bids else 1
                return total_received / original_qty if total_received > 0 else None
                
        except Exception:
            return None

    def _get_dynamic_threshold(self, symbol: str) -> float:
        """获取动态利润阈值"""
        base = self.ce_config.get('min_profit_threshold', 0.0015)
        history = self.spread_history.get(symbol, [])
        
        if len(history) >= 10:
            avg = sum(history) / len(history)
            if avg < 0.0005:  # 平均价差太小，提高门槛
                return base * 1.5
            elif max(history) > 0.01:  # 波动大，降低门槛
                return base * 0.8
        
        return base

    async def _execute_arbitrage(self, symbol: str, direction: str, spread: float):
        """执行套利"""
        try:
            # 风控检查
            if not await self.risk_manager.can_trade():
                return
            
            amount = self.config.trade_amount_usdt
            
            if self.config.dry_run:
                # 模拟模式：扣除双边手续费
                profit = amount * spread - (amount * self.config.fee_rate * 2)
                if profit > 0:
                    logger.info(f"[DRY_RUN] 跨所套利 {symbol}: {direction}, 价差{spread:.4%}, 预估利润{profit:.2f}USDT")
                    self._record_trade(symbol, direction, spread, profit, "simulated")
            else:
                # 实盘模式（待实现）
                logger.info(f"[LIVE] 执行套利 {symbol}: {direction}, 价差{spread:.4%}")
                
        except Exception as e:
            logger.error(f"执行套利失败 {symbol}: {e}")

    def _record_trade(self, symbol, direction, spread, profit, status):
        """记录交易"""
        trade = {
            'symbol': symbol,
            'direction': direction,
            'spread': spread,
            'profit': profit,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        # 追加写入文件
        filepath = 'data/cross_exchange_trades.json'
        trades = []
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                trades = json.load(f)
        trades.append(trade)
        with open(filepath, 'w') as f:
            json.dump(trades, f)

    async def _update_stats(self, symbol: str, spread_b2o: float, spread_o2b: float):
        """更新统计"""
        if symbol not in self.stats:
            self.stats[symbol] = {
                'count': 0,
                'profitable_count': 0,
                'max_diff': 0,
                'total_spread': 0
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

    def _clean_old_stats(self):
        """清理旧统计"""
        current = set(config.cross_exchange_symbols)
        for k in list(self.stats.keys()):
            if k not in current:
                del self.stats[k]
                if k in self.spread_history:
                    del self.spread_history[k]

    def get_stats(self):
        return self.stats
