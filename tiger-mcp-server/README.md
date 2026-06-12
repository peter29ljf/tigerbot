# Tiger OpenAPI MCP Server

在本机运行的 MCP 服务器，把 Tiger Brokers Open API 暴露给 Claude Code / Cowork / Cursor 等 AI 助手直接调用行情、期权、账户与交易接口。

## 安装依赖

```bash
cd tiger-mcp-server
pip install -r requirements.txt
```

## 配置 Claude Code

在你的项目目录（或 `~/.claude/`）创建 MCP 配置文件：

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

重启 Claude Code 后即可在对话中直接使用 Tiger 工具。

## 工具列表

### 行情

| 工具 | 说明 |
|------|------|
| `get_stock_quote` | 实时报价（优先 Bitget 合约/现货，YF 兜底） |
| `get_stock_bars` | 历史 K 线（day / week / hour / 4hour） |
| `get_option_expirations` | 期权到期日 |
| `get_option_chain` | 完整期权链（OI / IV / Greeks） |
| `get_oi_analysis` | OI 支撑压力分析、Max Pain、PCR（一键） |
| `get_market_status` | 市场交易状态（US / HK） |

### 账户

| 工具 | 说明 |
|------|------|
| `get_account` | 账户总览（净值、可用资金） |
| `get_positions` | 当前持仓 |
| `get_assets` | 资产明细 |
| `get_orders` | 订单查询（含历史） |
| `get_recent_fills` | 已成交订单（检测 TP/SL 出场） |

### 交易

| 工具 | 说明 |
|------|------|
| `place_order` | 下单（LMT / MKT / STP，⚠️ 真实资金） |
| `cancel_order` | 按 order_id 撤单 |
| `cancel_symbol_orders` | 撤销某股票全部未成交挂单 |
| `close_position` | 市价平掉全部持仓（仅正规交易时间） |

> **注意**：Tiger 仅在正规交易时间（9:30–16:00 ET）支持 MKT 和 STP 单。
> 盘前、盘后、夜盘只能使用 LMT 限价单。

## 价格来源优先级（`get_stock_quote`）

1. **Bitget USDT 永续合约**（`SYMBOLUSDT`）— 24/7 实时，无需认证
2. **Bitget 现货**（`SYMBOLUSDT`）— 部分股票有现货对
3. **Bitget 代币化美股**（`R{SYMBOL}USDT`，如 GEV → `RGEVUSDT`）
4. **Yahoo Finance**（按当前 ET session 选对应价格字段）

## 手动测试

```bash
python3 server.py --config ../tiger_openapi_config.properties
```
