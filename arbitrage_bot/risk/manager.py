"""
风控管理器
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum

from ..config import RiskConfig, TradingConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TradeStatus(Enum):
    """交易状态"""
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TradeRecord:
    """交易记录"""
    id: str
    strategy: str
    symbol: str
    side: str
    amount: float
    price: float
    expected_profit: float
    actual_profit: float = 0
    status: TradeStatus = TradeStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    notes: str = ""


class RiskManager:
    """风控管理器"""
    
    def __init__(self, risk_config: RiskConfig = None, trading_config: TradingConfig = None):
        from ..config import config
        self.risk_config = risk_config or config.risk
        self.trading_config = trading_config or config.trading
        
        self.trades: List[TradeRecord] = []
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.last_trade_time: Optional[datetime] = None
        self.consecutive_losses = 0
        self.cooldown_until: Optional[datetime] = None
        self.open_positions: Dict[str, Dict] = {}
        
        # 每日重置任务
        self._reset_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """启动风控管理器"""
        self._reset_task = asyncio.create_task(self._daily_reset_loop())
        logger.info("风控管理器已启动")
    
    async def stop(self):
        """停止风控管理器"""
        if self._reset_task:
            self._reset_task.cancel()
            try:
                await self._reset_task
            except asyncio.CancelledError:
                pass
        logger.info("风控管理器已停止")
    
    async def _daily_reset_loop(self):
        """每日重置循环"""
        while True:
            now = datetime.now()
            # 计算到明天 00:00 的时间
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            wait_seconds = (tomorrow - now).total_seconds()
            
            await asyncio.sleep(wait_seconds)
            self._reset_daily_stats()
    
    def _reset_daily_stats(self):
        """重置每日统计"""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.cooldown_until = None
        logger.info("每日风控统计已重置")
    
    def can_trade(self, strategy: str = None, symbol: str = None, amount: float = 0) -> tuple[bool, str]:
        """
        检查是否可以交易
        
        Returns:
            (是否可以交易, 原因)
        """
        # 检查冷却期
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).total_seconds() / 60
            return False, f"冷却期中，剩余 {remaining:.1f} 分钟"
        
        # 检查每日最大亏损
        if self.daily_pnl <= -self.risk_config.max_daily_loss:
            return False, f"已达到每日最大亏损限制: {self.daily_pnl:.2f} USDT"
        
        # 检查每日最大交易次数
        if self.daily_trades >= self.risk_config.max_trades_per_day:
            return False, f"已达到每日最大交易次数: {self.daily_trades}"
        
        # 检查持仓大小
        if amount > self.risk_config.max_position_size:
            return False, f"交易金额超过最大持仓限制: {amount} > {self.risk_config.max_position_size}"
        
        # 检查连续亏损
        if self.consecutive_losses >= self.risk_config.max_consecutive_losses:
            self.cooldown_until = datetime.now() + timedelta(minutes=self.risk_config.cooldown_minutes)
            return False, f"连续亏损 {self.consecutive_losses} 次，进入冷却期"
        
        # 检查是否有相同策略的未平仓交易
        if strategy and symbol:
            position_key = f"{strategy}_{symbol}"
            if position_key in self.open_positions:
                return False, f"已有相同策略的未平仓交易: {position_key}"
        
        return True, "OK"
    
    def record_trade_attempt(self, trade: TradeRecord) -> bool:
        """
        记录交易尝试
        
        Returns:
            是否允许执行
        """
        can_trade, reason = self.can_trade(
            strategy=trade.strategy,
            symbol=trade.symbol,
            amount=trade.amount * trade.price
        )
        
        if not can_trade:
            logger.warning(f"交易被拒绝: {reason}")
            trade.status = TradeStatus.CANCELLED
            trade.notes = reason
            self.trades.append(trade)
            return False
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        return True
    
    def record_trade_execution(self, trade_id: str, actual_profit: float):
        """记录交易执行结果"""
        for trade in self.trades:
            if trade.id == trade_id:
                trade.actual_profit = actual_profit
                trade.executed_at = datetime.now()
                trade.status = TradeStatus.EXECUTED
                
                # 更新统计
                self.daily_pnl += actual_profit
                self.daily_trades += 1
                
                # 更新连续亏损
                if actual_profit < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                
                # 添加到持仓
                position_key = f"{trade.strategy}_{trade.symbol}"
                self.open_positions[position_key] = {
                    'trade': trade,
                    'entry_time': datetime.now()
                }
                
                logger.info(
                    f"交易执行记录: {trade_id}, 实际利润: {actual_profit:.4f}, "
                    f"当日总盈亏: {self.daily_pnl:.4f}"
                )
                return
        
        logger.warning(f"未找到交易记录: {trade_id}")
    
    def record_trade_failure(self, trade_id: str, reason: str):
        """记录交易失败"""
        for trade in self.trades:
            if trade.id == trade_id:
                trade.status = TradeStatus.FAILED
                trade.notes = reason
                logger.error(f"交易失败记录: {trade_id}, 原因: {reason}")
                return
    
    def close_position(self, strategy: str, symbol: str):
        """平仓"""
        position_key = f"{strategy}_{symbol}"
        if position_key in self.open_positions:
            del self.open_positions[position_key]
            logger.info(f"仓位已关闭: {position_key}")
    
    def get_stats(self) -> Dict:
        """获取风控统计"""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'consecutive_losses': self.consecutive_losses,
            'open_positions': len(self.open_positions),
            'cooldown_active': self.cooldown_until is not None and datetime.now() < self.cooldown_until,
            'cooldown_remaining_minutes': (
                (self.cooldown_until - datetime.now()).total_seconds() / 60
                if self.cooldown_until and datetime.now() < self.cooldown_until
                else 0
            ),
            'total_trades': len(self.trades),
            'successful_trades': len([t for t in self.trades if t.status == TradeStatus.EXECUTED]),
            'failed_trades': len([t for t in self.trades if t.status == TradeStatus.FAILED]),
        }
    
    def get_open_positions(self) -> List[Dict]:
        """获取当前持仓"""
        return [
            {
                'strategy': pos['trade'].strategy,
                'symbol': pos['trade'].symbol,
                'amount': pos['trade'].amount,
                'entry_price': pos['trade'].price,
                'entry_time': pos['entry_time'].isoformat(),
            }
            for pos in self.open_positions.values()
        ]