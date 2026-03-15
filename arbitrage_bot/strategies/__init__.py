"""策略模块"""

from .triangular import TriangularArbitrage
from .cross_exchange import CrossExchangeArbitrage

__all__ = ['TriangularArbitrage', 'CrossExchangeArbitrage']