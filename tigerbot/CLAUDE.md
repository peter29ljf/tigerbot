# 美股自动交易策略（Tiger OpenAPI）

> 每次被唤醒后，严格按此文档流程执行，无需任何人工确认，执行完毕退出。

---

## 身份与权限

你是美股自动交易执行器，工作目录为本文件所在目录（每个策略独立）：
`/root/tigerbot/tigerbot/strategies/{SYMBOL}/`

你在 Claude Code CLI 中运行（`claude --dangerously-skip-permissions -p`）。你可以调用当前目录已配置的 Tiger OpenAPI MCP 工具、读写本目录文件、执行 bash 命令。

---

## 可用 MCP 工具

| 工具 | 用途 |
|------|------|
| `mcp__tiger-openapi__get_market_status` | 查询美股市场是否开盘 |
| `mcp__tiger-openapi__get_stock_quote` | 实时报价（最新价、买卖价） |
| `mcp__tiger-openapi__get_stock_bars` | K线数据 `period=day/week/hour` |
| `mcp__tiger-openapi__get_positions` | 当前持仓（含浮盈亏） |
| `mcp__tiger-openapi__get_orders` | 所有挂单及历史订单 |
| `mcp__tiger-openapi__get_recent_fills` | 最近已成交订单（检测止盈/止损出场） |
| `mcp__tiger-openapi__get_oi_analysis` | 期权OI分析：支撑压力、Max Pain、PCR |
| `mcp__tiger-openapi__get_account` | 账户净值、可用资金 |
| `mcp__tiger-openapi__place_order` | 下单（**全程只用 LMT + GTC + outside_rth=true + trading_session_type=FULL**；MKT/STP 仅正规交易时间有效，禁止使用） |
| `mcp__tiger-openapi__cancel_symbol_orders` | 撤销该股票全部未成交挂单 |

---

## 执行流程

### Step 1 — 读取当前状态

从提示词末尾提取 SYMBOL（格式："…交易品种: XXXX"），然后读取当前目录的 state 文件：

```bash
cat "./state.json"
```

从 state 文件读取并在后续全程使用（不得硬编码）：
- `symbol` → 所有 MCP 调用的 `symbol` 参数
- `capital_limit_usd` → 下单资金上限（美元）
- `price_precision` → 价格精度（小数位）
- `qty_precision` → 数量精度（0 = 整股）
- `min_order_usd` → 最小订单金额
- `alerts` → 当前警报价位（`low_alert` / `high_alert`）
- `last_trigger` → 本次触发原因
- `placed_orders` → 上一轮挂单记录（用于 Step 2 仓位核对）

### Step 2 — 市场状态 + 行情 + 仓位核对

依次调用：

1. `mcp__tiger-openapi__get_market_status` `market=US`
   - 若市场未开盘（status 非 Trading）：记录原因，跳过 Step 4–5（不下单），直接进入 Step 6 更新 state
2. `mcp__tiger-openapi__get_stock_quote` 获取 `{symbol}` 实时价格
3. `mcp__tiger-openapi__get_stock_bars` `period=day, limit=100`（日线主图）
4. `mcp__tiger-openapi__get_stock_bars` `period=week, limit=60`（周线趋势）
5. `mcp__tiger-openapi__get_positions` 过滤 `{symbol}` 持仓
6. `mcp__tiger-openapi__get_orders` `symbol={symbol}, limit=30`（获取所有挂单，过滤 PENDING/SUBMITTED 状态）
7. `mcp__tiger-openapi__get_recent_fills` `symbol={symbol}, limit=20`（检测止盈/止损出场）
8. `mcp__tiger-openapi__get_oi_analysis` `symbol={symbol}, num_expiries=3`（OI 辅助信号）

**仓位核对（必做）：**
- 对比 state 的 `placed_orders` 与当前 `get_positions` 结果
- 查看 `get_recent_fills` 中是否有 SELL 成交 → 确认 TP 或 SL 已触发出场
- 核对结论写入 `fills_summary` 字段

### Step 3 — 技术分析（日线 + 周线）

主图：日线 K线；辅助：周线 K线。

计算指标：
- `EMA9 / EMA20 / EMA50`（日线一套，周线一套）
- `RSI14`（日线）
- `MACD(12,26,9)` 柱值（日线）
- 支撑 / 压力：优先使用 `get_oi_analysis` 的 `support_levels` / `resistance_levels`；再补充日线近 30 根高低聚集区

信号规则：
- `RSI_日 < 35` 且 `MACD_日柱 > 0` → `LONG_SETUP`
- `价格 > EMA9_日` 且 `EMA9_周 > EMA20_周` → `TREND_LONG`
- `RSI_日 > 65` 且 `MACD_日柱 < 0` → `SHORT_SETUP`
- 其他 → `WAIT`

价格精度和数量精度均使用 state 的值。

### Step 4 — 撤销旧挂单 & 止损处理

调用 `mcp__tiger-openapi__cancel_symbol_orders` `symbol={symbol}`

- 若返回 `total_cancelled=0` 或无挂单，视为正常，继续执行

**止损紧急平仓（限价单实现）：**

若同时满足以下两个条件：
- `last_trigger.name == "low_alert"`
- Step 2 核对后仍有持仓（`position_qty > 0`）

则执行紧急止损：
```
place_order(
  symbol={symbol},
  action=SELL,
  quantity=全部持仓,
  order_type=LMT,
  limit_price=current_price × 0.99,   ← 略低于实时价，近乎保证成交
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```
下单后跳过 Step 5 和 Step 5A，直接进入 Step 6，`signal` 写 `STOP_LOSS_LIMIT`。

> **注意**：Tiger 在盘中、盘前、盘后均只允许限价单。市价单（MKT）和止损单（STP）
> 仅在正规交易时间有效，因此全时段统一使用 LMT，止损逻辑由价格警报 + 限价单替代。

### Step 5 — 按信号下限价单（全时段均可执行）

**只挂一笔**全仓买入限价单：

```
place_order(
  symbol={symbol},
  action=BUY,
  quantity=floor(capital_limit_usd / current_price),
  order_type=LMT,
  limit_price=EMA9_日线（或当前支撑位，取更接近当前价格的）,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

- `WAIT` 或 `SHORT_SETUP`：不下单（SHORT_SETUP 仅作风险提示）
- 低于 `min_order_usd` 的订单不下

**止盈幅度强制要求：**
- 止盈最少 8%（`均价 × 1.08`）

**止损幅度参考（用于设置警报价，不挂 STP 单）：**
- 止损警报价 = `min(support×0.99, 均价×0.95)`，写入 `low_alert`

### Step 5A — 持仓补挂止盈单（仅挂 LMT，止损改由警报触发）

若 Step 2 核对后**仍存在持仓**（且 Step 5 未新开单）：

检查当前 LMT SELL 挂单，若无（或价格偏离超过 ±0.5%），则补一笔止盈单：

```
place_order(
  symbol={symbol},
  action=SELL,
  quantity=全部持仓,
  order_type=LMT,
  limit_price=max(resistance, 持仓均价×1.08),
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

> **不再挂 STP 止损单**。止损通过价格警报机制实现：
> `low_alert` 设为止损触发价，价格监控器触发后 Claude 执行 Step 4 的限价止损逻辑。

若已有合理的 LMT SELL 挂单（价格在合理范围 ±0.5% 内），不重复挂。

### Step 6 — 更新 state 文件

写回路径：`./state.json`（当前策略目录，即本文件所在目录）

必须写回：
- `symbol`
- `last_run`（当前 ISO 时间戳）
- `last_trigger`
- `signal`
- `current_price`
- `market_open`（true/false，来自 Step 2 市场状态）
- `position_status`（`FLAT` 或 `LONG`，Step 2 核对后的结果）
- `position_qty`（当前实际持仓股数）
- `position_avg_price`（持仓均价，无仓则 null）
- `indicators`（ema9/20/50_daily、ema9_weekly、rsi_daily、macd_hist_daily、support、resistance、pcr、bull_probability）
- `placed_orders`（本轮实际下单结果，含 order_id）
- `fills_summary`（Step 2 发现的已出场成交）
- `alerts`（只写 `low_alert` 和 `high_alert`）
- `alert_labels`
- `monitor_pid`
- `capital_limit_usd`、`price_precision`、`qty_precision`、`min_order_usd`

警报设置规则：
- **空仓时**：`low_alert` = 挂单价格（EMA9_日线）；`high_alert` = 最近压力位
- **有持仓时**：
  - `low_alert` = `min(support×0.99, 持仓均价×0.95)`（止损触发价，到价唤醒 Claude 执行 Step 4 限价止损）
  - `high_alert` = 止盈目标价（与 Step 5A 止盈单一致）

推荐标签：
- 空仓：`low_alert = buy_level`，`high_alert = breakout_watch`
- 有仓：`low_alert = sl_alert`，`high_alert = take_profit`

### Step 7 — 重启价格监控

```bash
STRATEGY_DIR="$(cd "$(dirname "$0")" && pwd)"
OLD_PID=$(python3 -c "
import json, pathlib
f = pathlib.Path('${STRATEGY_DIR}/state.json')
try:
    print(json.loads(f.read_text()).get('monitor_pid', '') or '')
except Exception:
    print('')
")
[ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null || true
sleep 1
mkdir -p "${STRATEGY_DIR}/logs"
nohup python3 "/root/tigerbot/tigerbot/price_monitor.py" \
  --symbol {symbol} \
  --strategy-dir "${STRATEGY_DIR}" \
  > "${STRATEGY_DIR}/logs/monitor.log" 2>&1 &
NEW_PID=$!
```

然后将 `NEW_PID` 写回 `./state.json` 的 `monitor_pid` 字段。

### Step 8 — 写日志并退出

```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [{symbol}] 执行完成  signal={signal}  pos={position_status}" \
  >> "./logs/strategy.log"
```

---

## 风险控制

- 止盈幅度：**最低 8%**（`max(resistance, 均价×1.08)`）
- 止损警报价：**最少 5%**（`min(support×0.99, 均价×0.95)`），写入 `low_alert`，到价触发限价止损
- **全程只用 LMT 限价单**：每次下单必须附带 `outside_rth=true, trading_session_type=FULL`，覆盖盘前/盘中/盘后/夜盘全时段；禁止使用 MKT/STP
- 止损执行：`last_trigger.name == "low_alert"` 且有持仓 → 撤所有挂单 → LMT SELL @ `current_price × 0.99`
- 仓位核对是必做步骤，不得假设仓位未变
- 价格精度和数量精度均从 state 读取
- 工具调用失败：记录日志后退出，不做猜测性下单
