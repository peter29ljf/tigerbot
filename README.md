# tigermcp

Tiger Brokers Open API 的 MCP 服务器 + AI 自动交易机器人，供 Claude Code / Cowork / Cursor 等 AI 助手调用行情、期权、账户与交易接口。

## 目录结构

```
tigermcp/
├── tiger-mcp-server/          # MCP 服务主程序（15 个工具）
│   ├── server.py
│   ├── requirements.txt
│   └── README.md
├── tigerbot/                  # Claude Code CLI 自动交易机器人
│   ├── CLAUDE.md              # 策略文档
│   ├── config.json            # 股票参数
│   ├── price_monitor.py       # 价格监控器
│   ├── launch.sh              # 一键启动
│   ├── .mcp.json.example      # MCP 配置模板
│   └── README.md
├── tiger_openapi_config.properties.example   # API 凭证模板
└── .claude/skills/tiger-openapi/             # Tiger API 参考文档
```

## 快速开始

### 1. 配置 Tiger API 凭证

```bash
cp tiger_openapi_config.properties.example tiger_openapi_config.properties
# 编辑 tiger_openapi_config.properties，填入你的 Tiger Open API 凭证
```

### 2. 安装依赖

```bash
cd tiger-mcp-server
pip install -r requirements.txt
```

### 3a. 仅使用 MCP 工具（Claude Code / Cowork）

参见 [tiger-mcp-server/README.md](tiger-mcp-server/README.md)。

### 3b. 启动自动交易机器人

```bash
cd tigerbot
cp .mcp.json.example .mcp.json
# 编辑 .mcp.json，填入真实路径
./launch.sh TSLA
```

参见 [tigerbot/README.md](tigerbot/README.md)。

## 主要特性

- **15 个 MCP 工具**：行情（实时报价、K线、期权链、OI分析）+ 账户（持仓、订单、成交）+ 交易（下单、撤单、平仓）
- **多价格来源**：Bitget 合约 → Bitget 现货 → Bitget 代币化美股（R 前缀）→ Yahoo Finance，覆盖 24/7 包括夜盘
- **全限价单**：Tiger 盘前/盘后/夜盘只支持 LMT，系统全时段统一限价，止损通过价格警报触发
- **多品种并行**：每个股票独立 state / 日志 / 监控进程

## 安全说明

`tiger_openapi_config.properties` 含私钥与账户信息，已加入 `.gitignore`，**请勿提交到版本库**。
