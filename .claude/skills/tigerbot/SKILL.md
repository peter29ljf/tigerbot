---
name: tigerbot
description: |
  自动交易机器人管理技能：启动/停止/查看美股策略，管理 tigerbot 项目下的各品种独立策略目录。
  MANDATORY TRIGGERS: tigerbot, 启动策略, 启动监控, 交易机器人, 策略目录, 策略文件, 启动交易, 停止策略, 查看监控, 查看策略日志, 策略状态, launch strategy, start strategy, trading bot, 美股机器人
---

# Tigerbot 自动交易机器人技能

## 安装路径

此 skill 文件须放置于以下位置之一：

| 作用范围 | 安装路径 |
|---------|---------|
| **项目级**（推荐，仅对本仓库生效） | `{repo_root}/.claude/skills/tigerbot/SKILL.md` |
| **用户级**（对当前用户所有项目生效） | `~/.claude/skills/tigerbot/SKILL.md` |

克隆本仓库后，文件已在正确的项目级位置（`.claude/skills/tigerbot/`），无需额外操作。

## 项目位置

```
/root/tigerbot/tigerbot/    ← 主目录（所有命令在此执行）
```

## 目录结构

```
tigerbot/
├── CLAUDE.md              # 主模板（launch 自动复制到各策略目录）
├── config.json            # 各品种参数（资金上限、初始警报价）
├── price_monitor.py       # 价格监控进程
├── launch.sh              # 一键启动脚本
└── strategies/
    └── {SYMBOL}/          # 每个品种独立目录
        ├── CLAUDE.md      # 策略文档（从主模板复制）
        ├── state.json     # 实时状态（仓位/警报/指标）
        └── logs/
            ├── monitor.log    # 价格监控
            ├── strategy.log   # 策略摘要
            ├── claude_run.log # Claude 完整输出
            └── first_run.log  # 首次启动输出
```

## 常用操作

### 启动策略

```bash
cd /root/tigerbot/tigerbot
./launch.sh TSLA          # 前台启动（看完整输出）
./launch.sh TSLA &        # 后台启动
```

launch 会自动：
1. 创建 `strategies/TSLA/` 目录
2. 复制最新 `CLAUDE.md` 到策略目录
3. 从 `config.json` 初始化 `state.json`（首次）
4. 在策略目录内运行 Claude Code CLI 执行一次完整策略
5. 后台启动价格监控器（盘中每 30s 轮询，触发时自动唤醒 Claude）

### 并行启动多个品种

```bash
cd /root/tigerbot/tigerbot
./launch.sh TSLA & ./launch.sh NVDA & ./launch.sh AAPL &
```

### 查看运行状态

```bash
# 查看所有监控进程
ps aux | grep price_monitor.py

# 查看某品种实时状态
cat /root/tigerbot/tigerbot/strategies/TSLA/state.json | python3 -m json.tool

# 实时日志
tail -f /root/tigerbot/tigerbot/strategies/TSLA/logs/monitor.log
tail -f /root/tigerbot/tigerbot/strategies/TSLA/logs/strategy.log
tail -f /root/tigerbot/tigerbot/strategies/TSLA/logs/claude_run.log
```

### 停止策略

```bash
# 停止单个品种监控
pkill -f "price_monitor.py.*--symbol.*TSLA"

# 停止所有监控
pkill -f price_monitor.py
```

## 新增品种

1. 编辑 `/root/tigerbot/tigerbot/config.json`，在 `symbols` 下添加：

```json
{
  "symbols": {
    "NVDA": {
      "low_alert": 100.0,
      "high_alert": 150.0,
      "capital_usd": 2000.0,
      "price_precision": 2,
      "qty_precision": 0,
      "min_order_usd": 10.0
    }
  }
}
```

2. 启动：`cd /root/tigerbot/tigerbot && ./launch.sh NVDA`

## 修改已有策略的警报价

直接编辑对应 `state.json`：

```bash
python3 -c "
import json
from pathlib import Path
p = Path('/root/tigerbot/tigerbot/strategies/TSLA/state.json')
d = json.loads(p.read_text())
d['alerts']['low_alert'] = 280.0
d['alerts']['high_alert'] = 350.0
p.write_text(json.dumps(d, indent=2))
print('已更新警报价')
"
```

## state.json 关键字段说明

| 字段 | 说明 |
|------|------|
| `position_status` | `FLAT`（空仓）或 `LONG`（持仓） |
| `position_qty` | 当前持仓股数 |
| `position_avg_price` | 持仓均价 |
| `alerts.low_alert` | 下跌警报价（触发止损或买入） |
| `alerts.high_alert` | 上涨警报价（触发突破分析） |
| `signal` | 最近信号：`LONG_SETUP` / `TREND_LONG` / `WAIT` / `STOP_LOSS_LIMIT` |
| `last_run` | 最近一次 Claude 执行时间 |
| `monitor_pid` | 价格监控进程 PID |
| `placed_orders` | 本轮挂单详情 |

## 策略逻辑概述（agent 执行时的依据）

Claude 被唤醒后执行 `strategies/{SYMBOL}/CLAUDE.md` 中定义的 8 步流程：

1. 读取 `./state.json`
2. 查市场状态、报价、K线、持仓、挂单、成交记录、OI 分析
3. 计算 EMA9/20/50、RSI14、MACD 信号
4. 撤旧挂单；若触发 `low_alert` 且有持仓 → 限价止损
5. 按信号挂限价买单（`LONG_SETUP` / `TREND_LONG`）
6. 补挂止盈单（若有持仓且无合理卖单）
7. 写回 `./state.json`
8. 重启价格监控，写策略日志

**全程只用 LMT 限价单**（Tiger 盘前/盘后不支持 MKT/STP）。

## 前置条件检查

```bash
# 检查 Claude Code CLI
claude --version

# 检查 Python 依赖
python3 -c "import tigeropen, pytz; print('依赖OK')"

# 检查 MCP 配置
cat /root/tigerbot/tigerbot/.mcp.json 2>/dev/null || echo "缺少 .mcp.json"
```
