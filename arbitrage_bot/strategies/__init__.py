# arbitrage_bot/strategies/__init__.py

from .cross_exchange_arbitrage import CrossExchangeArbitrage
from .triangular_arbitrage import TriangularArbitrage

__all__ = ['CrossExchangeArbitrage', 'TriangularArbitrage']
