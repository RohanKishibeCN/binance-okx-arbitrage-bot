# arbitrage_bot/strategies/__init__.py

# 只导入跨所套利（三角套利已移除）
from .cross_exchange_arbitrage import CrossExchangeArbitrage

__all__ = ['CrossExchangeArbitrage']
