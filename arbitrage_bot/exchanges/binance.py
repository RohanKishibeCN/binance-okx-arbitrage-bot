"""
Binance 交易所实现
"""

import ccxt.async_support as ccxt
import ccxt.pro as ccxt_pro

from .base import BaseExchange
from ..config import ExchangeConfig


class BinanceExchange(BaseExchange):
    """Binance 交易所"""
    
    def __init__(self, config: ExchangeConfig = None):
        from ..config import config as global_config
        super().__init__("Binance", config or global_config.binance)
    
    def _create_exchange(self) -> ccxt.Exchange:
        """创建 Binance 交易所实例"""
        return ccxt.binance({
            'apiKey': self.config.api_key,
            'secret': self.config.secret,
            'enableRateLimit': self.config.enable_rate_limit,
            'options': {
                'defaultType': 'spot',
                'sandbox': self.config.sandbox,
            },
            'timeout': self.config.timeout,
        })
    
    def _create_ws_exchange(self) -> ccxt_pro.Exchange:
        """创建 Binance WebSocket 交易所实例"""
        return ccxt_pro.binance({
            'apiKey': self.config.api_key,
            'secret': self.config.secret,
            'options': {
                'defaultType': 'spot',
            },
        })