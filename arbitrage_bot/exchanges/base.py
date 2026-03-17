"""
交易所基类 - 封装通用功能
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from decimal import Decimal
import ccxt.async_support as ccxt
import ccxt.pro as ccxt_pro

from ..config import ExchangeConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Ticker:
    """行情数据"""
    symbol: str
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    timestamp: int


@dataclass
class OrderBook:
    """订单簿数据"""
    symbol: str
    bids: List[Tuple[float, float]]  # (price, volume)
    asks: List[Tuple[float, float]]
    timestamp: int
    
    def get_best_bid(self) -> Tuple[float, float]:
        """获取最优买价"""
        return self.bids[0] if self.bids else (0, 0)
    
    def get_best_ask(self) -> Tuple[float, float]:
        """获取最优卖价"""
        return self.asks[0] if self.asks else (0, 0)
    
    def get_depth_at_price(self, price: float, side: str = 'ask') -> float:
        """获取指定价格区间的深度"""
        orders = self.asks if side == 'ask' else self.bids
        total_volume = 0
        for p, v in orders:
            if side == 'ask' and p <= price:
                total_volume += v
            elif side == 'bid' and p >= price:
                total_volume += v
        return total_volume


@dataclass
class Balance:
    """账户余额"""
    asset: str
    free: float
    used: float
    total: float


class BaseExchange(ABC):
    """交易所基类"""
    
    def __init__(self, name: str, config: ExchangeConfig):
        self.name = name
        self.config = config
        self.exchange: Optional[ccxt.Exchange] = None
        self.ws_exchange: Optional[ccxt_pro.Exchange] = None
        self._connected = False
        self._last_request_time = 0
        self._request_count = 0
        
    async def initialize(self):
        """初始化交易所连接"""
        try:
            self.exchange = self._create_exchange()
            await self.exchange.load_markets()
            self._connected = True
            logger.info(f"{self.name} 交易所初始化成功")
        except Exception as e:
            logger.error(f"{self.name} 交易所初始化失败: {e}")
            raise
    
    async def initialize_websocket(self):
        """初始化 WebSocket 连接"""
        try:
            self.ws_exchange = self._create_ws_exchange()
            logger.info(f"{self.name} WebSocket 初始化成功")
        except Exception as e:
            logger.error(f"{self.name} WebSocket 初始化失败: {e}")
            raise
    
    @abstractmethod
    def _create_exchange(self) -> ccxt.Exchange:
        """创建交易所实例"""
        pass
    
    @abstractmethod
    def _create_ws_exchange(self) -> ccxt_pro.Exchange:
        """创建 WebSocket 交易所实例"""
        pass
    
    async def close(self):
        """关闭连接"""
        if self.exchange:
            await self.exchange.close()
        if self.ws_exchange:
            await self.ws_exchange.close()
        self._connected = False
        logger.info(f"{self.name} 交易所连接已关闭")
    
    async def fetch_ticker(self, symbol: str) -> Optional[Ticker]:
        """获取单个交易对行情"""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                bid=float(ticker['bid']) if ticker.get('bid') else 0,
                ask=float(ticker['ask']) if ticker.get('ask') else 0,
                bid_volume=float(ticker.get('bidVolume', 0) or 0),
                ask_volume=float(ticker.get('askVolume', 0) or 0),
                timestamp=ticker.get('timestamp', 0)
            )
        except Exception as e:
            logger.debug(f"获取 {symbol} 行情失败: {e}")
            return None
    
    async def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        """获取多个交易对行情"""
        try:
            tickers = await self.exchange.fetch_tickers(symbols)
            result = {}
            for symbol, ticker in tickers.items():
                try:
                    result[symbol] = Ticker(
                        symbol=symbol,
                        bid=float(ticker['bid']) if ticker.get('bid') else 0,
                        ask=float(ticker['ask']) if ticker.get('ask') else 0,
                        bid_volume=float(ticker.get('bidVolume', 0) or 0),
                        ask_volume=float(ticker.get('askVolume', 0) or 0),
                        timestamp=ticker.get('timestamp', 0)
                    )
                except Exception as e:
                    logger.debug(f"解析 {symbol} 行情失败: {e}")
            return result
        except Exception as e:
            logger.debug(f"获取行情失败: {e}")
            return {}
    
    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Optional[OrderBook]:
        """获取订单簿"""
        try:
            orderbook = await self.exchange.fetch_order_book(symbol, limit)
            
            # 安全解析 bids 和 asks
            bids = []
            asks = []
            
            for item in orderbook.get('bids', [])[:limit]:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        price = float(item[0])
                        volume = float(item[1])
                        bids.append((price, volume))
                except (ValueError, TypeError):
                    continue
            
            for item in orderbook.get('asks', [])[:limit]:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        price = float(item[0])
                        volume = float(item[1])
                        asks.append((price, volume))
                except (ValueError, TypeError):
                    continue
            
            return OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=orderbook.get('timestamp', 0)
            )
        except Exception as e:
            logger.debug(f"获取 {symbol} 订单簿失败: {e}")
            return None
    
    async def fetch_balance(self) -> Dict[str, Balance]:
        """获取账户余额"""
        try:
            balance = await self.exchange.fetch_balance()
            result = {}
            
            # ccxt 返回的 balance 结构: {'BTC': {'free': 1.0, 'used': 0.0, 'total': 1.0}, ...}
            for asset, data in balance.items():
                # 跳过非币种字段
                if asset in ['info', 'timestamp', 'datetime', 'free', 'used', 'total']:
                    continue
                
                if isinstance(data, dict):
                    try:
                        free = float(data.get('free', 0) or 0)
                        used = float(data.get('used', 0) or 0)
                        total = float(data.get('total', 0) or 0)
                        
                        # 只保留有余额的币种
                        if total > 0:
                            result[asset] = Balance(
                                asset=asset,
                                free=free,
                                used=used,
                                total=total
                            )
                    except (ValueError, TypeError):
                        continue
            
            return result
        except Exception as e:
            logger.debug(f"获取余额失败: {e}")
            return {}
    
    async def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float
    ) -> Optional[Dict]:
        """创建限价单"""
        try:
            order = await self.exchange.create_limit_order(symbol, side, amount, price)
            logger.info(f"创建限价单成功: {symbol} {side} {amount} @ {price}")
            return order
        except Exception as e:
            logger.error(f"创建限价单失败: {e}")
            return None
    
    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float
    ) -> Optional[Dict]:
        """创建市价单"""
        try:
            order = await self.exchange.create_market_order(symbol, side, amount)
            logger.info(f"创建市价单成功: {symbol} {side} {amount}")
            return order
        except Exception as e:
            logger.error(f"创建市价单失败: {e}")
            return None
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"取消订单成功: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    async def fetch_order(self, order_id: str, symbol: str) -> Optional[Dict]:
        """获取订单信息"""
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.error(f"获取订单信息失败: {e}")
            return None
    
    async def watch_order_book(self, symbol: str) -> OrderBook:
        """WebSocket 订阅订单簿"""
        if not self.ws_exchange:
            raise RuntimeError("WebSocket 未初始化")
        
        orderbook = await self.ws_exchange.watch_order_book(symbol)
        
        bids = []
        asks = []
        
        for item in orderbook.get('bids', []):
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    bids.append((float(item[0]), float(item[1])))
            except (ValueError, TypeError):
                continue
        
        for item in orderbook.get('asks', []):
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    asks.append((float(item[0]), float(item[1])))
            except (ValueError, TypeError):
                continue
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=orderbook.get('timestamp', 0)
        )
    
    async def watch_ticker(self, symbol: str) -> Ticker:
        """WebSocket 订阅行情"""
        if not self.ws_exchange:
            raise RuntimeError("WebSocket 未初始化")
        
        ticker = await self.ws_exchange.watch_ticker(symbol)
        return Ticker(
            symbol=symbol,
            bid=float(ticker['bid']) if ticker.get('bid') else 0,
            ask=float(ticker['ask']) if ticker.get('ask') else 0,
            bid_volume=float(ticker.get('bidVolume', 0) or 0),
            ask_volume=float(ticker.get('askVolume', 0) or 0),
            timestamp=ticker.get('timestamp', 0)
        )
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected