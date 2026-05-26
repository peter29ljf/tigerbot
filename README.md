# tigermcp

Tiger Brokers Open API 的 MCP 服务器，供 Claude Code / Cowork / Cursor 等 AI 助手调用行情、期权、账户与交易接口。

## 目录结构

```
tigermcp/
├── tiger-mcp-server/          # MCP 服务主程序
├── .claude/skills/tiger-openapi/  # Claude skill 与 API 参考文档
└── tiger_openapi_config.properties.example
```

## 快速开始

1. 复制配置模板并填入你的 Tiger Open API 凭证：

```bash
cp tiger_openapi_config.properties.example tiger_openapi_config.properties
# 编辑 tiger_openapi_config.properties
```

2. 安装依赖：

```bash
cd tiger-mcp-server
pip install -r requirements.txt
```

3. 在 `~/.claude/claude_mcp_config.json`（或 Cursor MCP 配置）中注册服务，详见 [tiger-mcp-server/README.md](tiger-mcp-server/README.md)。

## 安全说明

`tiger_openapi_config.properties` 含私钥与账户信息，已加入 `.gitignore`，请勿提交到版本库。
