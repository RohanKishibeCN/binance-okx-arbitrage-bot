# arbitrage_bot/config.py

import os
from typing import List, Optional

def get_env(key: str, default=None):
    """从环境变量读取配置"""
    return os.getenv(key, default)

class ExchangeConfig:
    def __init__(self, api_key_env: str, secret_env: str, passphrase_env: str = None):
        self.api_key = get_env(api_key_env, '')
        self.secret = get_env(secret_env, '')
        self.passphrase = get_env(passphrase_env, '') if passphrase_env else None
        self.sandbox = get_env('EXCHANGE_SANDBOX', 'false').lower() == 'true'
        self.timeout = 30000
        self.enable_rate_limit = True
        self.rate_limit = 100  # 每秒最大请求数（Binance默认1200/分钟，但建议保守设置）

class RiskConfig:
    def __init__(self):
        self.max_daily_loss = float(get_env('RISK_MAX_DAILY_LOSS', '200'))
        self.max_position_size = float(get_env('RISK_MAX_POSITION_SIZE', '500'))
        self.max_trades_per_day = int(get_env('RISK_MAX_TRADES_PER_DAY', '50'))
        self.cooldown_minutes = int(get_env('RISK_COOLDOWN_MINUTES', '3'))
        self.max_consecutive_losses = int(get_env('RISK_MAX_CONSECUTIVE_LOSSES', '5'))

class TradingConfig:
    def __init__(self):
        self.dry_run = get_env('DRY_RUN', 'true').lower() == 'true'
        self.fee_rate = float(get_env('TRADING_FEE_RATE', '0.001'))
        self.slippage_buffer = float(get_env('TRADING_SLIPPAGE_BUFFER', '0.0015'))
        self.min_profit_threshold = float(get_env('MIN_PROFIT', '0.0015'))  # 跨所套利降至0.15%
        self.trade_amount_usdt = float(get_env('TRADE_AMOUNT_USDT', '30'))
        self.min_orderbook_depth = float(get_env('MIN_ORDERBOOK_DEPTH', '500'))
        self.check_interval = float(get_env('CHECK_INTERVAL', '0.5'))

class NotificationConfig:
    def __init__(self):
        self.nanobot_url = get_env('NANOBOT_URL')
        self.notion_token = get_env('NOTION_TOKEN')
        self.notion_db_id = get_env('NOTION_DB_ID')
        self.enable_qq_notification = get_env('ENABLE_QQ_NOTIFICATION', 'true').lower() == 'true'
        self.enable_notion_logging = get_env('ENABLE_NOTION_LOGGING', 'true').lower() == 'true'

class Config:
    def __init__(self):
        # 交易所配置
        self.binance = ExchangeConfig('BINANCE_API', 'BINANCE_SECRET')
        self.okx = ExchangeConfig('OKX_API', 'OKX_SECRET', 'OKX_PASSPHRASE')

        # 关键修复：确保 notification 属性存在
        self.risk = RiskConfig()
        self.trading = TradingConfig()
        self.notification = NotificationConfig()  # 这一行必须有！

        # 跨交易所套利币种（优化后的非主流币列表）
        self.cross_exchange_symbols = [
            # Tier 1: 高波动核心山寨币（重点监控）
            'SOL/USDT',      # Solana，波动大
            'AVAX/USDT',     # Avalanche
            'FET/USDT',      # Fetch.ai，AI概念，波动极大
            'LINK/USDT',     # Chainlink
            'DOT/USDT',      # Polkadot
    
            # Tier 2: 中等市值活跃币种
            'UNI/USDT',      # Uniswap
            'ATOM/USDT',     # Cosmos
            'ARB/USDT',      # Arbitrum，L2概念
            'OP/USDT',       # Optimism，L2概念
            'NEAR/USDT',     # NEAR Protocol
    
            # Tier 3: 新公链/生态币（波动极大）
            'APT/USDT',      # Aptos
            'SUI/USDT',      # Sui
            'SEI/USDT',      # Sei，高性能链
            'PYTH/USDT',     # Pyth，预言机
            'JTO/USDT',      # Jito，Solana生态
    
            # Tier 4: 概念/Meme（极高波动，小仓位）
            'WLD/USDT',      # Worldcoin，AI概念
            'ARKM/USDT',     # Arkham，数据分析
            'PEPE/USDT',     # Meme币
            'WIF/USDT',      # Meme币
    
            # 主流币保留但低优先级
            'BTC/USDT',      # 流动性太好，机会极少
            'ETH/USDT',      # 流动性太好，机会极少
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
