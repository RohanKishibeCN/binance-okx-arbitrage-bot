# CEX 套利机器人 v2.0 - 盈利优化版

基于 Python 的加密货币套利机器人，专注于策略可行性和盈利能力。

## 核心优化

### 1. 多路径三角套利
- 支持 10+ 种三角套利路径
- 自动选择最优路径
- 价差统计和机会频率分析

### 2. 多币种跨所套利
- 监控 20+ 个主流币种
- 双边持仓模式，即时套利
- 动态阈值调整

### 3. 模拟交易验证
- DRY_RUN 模式下完整模拟
- 记录预期收益
- 验证策略可行性

### 4. 实时统计分析
- 价差历史记录
- 机会出现频率统计
- 预期收益计算

## 支持的套利路径

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

## 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/RohanKishibeCN/binance-okx-arbitrage-bot.git
cd binance-okx-arbitrage-bot
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件填写你的 API 密钥
```

### 4. 运行（模拟模式）
```bash
python -m arbitrage_bot.main
```

## 配置说明

### 关键配置项

```env
# 交易模式 (重要！)
DRY_RUN=True  # True=模拟，False=真实交易

# 最小利润率 (建议 0.3% - 0.8%)
MIN_PROFIT=0.004

# 每笔交易金额
TRADE_AMOUNT_USDT=50

# 风控配置
RISK_MAX_DAILY_LOSS=200
RISK_MAX_TRADES_PER_DAY=50
```

### 利润率设置建议

| 市场情况 | 建议 MIN_PROFIT | 说明 |
|---------|----------------|------|
| 高波动 | 0.006 - 0.008 | 机会多，但竞争激烈 |
| 正常 | 0.004 - 0.006 | 平衡机会和收益 |
| 低波动 | 0.003 - 0.004 | 机会少，需要更敏感 |

## 套利原理

### 三角套利

路径: USDT → A → B → USDT

```
毛利润 = (B/USDT 卖出价) / (A/USDT 买入价 × B/A 买入价) - 1
净利润 = 毛利润 - 3 × 手续费 - 滑点缓冲
```

### 跨所套利

双边持仓模式:
- 在 Binance 和 OKX 都持有 USDT 和币种
- 检测到价差后，在低价所买入，同时在高价所卖出
- 无需等待提币，套利几乎是即时的

```
净利润 = 价差 × 交易金额 - 2 × 手续费 - 滑点缓冲
```

## 盈利策略

### 1. 先跑模拟模式
```env
DRY_RUN=True
MIN_PROFIT=0.004
```

运行几天，观察：
- 机会出现频率
- 预期收益
- 最佳币种/路径

### 2. 调整参数
根据模拟结果调整：
- 降低 MIN_PROFIT 增加机会
- 增加 TRADE_AMOUNT_USDT 提高收益
- 调整监控币种

### 3. 小金额实盘
```env
DRY_RUN=False
TRADE_AMOUNT_USDT=20
MIN_PROFIT=0.005
```

### 4. 逐步增加
确认盈利后：
- 增加交易金额
- 降低利润率阈值
- 添加更多币种

## 数据文件

运行后会生成以下数据文件：

```
data/
├── triangular_stats_binance.json  # Binance 三角套利统计
├── triangular_stats_okx.json      # OKX 三角套利统计
├── cross_exchange_stats.json      # 跨所套利统计
├── simulated_trades_binance.json  # 模拟交易记录
├── simulated_trades_okx.json
├── simulated_trades_cross.json
└── arbitrage_bot.log              # 运行日志
```

## 监控指标

### 关键指标

1. **机会频率**: 每小时出现多少次套利机会
2. **成功率**: 实际成交的比例
3. **平均利润**: 每笔交易的平均收益
4. **最大回撤**: 单日最大亏损

### 日志输出示例

```
🎯 发现三角套利机会: Binance | 路径: BTC-ETH-USDT | 利润率: 0.65% | 净利润: 0.32 USDT
[DRY RUN] 模拟三角套利: BTC-ETH-USDT | 预期利润: 0.32 USDT | 累计模拟交易: 15

📊 跨所套利统计 (Binance <-> OKX)
  BTC/USDT      | 检查:  1250 | 机会:   23 ( 1.84%) | 最大:  0.89% | 平均:  0.12%
  ETH/USDT      | 检查:  1250 | 机会:   18 ( 1.44%) | 最大:  0.76% | 平均:  0.08%
  模拟总收益: 12.45 USDT (56 笔)
```

## 部署到 Railway

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 链接项目
railway link

# 设置环境变量
railway variables set DRY_RUN=True
railway variables set BINANCE_API=your_api_key
railway variables set BINANCE_SECRET=your_secret
# ... 其他变量

# 部署
railway up
```

## 常见问题

### Q: 为什么 DRY_RUN 模式下看不到交易？
A: 可能是：
1. 利润率阈值设置太高，降低 MIN_PROFIT
2. 市场波动小，机会本来就少
3. API 连接有问题，检查日志

### Q: 真实交易会亏损吗？
A: 可能的原因：
1. 滑点过大，增加 SLIPPAGE_BUFFER
2. 执行延迟，检查服务器延迟
3. 深度不足，增加 MIN_ORDERBOOK_DEPTH

### Q: 如何提高收益？
A: 建议：
1. 增加监控币种数量
2. 降低利润率阈值（但要小心）
3. 增加每笔交易金额
4. 使用更低延迟的服务器

## 风险提示

1. **市场风险**: 加密货币价格波动大，可能亏损
2. **执行风险**: 网络延迟、API 故障可能导致执行失败
3. **资金风险**: 建议先用小金额测试
4. **交易所风险**: API 限制、维护等可能影响交易

## 许可证

MIT