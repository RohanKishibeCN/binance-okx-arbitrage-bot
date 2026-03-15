"""
结构化日志模块
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
import json
import os


class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(
    name: str = "arbitrage_bot",
    log_level: int = logging.INFO,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_json: bool = True
) -> logging.Logger:
    """
    设置结构化日志
    
    Args:
        name: 日志器名称
        log_level: 日志级别
        log_dir: 日志目录
        max_bytes: 单个日志文件最大大小
        backup_count: 备份文件数量
        use_json: 是否使用 JSON 格式
    
    Returns:
        配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 清除现有处理器
    logger.handlers.clear()
    
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 文件处理器
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # 格式化器
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = "arbitrage_bot") -> logging.Logger:
    """获取日志器实例"""
    return logging.getLogger(name)


class LogContext:
    """日志上下文管理器，用于添加额外字段"""
    
    def __init__(self, logger: logging.Logger, **extra):
        self.logger = logger
        self.extra = extra
    
    def debug(self, msg: str, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self._log(logging.CRITICAL, msg, **kwargs)
    
    def _log(self, level: int, msg: str, **kwargs):
        extra_data = {**self.extra, **kwargs}
        self.logger.log(level, msg, extra={'extra_data': extra_data})