# arbitrage_bot/config.py

import os
from typing import List, Optional

def get_env(key: str, default=None):
    return os.getenv(key, default)

class ExchangeConfig:
    def __init__(self, api_key_env: str, secret_env: str, passphrase_env: str = None):
        self.api_key = get_env(api_key_env, '')
        self.secret = get_env(secret_env, '')
        self.passphrase = get_env(passphrase_env, '') if passphrase_env else None

class RiskConfig:
    def __init__(self):
        self.max_daily_loss = float(get_env('RISK_MAX_DAILY_LOSS', '200'))
        self.max_trades_per_day = int(get_env('RISK_MAX_TRADES_PER_DAY', '100'))

class TradingConfig:
    def __init__(self):
        self.dry_run = get_env('DRY_RUN', 'true').lower() == 'true'
        self.fee_rate = float(get_env('TRADING_FEE_RATE', '0.0005'))
        self.min_profit_threshold = float(get_env('MIN_PROFIT', '0.0015'))
        self.trade_amount_usdt = float(get_env('TRADE_AMOUNT_USDT', '30'))

class Config:
    def __init__(self):
        self.binance = ExchangeConfig('BINANCE_API', 'BINANCE_SECRET')
        self.okx = ExchangeConfig('OKX_API', 'OKX_SECRET', 'OKX_PASSPHRASE')
        self.risk = RiskConfig()
        self.trading = TradingConfig()
        
        # 跨所套利特有配置
        self.cross_exchange_config = {
            'min_profit_threshold': 0.0015,
            'max_spread_history': 100
        }
        
        # 跨所套利币种列表
        self.cross_exchange_symbols = [
            'SOL/USDT', 'AVAX/USDT', 'FET/USDT', 'MATIC/USDT', 'LINK/USDT',
            'UNI/USDT', 'DOT/USDT', 'ATOM/USDT', 'ARB/USDT', 'OP/USDT',
            'NEAR/USDT', 'APT/USDT', 'SUI/USDT', 'SEI/USDT', 'PYTH/USDT'
        ]

    def print_config(self):
        return {
            'dry_run': self.trading.dry_run,
            'min_profit': self.trading.min_profit_threshold,
            'trade_amount': self.trading.trade_amount_usdt,
            'binance_api_configured': bool(self.binance.api_key),
            'okx_api_configured': bool(self.okx.api_key),
            'notion_configured': bool(self.notification.notion_token),  # 添加这行
            'nanobot_configured': bool(self.notification.nanobot_url),  # 添加这行
        }

# 全局实例
config = Config()
