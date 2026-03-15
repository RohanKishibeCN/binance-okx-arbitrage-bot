"""
订单执行器
处理订单创建、监控和重试逻辑
"""

import asyncio
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import time

from ..exchanges.base import BaseExchange
from ..utils.logger import get_logger

logger = get_logger(__name__)


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class OrderResult:
    """订单结果"""
    success: bool
    order_id: Optional[str]
    filled: float
    remaining: float
    cost: float
    fee: float
    average_price: float
    status: OrderStatus
    error: Optional[str] = None


class OrderExecutor:
    """订单执行器"""
    
    def __init__(
        self,
        exchange: BaseExchange,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        order_timeout: float = 30.0
    ):
        self.exchange = exchange
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.order_timeout = order_timeout
        self._pending_orders: Dict[str, Dict] = {}
        
    async def execute_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        on_fill: Callable = None
    ) -> OrderResult:
        """
        执行市价单
        
        Args:
            symbol: 交易对
            side: buy 或 sell
            amount: 数量
            on_fill: 成交回调函数
        
        Returns:
            订单结果
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"执行市价单: {symbol} {side} {amount} "
                    f"(尝试 {attempt + 1}/{self.max_retries})"
                )
                
                order = await asyncio.wait_for(
                    self.exchange.create_market_order(symbol, side, amount),
                    timeout=self.order_timeout
                )
                
                if order:
                    result = self._parse_order_result(order)
                    
                    if result.success and on_fill:
                        await on_fill(result)
                    
                    return result
                else:
                    return OrderResult(
                        success=False,
                        order_id=None,
                        filled=0,
                        remaining=amount,
                        cost=0,
                        fee=0,
                        average_price=0,
                        status=OrderStatus.REJECTED,
                        error="Order creation returned None"
                    )
                    
            except asyncio.TimeoutError:
                logger.warning(f"订单超时: {symbol} {side} {amount}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
            except Exception as e:
                logger.error(f"订单执行失败: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    return OrderResult(
                        success=False,
                        order_id=None,
                        filled=0,
                        remaining=amount,
                        cost=0,
                        fee=0,
                        average_price=0,
                        status=OrderStatus.REJECTED,
                        error=str(e)
                    )
        
        return OrderResult(
            success=False,
            order_id=None,
            filled=0,
            remaining=amount,
            cost=0,
            fee=0,
            average_price=0,
            status=OrderStatus.REJECTED,
            error="Max retries exceeded"
        )
    
    async def execute_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        time_in_force: str = 'GTC',
        on_fill: Callable = None
    ) -> OrderResult:
        """
        执行限价单
        
        Args:
            symbol: 交易对
            side: buy 或 sell
            amount: 数量
            price: 价格
            time_in_force: 有效时间 (GTC, IOC, FOK)
            on_fill: 成交回调函数
        
        Returns:
            订单结果
        """
        try:
            logger.info(f"执行限价单: {symbol} {side} {amount} @ {price}")
            
            order = await self.exchange.create_limit_order(symbol, side, amount, price)
            
            if order:
                order_id = order.get('id')
                self._pending_orders[order_id] = {
                    'order': order,
                    'symbol': symbol,
                    'callback': on_fill
                }
                
                # 等待订单成交或超时
                result = await self._wait_for_fill(order_id, symbol)
                return result
            else:
                return OrderResult(
                    success=False,
                    order_id=None,
                    filled=0,
                    remaining=amount,
                    cost=0,
                    fee=0,
                    average_price=0,
                    status=OrderStatus.REJECTED,
                    error="Order creation returned None"
                )
                
        except Exception as e:
            logger.error(f"限价单执行失败: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled=0,
                remaining=amount,
                cost=0,
                fee=0,
                average_price=0,
                status=OrderStatus.REJECTED,
                error=str(e)
            )
    
    async def _wait_for_fill(
        self,
        order_id: str,
        symbol: str,
        max_wait: float = 60.0,
        check_interval: float = 1.0
    ) -> OrderResult:
        """等待订单成交"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                order = await self.exchange.fetch_order(order_id, symbol)
                
                if order:
                    status = order.get('status')
                    filled = float(order.get('filled', 0))
                    
                    if status == 'closed':
                        result = self._parse_order_result(order)
                        
                        # 调用回调
                        if order_id in self._pending_orders:
                            callback = self._pending_orders[order_id].get('callback')
                            if callback:
                                await callback(result)
                            del self._pending_orders[order_id]
                        
                        return result
                    
                    elif status == 'canceled' or status == 'expired':
                        return self._parse_order_result(order)
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"查询订单状态失败: {e}")
                await asyncio.sleep(check_interval)
        
        # 超时，取消订单
        logger.warning(f"订单超时，取消订单: {order_id}")
        await self.cancel_order(order_id, symbol)
        
        return OrderResult(
            success=False,
            order_id=order_id,
            filled=0,
            remaining=0,
            cost=0,
            fee=0,
            average_price=0,
            status=OrderStatus.EXPIRED,
            error="Order timeout"
        )
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        try:
            result = await self.exchange.cancel_order(order_id, symbol)
            if result:
                logger.info(f"订单已取消: {order_id}")
                if order_id in self._pending_orders:
                    del self._pending_orders[order_id]
                return True
            return False
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    def _parse_order_result(self, order: Dict) -> OrderResult:
        """解析订单结果"""
        status_map = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.CLOSED,
            'canceled': OrderStatus.CANCELED,
            'expired': OrderStatus.EXPIRED,
            'rejected': OrderStatus.REJECTED,
        }
        
        status = status_map.get(order.get('status'), OrderStatus.PENDING)
        filled = float(order.get('filled', 0))
        amount = float(order.get('amount', 0))
        
        return OrderResult(
            success=status == OrderStatus.CLOSED and filled > 0,
            order_id=order.get('id'),
            filled=filled,
            remaining=float(order.get('remaining', amount - filled)),
            cost=float(order.get('cost', 0)),
            fee=float(order.get('fee', {}).get('cost', 0)),
            average_price=float(order.get('average', 0)),
            status=status
        )
    
    async def get_pending_orders(self) -> Dict[str, Dict]:
        """获取待处理订单"""
        return self._pending_orders.copy()