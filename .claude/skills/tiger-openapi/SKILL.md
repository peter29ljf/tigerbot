---
name: tiger-openapi
description: |
  Tiger Brokers Open API skill for trading stocks, options, and futures via the tigeropen Python SDK. Covers: real-time quotes, historical bars/klines, option chains, futures data, placing/modifying/canceling orders, account info, positions, assets, and WebSocket push subscriptions.
  MANDATORY TRIGGERS: tiger, tigeropen, tiger brokers, tiger api, tiger trade, tiger quote, tiger order, tiger position, tiger asset, tiger option chain, tiger futures, tiger push, tiger websocket, tiger kline, tiger bars, stock quote via tiger, place order tiger, get positions tiger, tiger SDK, tiger open platform, 老虎, 老虎证券, 老虎API
---

# Tiger OpenAPI Python SDK Skill

This skill enables Claude to interact with Tiger Brokers' Open Platform via the `tigeropen` Python SDK. It covers market data retrieval, order management, account queries, and real-time push subscriptions for stocks, options, and futures.

## Prerequisites

The `tigeropen` package must be installed in the user's Python environment:
```
pip install tigeropen
```

A configuration file is required at the path the user specifies (typically `tiger_openapi_config.properties`). The file contains:
```properties
private_key_pk8=<RSA private key in PKCS8 format>
tiger_id=<developer ID>
account=<trading account number>
license=<license code, e.g. TBNZ>
env=<PROD or SANDBOX>
```

## Architecture Overview

The SDK has four main client classes:

| Client | Purpose | Import |
|--------|---------|--------|
| **QuoteClient** | Market data (quotes, bars, ticks, option chains, futures) | `tigeropen.quote.quote_client` |
| **TradeClient** | Order management + account/position queries | `tigeropen.trade.trade_client` |
| **PushClient** | Real-time WebSocket streaming | `tigeropen.push.push_client` |
| **TigerOpenClientConfig** | Authentication & configuration | `tigeropen.tiger_open_client_config` |

## Quick Reference

For detailed API references with full method signatures and code examples, read the appropriate reference file:

- **`references/client_setup.md`** — How to initialize clients from config file
- **`references/quote_api.md`** — All market data methods (stocks, options, futures, bars, ticks)
- **`references/trade_api.md`** — Order placement, modification, cancellation, and order queries
- **`references/account_api.md`** — Account info, positions, assets
- **`references/push_api.md`** — Real-time WebSocket subscriptions

## Workflow — MCP 模式（推荐）

Tiger API 通过本机运行的 MCP Server 暴露为工具，Cowork 直接调用，无需手写脚本：

1. 确认 MCP Server 已启动（`tiger-mcp-server/server.py`）
2. 直接调用 MCP 工具，无需读取 reference 文件或写代码
3. 以表格或结构化文本返回结果，并做分析解读

### 可用 MCP 工具

| 工具 | 说明 |
|------|------|
| `get_stock_quote` | 股票实时报价 |
| `get_stock_bars` | 历史K线（支持1min～月线）|
| `get_option_expirations` | 期权到期日列表 |
| `get_option_chain` | 期权链（OI/IV/Delta/Gamma/Theta/Vega）|
| `get_oi_analysis` | OI支撑压力分析+走势概率（一键完成）|
| `get_market_status` | 市场开收盘状态 |
| `get_account` | 账户净值/资金/购买力 |
| `get_positions` | 持仓（含未实现盈亏）|
| `get_assets` | 资产（按币种）|
| `get_orders` | 订单历史 |
| `place_order` | ⚠️ 下单（真实交易，需用户确认）|
| `cancel_order` | 撤单 |
| `get_future_bars` | 期货K线 |

## 安装 MCP Server（首次使用）

```bash
cd ~/workspace/tigerskill/tiger-mcp-server
pip install -r requirements.txt
```

将 `claude_mcp_config.json` 内容合并到 `~/.claude/claude_mcp_config.json`，重启 Cowork 即可。

## Important Notes

- MCP Server 在本机运行，有完整网络权限，可直接访问 Tiger API
- 下单操作（`place_order`）是真实交易，执行前必须向用户确认
- Reference 文件（`references/`）仅在需要手写脚本时查阅
