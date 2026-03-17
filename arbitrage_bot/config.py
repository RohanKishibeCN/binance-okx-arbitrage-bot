"""
配置管理 - 从环境变量读取（支持 Railway Variables）
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field, validator


def get_env(key: str, default: any = None) -> any:
    """从环境变量读取配置"""
    return os.getenv(key, default)


class ExchangeConfig:
    """交易所配置"""
    def __init__(self, api_key_env: str, secret_env: str, passphrase_env: str = None):
        self.api_key = get_env(api_key_env, '')
        self.secret = get_env(secret_env, '')
        self.passphrase = get_env(passphrase_env, '') if passphrase_env else None
        self.sandbox = get_env('EXCHANGE_SANDBOX', 'false').lower() == 'true'
        self.timeout = 30000
        self.enable_rate_limit = True


class RiskConfig:
    """风控配置"""
    def __init__(self):
        self.max_daily_loss = float(get_env('RISK_MAX_DAILY_LOSS', '200'))
        self.max_position_size = float(get_env('RISK_MAX_POSITION_SIZE', '500'))
        self.max_trades_per_day = int(get_env('RISK_MAX_TRADES_PER_DAY', '50'))
        self.cooldown_minutes = int(get_env('RISK_COOLDOWN_MINUTES', '3'))
        self.max_consecutive_losses = int(get_env('RISK_MAX_CONSECUTIVE_LOSSES', '5'))


class TradingConfig:
    """交易配置"""
    def __init__(self):
        self.dry_run = get_env('DRY_RUN', 'True').lower() == 'true'
        self.fee_rate = float(get_env('TRADING_FEE_RATE', '0.001'))
        self.slippage_buffer = float(get_env('TRADING_SLIPPAGE_BUFFER', '0.0015'))
        self.min_profit_threshold = float(get_env('MIN_PROFIT', '0.004'))
        self.trade_amount_usdt = float(get_env('TRADE_AMOUNT_USDT', '50'))
        self.min_orderbook_depth = float(get_env('MIN_ORDERBOOK_DEPTH', '500'))
        self.check_interval = float(get_env('CHECK_INTERVAL', '0.5'))


class NotificationConfig:
    """通知配置"""
    def __init__(self):
        self.nanobot_url = get_env('NANOBOT_URL')
        self.notion_token = get_env('NOTION_TOKEN')
        self.notion_db_id = get_env('NOTION_DB_ID')
        self.enable_qq_notification = get_env('ENABLE_QQ_NOTIFICATION', 'true').lower() == 'true'
        self.enable_notion_logging = get_env('ENABLE_NOTION_LOGGING', 'true').lower() == 'true'


class Config:
    """全局配置"""
    def __init__(self):
        # 交易所配置
        self.binance = ExchangeConfig('BINANCE_API', 'BINANCE_SECRET')
        self.okx = ExchangeConfig('OKX_API', 'OKX_SECRET', 'OKX_PASSPHRASE')
        
        # 其他配置
        self.risk = RiskConfig()
        self.trading = TradingConfig()
        self.notification = NotificationConfig()
        
        # 三角套利路径配置
        self.triangular_paths = [
            {'name': 'BTC-ETH-USDT', 'symbols': ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']},
            {'name': 'BTC-SOL-USDT', 'symbols': ['BTC/USDT', 'SOL/BTC', 'SOL/USDT']},
            {'name': 'ETH-SOL-USDT', 'symbols': ['ETH/USDT', 'SOL/ETH', 'SOL/USDT']},
            {'name': 'BTC-BNB-USDT', 'symbols': ['BTC/USDT', 'BNB/BTC', 'BNB/USDT']},
            {'name': 'ETH-BNB-USDT', 'symbols': ['ETH/USDT', 'BNB/ETH', 'BNB/USDT']},
            {'name': 'BTC-XRP-USDT', 'symbols': ['BTC/USDT', 'XRP/BTC', 'XRP/USDT']},
            {'name': 'ETH-XRP-USDT', 'symbols': ['ETH/USDT', 'XRP/ETH', 'XRP/USDT']},
            {'name': 'BTC-DOGE-USDT', 'symbols': ['BTC/USDT', 'DOGE/BTC', 'DOGE/USDT']},
            {'name': 'BTC-ADA-USDT', 'symbols': ['BTC/USDT', 'ADA/BTC', 'ADA/USDT']},
            {'name': 'ETH-ADA-USDT', 'symbols': ['ETH/USDT', 'ADA/ETH', 'ADA/USDT']},
        ]
        
        # 跨交易所套利币种
        self.cross_exchange_symbols = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT',
            'ADA/USDT', 'BNB/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT',
            'LTC/USDT', 'BCH/USDT', 'ETC/USDT', 'AVAX/USDT', 'UNI/USDT',
            'ATOM/USDT', 'FIL/USDT', 'TRX/USDT', 'SHIB/USDT', 'APT/USDT'
        ]
    
    def print_config(self):
        """打印配置信息（隐藏敏感信息）"""
        return {
            'dry_run': self.trading.dry_run,
            'min_profit': self.trading.min_profit_threshold,
            'trade_amount': self.trading.trade_amount_usdt,
            'binance_api_configured': bool(self.binance.api_key),
            'okx_api_configured': bool(self.okx.api_key),
            'notion_configured': bool(self.notification.notion_token),
            'nanobot_configured': bool(self.notification.nanobot_url),
        }


# 全局配置实例
config = Config()