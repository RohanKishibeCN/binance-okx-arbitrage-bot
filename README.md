# CEX 套利机器人 v2.0

基于 Python 的加密货币套利机器人，支持三角套利和跨交易所套利策略。

## 特性

- **三角套利**: 在单一交易所内通过 BTC/ETH/USDT 三角路径套利
- **跨交易所套利**: 利用 Binance 和 OKX 之间的价格差异套利
- **双边持仓模式**: 无需等待提币，同时买卖实现即时套利
- **风控系统**: 完整的止损、仓位限制、冷却机制
- **实时监控**: 订单簿深度检查、健康检查、日志记录
- **多渠道通知**: Notion 记录 + QQ 推送

## 架构

```
arbitrage_bot/
├── exchanges/          # 交易所封装
│   ├── base.py        # 交易所基类
│   ├── binance.py     # Binance 实现
│   └── okx.py         # OKX 实现
├── strategies/         # 套利策略
│   ├── triangular.py  # 三角套利
│   └── cross_exchange.py  # 跨所套利
├── risk/              # 风控模块
│   └── manager.py     # 风控管理器
├── execution/         # 订单执行
│   └── executor.py    # 订单执行器
├── notifications/     # 通知模块
│   ├── notion.py      # Notion 通知
│   ├── qq.py          # QQ 通知
│   └── manager.py     # 通知管理器
├── utils/             # 工具模块
│   └── logger.py      # 结构化日志
├── config.py          # 配置管理
└── main.py            # 主入口
```

## 安装

```bash
# 克隆仓库
git clone https://github.com/RohanKishibeCN/binance-okx-arbitrage-bot.git
cd binance-okx-arbitrage-bot

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件填写你的 API 密钥
```

## 配置

编辑 `.env` 文件：

```env
# 交易模式 (True=模拟, False=真实交易)
DRY_RUN=True

# API 密钥
BINANCE_API=your_api_key
BINANCE_SECRET=your_secret
OKX_API=your_api_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase

# Notion (可选)
NOTION_TOKEN=your_notion_token
NOTION_DB_ID=your_database_id

# Nanobot QQ 推送 (可选)
NANOBOT_URL=http://your-server:port

# 交易参数
MIN_PROFIT=0.006              # 最小利润率 0.6%
TRADE_AMOUNT_USDT=50          # 每笔交易金额
TRADING_FEE_RATE=0.001        # 手续费率 0.1%
TRADING_SLIPPAGE_BUFFER=0.002 # 滑点缓冲 0.2%

# 风控参数
RISK_MAX_DAILY_LOSS=100       # 每日最大亏损
RISK_MAX_TRADES_PER_DAY=20    # 每日最大交易次数
```

## 使用

```bash
# 运行机器人
python -m arbitrage_bot.main
```

## 部署到 Railway

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 链接项目
railway link

# 部署
railway up
```

## 套利原理

### 三角套利

路径: USDT → BTC → ETH → USDT

```
毛利润 = (ETH/USDT 卖出价) / (BTC/USDT 买入价 × ETH/BTC 买入价) - 1
净利润 = 毛利润 - 3 × 手续费 - 滑点缓冲
```

### 跨交易所套利

双边持仓模式:
- 在 Binance 和 OKX 都持有 USDT 和交易币种
- 当价差出现时，在低价所买入，同时在高价所卖出
- 无需等待提币，套利即时完成

```
净利润 = 价差 × 交易金额 - 2 × 手续费 - 滑点缓冲
```

## 风控机制

- **每日亏损限制**: 达到限制后停止交易
- **最大持仓限制**: 限制单笔交易金额
- **交易次数限制**: 限制每日交易次数
- **连续亏损冷却**: 连续亏损后进入冷却期
- **订单簿深度检查**: 确保有足够深度成交

## 日志

日志文件位于 `logs/arbitrage_bot.log`，使用 JSON 格式便于分析：

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "level": "INFO",
  "message": "发现套利机会",
  "profit_rate": 0.0085
}
```

## 注意事项

1. **DRY_RUN 模式**: 默认开启模拟模式，不会真实交易
2. **API 权限**: 确保 API 密钥有交易权限
3. **资金安全**: 建议先用小金额测试
4. **网络稳定**: 确保服务器网络稳定，延迟低

## 许可证

MIT