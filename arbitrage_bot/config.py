"""
配置管理 - 从环境变量读取（支持 Railway Variables）
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


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
        
        # 三角套利路径配置（保留但降低优先级，改为非主流币组合）
        self.triangular_paths = [
            {'name': 'SOL-AVAX-USDT', 'symbols': ['SOL/USDT', 'AVAX/SOL', 'AVAX/USDT']},
            {'name': 'MATIC-FET-USDT', 'symbols': ['MATIC/USDT', 'FET/MATIC', 'FET/USDT']},
            {'name': 'LINK-UNI-USDT', 'symbols': ['LINK/USDT', 'UNI/LINK', 'UNI/USDT']},
            {'name': 'DOT-ATOM-USDT', 'symbols': ['DOT/USDT', 'ATOM/DOT', 'ATOM/USDT']},
            {'name': 'AVAX-FET-USDT', 'symbols': ['AVAX/USDT', 'FET/AVAX', 'FET/USDT']},
        ]
        
        # 跨交易所套利币种（扩展到中高市值非主流币，保持双边持仓）
        self.cross_exchange_symbols = [
            # 原主流币（降低权重，保留作为基准）
            'BTC/USDT',
            'ETH/USDT',
            
            # 新增：中高市值币（波动大，价差机会多）
            'SOL/USDT',      # Solana - 波动率高
            'AVAX/USDT',     # Avalanche - 生态活跃
            'MATIC/USDT',    # Polygon - 但注意已更名为POL
            'FET/USDT',      # Fetch.ai - AI概念，波动极大
            'LINK/USDT',     # Chainlink - 预言机龙头
            'UNI/USDT',      # Uniswap - DeFi蓝筹
            'DOT/USDT',      # Polkadot - 跨链概念
            'ATOM/USDT',     # Cosmos - 生态币
            'ARB/USDT',      # Arbitrum - L2概念
            'OP/USDT',       # Optimism - L2概念
            'NEAR/USDT',     # NEAR Protocol
            'APT/USDT',      # Aptos - 新公链
            'SUI/USDT',      # Sui - 新公链
            'SEI/USDT',      # Sei - 高性能链
            'PYTH/USDT',     # Pyth - 预言机新贵，波动大
            'JTO/USDT',      # Jito - Solana生态，高波动
            'WLD/USDT',      # Worldcoin - AI概念，波动极大
            'ARKM/USDT',     # Arkham - 数据分析，新币波动大
            'PEPE/USDT',     # Meme币 - 极高波动（小仓位）
            'WIF/USDT',      # Meme币 - 极高波动（小仓位）
        ]

        # 策略权重配置（新增）
        self.strategy_weights = {
            'cross_exchange': 0.7,    # 跨所套利权重 70%
            'triangular': 0.3,         # 三角套利权重 30%
        }

        # 跨所套利特有配置
        self.cross_exchange_config = {
            'min_profit_threshold': 0.0015,  # 跨所门槛更低（0.15%），双边持仓无提币成本
            'check_interval_fast': 0.2,      # 快速检查间隔（200ms）
            'check_interval_slow': 1.0,      # 慢速检查间隔（用于低优先级币种）
            'depth_validation': True,        # 启用深度验证
            'max_spread_history': 100,       # 保存最近100个价差用于动态阈值
        }
    
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
