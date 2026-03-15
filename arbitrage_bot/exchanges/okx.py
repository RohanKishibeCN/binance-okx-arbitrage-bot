"""
OKX 交易所实现
"""

import ccxt.async_support as ccxt
import ccxt.pro as ccxt_pro

from .base import BaseExchange
from ..config import ExchangeConfig


class OKXExchange(BaseExchange):
    """OKX 交易所"""
    
    def __init__(self, config: ExchangeConfig = None):
        from ..config import config as global_config
        super().__init__("OKX", config or global_config.okx)
    
    def _create_exchange(self) -> ccxt.Exchange:
        """创建 OKX 交易所实例"""
        options = {
            'defaultType': 'spot',
            'sandbox': self.config.sandbox,
        }
        
        # 如果有密码，添加到选项中
        if self.config.passphrase:
            options['password'] = self.config.passphrase
        
        return ccxt.okx({
            'apiKey': self.config.api_key,
            'secret': self.config.secret,
            'enableRateLimit': self.config.enable_rate_limit,
            'options': options,
            'timeout': self.config.timeout,
        })
    
    def _create_ws_exchange(self) -> ccxt_pro.Exchange:
        """创建 OKX WebSocket 交易所实例"""
        options = {'defaultType': 'spot'}
        
        if self.config.passphrase:
            options['password'] = self.config.passphrase
        
        return ccxt_pro.okx({
            'apiKey': self.config.api_key,
            'secret': self.config.secret,
            'options': options,
        })