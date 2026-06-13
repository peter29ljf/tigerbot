# tigerbot — Tiger OpenAPI 自动交易机器人

基于 Claude Code CLI 驱动的美股自动交易系统，通过 Tiger Brokers Open API 执行多股票全仓限价交易策略，支持并行监控多个品种。

## 项目结构

```
tigerbot/
├── CLAUDE.md              # 主模板（每次 launch 自动复制到策略目录）
├── config.json            # 各股票默认参数（资金、警报价位、精度）
├── price_monitor.py       # 价格监控器（触发 Claude 执行策略）
├── launch.sh              # 一键启动脚本
├── .mcp.json.example      # MCP 配置模板（复制后填入真实路径）
└── strategies/
    └── {SYMBOL}/          # 每个品种独立目录（launch 自动创建）
        ├── CLAUDE.md      # 策略文档（从主模板复制）
        ├── state.json     # 仓位/警报/订单状态
        └── logs/
            ├── monitor.log     # 价格监控日志
            ├── strategy.log    # 策略执行摘要
            ├── claude_run.log  # Claude Code CLI 完整输出
            └── first_run.log   # 首次启动输出
```

## 前置条件

1. **Tiger Brokers Open API** 凭证（`tiger_openapi_config.properties`）
2. **Claude Code CLI** 已安装：`npm install -g @anthropic-ai/claude-code`
3. Python 依赖：

```bash
pip install tigeropen pytz mcp pandas numpy
```

## 快速开始

### 1. 配置 MCP

```bash
cp .mcp.json.example .mcp.json
# 编辑 .mcp.json，把路径替换为你机器上的实际路径
```

`.mcp.json` 示例：
```json
{
  "mcpServers": {
    "tiger-openapi": {
      "command": "python3",
      "args": [
        "/path/to/tigermcp/tiger-mcp-server/server.py",
        "--config",
        "/path/to/tigermcp/tiger_openapi_config.properties"
      ]
    }
  }
}
```

### 2. 配置股票参数

编辑 `config.json`，按需修改各股票的资金上限和初始警报价位：

```json
{
  "symbols": {
    "TSLA": {
      "low_alert": 250.0,
      "high_alert": 300.0,
      "capital_usd": 2000.0
    }
  }
}
```

### 3. 启动

```bash
chmod +x launch.sh
./launch.sh TSLA
```

脚本会：
1. 创建 `strategies/TSLA/` 目录
2. 从主模板复制最新 `CLAUDE.md` 到策略目录
3. 从 `config.json` 初始化 `strategies/TSLA/state.json`
4. 在策略目录内执行一次完整策略分析（Claude Code CLI）
5. 后台启动价格监控器（每 30 秒轮询，仅盘中）

## 多股票并行

```bash
./launch.sh TSLA &
./launch.sh NVDA &
./launch.sh GEV &
```

每个品种完全独立：策略文件、state、日志、监控进程互不干扰。

## 策略概述

- **技术分析**：日线 + 周线 EMA9/20/50、RSI14、MACD，OI 支撑压力
- **信号**：`LONG_SETUP`（RSI<35+MACD↑）、`TREND_LONG`（价格>EMA9+周线趋势）
- **下单**：全仓一笔 GTC 限价买入（LMT）
- **止盈**：单独一笔 GTC 限价卖出（LMT），目标 ≥ 均价 × 1.08
- **止损**：通过价格警报触发，到价后 Claude 挂 `当前价 × 0.99` 的限价卖单

> Tiger 盘前/盘后/夜盘只支持 LMT 限价单，系统全时段统一使用 LMT。

## 日志查看

```bash
# 价格监控
tail -f strategies/TSLA/logs/monitor.log

# 策略执行
tail -f strategies/TSLA/logs/claude_run.log

# 策略摘要
tail -f strategies/TSLA/logs/strategy.log

# 停止某品种监控
pkill -f "price_monitor.py.*--symbol.*TSLA"
```

## 管理多个策略

```bash
# 查看所有运行中的监控进程
ps aux | grep price_monitor.py

# 查看所有策略目录
ls strategies/

# 查看某品种当前状态
cat strategies/TSLA/state.json | python3 -m json.tool

# 停止所有监控
pkill -f price_monitor.py
```

## 价格来源

价格监控器（`price_monitor.py`）按以下优先级获取实时价格：

1. **Bitget 永续合约**（`TSLAUSDT` 等）— 24/7，无需认证
2. **Bitget 现货**（`SYMBOLUSDT`）
3. **Bitget 代币化美股**（`R{SYMBOL}USDT`，如 GEV → `RGEVUSDT`）
4. **Yahoo Finance**（按盘前/盘中/盘后/夜盘 session 选正确字段）

## 安全说明

- `tiger_openapi_config.properties` 含私钥，已加入 `.gitignore`，勿提交
- `tigerbot/.mcp.json` 含本机绝对路径，已加入 `.gitignore`，使用 `.mcp.json.example` 模板
- `strategies/*/state.json` 含账户仓位信息，已加入 `.gitignore`
