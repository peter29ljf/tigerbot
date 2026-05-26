# Tiger OpenAPI MCP Server

在本机运行的 MCP 服务器，把 Tiger Brokers Open API 暴露给 Cowork / Claude Code 直接调用。

## 安装

```bash
cd ~/workspace/tigerskill/tiger-mcp-server
pip install -r requirements.txt
```

## 配置 Cowork / Claude Code

编辑 `~/.claude/claude_mcp_config.json`（没有则新建）：

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

保存后**重启 Cowork**，即可在对话中直接说：
- "查一下 NVDA 的实时报价"
- "分析 NVDA 期权 OI，找支撑位和压力位"
- "查我的持仓"
- "查账户资金"

## 手动测试（可选）

```bash
python3 server.py --config ../tiger_openapi_config.properties
```

## 工具列表

| 工具 | 说明 |
|------|------|
| `get_stock_quote` | 股票实时报价 |
| `get_stock_bars` | 历史K线 |
| `get_option_expirations` | 期权到期日 |
| `get_option_chain` | 完整期权链（OI/IV/Greeks） |
| `get_oi_analysis` | OI支撑压力分析（一键） |
| `get_market_status` | 市场交易状态 |
| `get_account` | 账户总览 |
| `get_positions` | 持仓查询 |
| `get_assets` | 资产查询 |
| `get_orders` | 订单查询 |
| `place_order` | 下单（⚠️ 真实交易） |
| `cancel_order` | 撤单 |
| `get_future_bars` | 期货K线 |
