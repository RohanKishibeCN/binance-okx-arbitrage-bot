"""
配置管理 - 使用 Pydantic 进行配置验证
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field, validator


class ExchangeConfig(BaseSettings):
    """交易所配置"""
    api_key: str = Field(default="", env="BINANCE_API")
    secret: str = Field(default="", env="BINANCE_SECRET")
    passphrase: Optional[str] = Field(default=None, env="OKX_PASSPHRASE")
    sandbox: bool = Field(default=True, env="EXCHANGE_SANDBOX")
    timeout: int = 30000
    enable_rate_limit: bool = True


class RiskConfig(BaseSettings):
    """风控配置"""
    max_daily_loss: float = Field(default=100.0, env="RISK_MAX_DAILY_LOSS")
    max_position_size: float = Field(default=500.0, env="RISK_MAX_POSITION_SIZE")
    max_trades_per_day: int = Field(default=20, env="RISK_MAX_TRADES_PER_DAY")
    cooldown_minutes: int = Field(default=5, env="RISK_COOLDOWN_MINUTES")
    max_consecutive_losses: int = Field(default=3, env="RISK_MAX_CONSECUTIVE_LOSSES")
    
    @validator('max_daily_loss')
    def validate_max_daily_loss(cls, v):
        if v <= 0:
            raise ValueError('max_daily_loss must be positive')
        return v


class TradingConfig(BaseSettings):
    """交易配置"""
    dry_run: bool = Field(default=True, env="DRY_RUN")
    fee_rate: float = Field(default=0.001, env="TRADING_FEE_RATE")
    slippage_buffer: float = Field(default=0.002, env="TRADING_SLIPPAGE_BUFFER")
    min_profit_threshold: float = Field(default=0.006, env="MIN_PROFIT")
    trade_amount_usdt: float = Field(default=50.0, env="TRADE_AMOUNT_USDT")
    min_orderbook_depth: float = Field(default=1000.0, env="MIN_ORDERBOOK_DEPTH")
    check_interval: float = Field(default=1.0, env="CHECK_INTERVAL")
    
    @validator('min_profit_threshold')
    def validate_min_profit(cls, v):
        if v < 0.003:
            raise ValueError('min_profit_threshold too low, risk of loss')
        return v


class NotificationConfig(BaseSettings):
    """通知配置"""
    nanobot_url: Optional[str] = Field(default=None, env="NANOBOT_URL")
    notion_token: Optional[str] = Field(default=None, env="NOTION_TOKEN")
    notion_db_id: Optional[str] = Field(default=None, env="NOTION_DB_ID")
    enable_qq_notification: bool = Field(default=True, env="ENABLE_QQ_NOTIFICATION")
    enable_notion_logging: bool = Field(default=True, env="ENABLE_NOTION_LOGGING")


class Config(BaseSettings):
    """全局配置"""
    # 交易所配置
    binance: ExchangeConfig = ExchangeConfig(
        api_key=os.getenv('BINANCE_API', ''),
        secret=os.getenv('BINANCE_SECRET', '')
    )
    okx: ExchangeConfig = ExchangeConfig(
        api_key=os.getenv('OKX_API', ''),
        secret=os.getenv('OKX_SECRET', ''),
        passphrase=os.getenv('OKX_PASSPHRASE', '')
    )
    
    # 其他配置
    risk: RiskConfig = RiskConfig()
    trading: TradingConfig = TradingConfig()
    notification: NotificationConfig = NotificationConfig()
    
    # 交易对配置
    triangular_symbols: List[str] = ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']
    cross_exchange_symbols: List[str] = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT']
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


# 全局配置实例
config = Config()