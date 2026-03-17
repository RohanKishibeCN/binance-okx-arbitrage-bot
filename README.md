# CEX 套利机器人 v2.0 - 盈利优化版

基于 Python 的加密货币套利机器人，专注于策略可行性和盈利能力。

## 核心特性

- **多路径三角套利**: 10+ 种套利路径自动选择
- **多币种跨所套利**: 20+ 主流币种监控
- **双边持仓模式**: 即时套利无需提币
- **智能每日推送**: 8点交易记录 + 9点AI分析总结
- **Railway 原生支持**: 通过 Railway Variables 管理配置

## 每日推送流程

```
08:00 → 推送昨日交易记录到 Notion
09:00 → Nanobot 读取记录生成分析总结 → 推送到 Notion
```

## 快速开始

### 1. 部署到 Railway

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 链接项目
railway link

# 设置环境变量（见下方配置说明）
railway variables

# 部署
railway up
```

### 2. 配置 Railway Variables

在 Railway Dashboard → Variables 中配置：

**必需配置：**
```
BINANCE_API=your_binance_api_key
BINANCE_SECRET=your_binance_secret
OKX_API=your_okx_api_key
OKX_SECRET=your_okx_secret
NOTION_TOKEN=your_notion_token
NOTION_DB_ID=your_notion_db_id
NANOBOT_URL=https://your-nanobot.railway.app
```

**可选配置（有默认值）：**
```
DRY_RUN=true                    # 模拟模式
MIN_PROFIT=0.004               # 最小利润率 0.4%
TRADE_AMOUNT_USDT=50           # 每笔交易金额
TRADING_FEE_RATE=0.001         # 手续费率 0.1%
RISK_MAX_DAILY_LOSS=200        # 每日最大亏损
RISK_MAX_TRADES_PER_DAY=50     # 每日最大交易次数
```

### 3. 本地开发

```bash
# 克隆仓库
git clone https://github.com/RohanKishibeCN/binance-okx-arbitrage-bot.git
cd binance-okx-arbitrage-bot

# 安装依赖
pip install -r requirements.txt

# 本地开发时复制 .env.example 为 .env
cp .env.example .env
# 编辑 .env 文件

# 运行
python -m arbitrage_bot.main
```

## 配置说明

### Railway Variables 配置（推荐）

所有配置都通过 Railway Variables 管理，无需修改代码或 .env 文件。

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `BINANCE_API` | ✓ | - | Binance API Key |
| `BINANCE_SECRET` | ✓ | - | Binance API Secret |
| `OKX_API` | ✓ | - | OKX API Key |
| `OKX_SECRET` | ✓ | - | OKX API Secret |
| `OKX_PASSPHRASE` | ✗ | - | OKX API Passphrase |
| `NOTION_TOKEN` | ✓ | - | Notion Integration Token |
| `NOTION_DB_ID` | ✓ | - | Notion Database ID |
| `NANOBOT_URL` | ✓ | - | Nanobot 服务地址 |
| `DRY_RUN` | ✗ | true | 模拟模式开关 |
| `MIN_PROFIT` | ✗ | 0.004 | 最小利润率 |
| `TRADE_AMOUNT_USDT` | ✗ | 50 | 每笔交易金额 |

### 利润率设置建议

| 市场情况 | 建议 MIN_PROFIT | 说明 |
|---------|----------------|------|
| 高波动 | 0.006 - 0.008 | 机会多，竞争激烈 |
| 正常 | 0.004 - 0.006 | 平衡机会和收益 |
| 低波动 | 0.003 - 0.004 | 机会少，需更敏感 |

## 套利策略

### 三角套利路径
- BTC-ETH-USDT
- BTC-SOL-USDT
- ETH-SOL-USDT
- BTC-BNB-USDT
- ETH-BNB-USDT
- BTC-XRP-USDT
- ETH-XRP-USDT
- BTC-DOGE-USDT
- BTC-ADA-USDT
- ETH-ADA-USDT

### 跨所套利币种
BTC, ETH, SOL, XRP, DOGE, ADA, BNB, DOT, MATIC, LINK, LTC, BCH, ETC, AVAX, UNI, ATOM, FIL, TRX, SHIB, APT

## 每日推送内容

### 8:00 - 交易记录
包含内容：
- 交易统计（总交易数、成功/失败、总利润）
- 交易明细列表
- 各策略表现
- 价差统计

### 9:00 - AI 分析总结
由 Nanobot 生成，包含：
- 交易表现分析
- 市场机会分析
- 问题诊断
- 优化建议
- 明日操作计划

## 数据文件

运行后生成以下数据文件：

```
data/
├── triangular_stats_binance.json    # 三角套利统计
├── triangular_stats_okx.json
├── cross_exchange_stats.json        # 跨所套利统计
├── simulated_trades_*.json          # 模拟交易记录
└── arbitrage_bot.log                # 运行日志
```

## 盈利策略

### 阶段 1: 模拟验证（1-3天）
```
DRY_RUN=true
MIN_PROFIT=0.004
```

观察指标：
- 机会出现频率
- 预期收益
- 最佳币种/路径

### 阶段 2: 小金额实盘
```
DRY_RUN=false
TRADE_AMOUNT_USDT=20
MIN_PROFIT=0.005
```

### 阶段 3: 逐步增加
确认盈利后：
- 增加交易金额
- 降低利润率阈值
- 添加更多币种

## 常见问题

### Q: 为什么 DRY_RUN 模式下看不到交易？
A: 可能原因：
1. 利润率阈值太高，降低 `MIN_PROFIT`
2. 市场波动小，机会少
3. API 连接问题，检查日志

### Q: 如何修改配置？
A: 直接在 Railway Dashboard → Variables 修改，无需重新部署。

### Q: 如何查看日志？
A: Railway Dashboard → Deployments → View Logs

### Q: Nanobot 分析没有生成？
A: 检查：
1. `NANOBOT_URL` 是否正确配置
2. Nanobot 服务是否正常运行
3. 查看 Nanobot 日志

## 风险提示

1. **市场风险**: 加密货币价格波动大
2. **执行风险**: 网络延迟、API 故障
3. **资金风险**: 建议先用小金额测试
4. **交易所风险**: API 限制、维护等

## 许可证

MIT