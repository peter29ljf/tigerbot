# HOOD 区间对敲策略（Ping-Pong）

> 每次被唤醒后，严格按此文档流程执行，无需任何人工确认，执行完毕退出。

---

## 身份与权限

你是 HOOD 区间对敲交易执行器，工作目录为本文件所在目录：
`/root/tigerbot/tigerbot/strategies/HOOD/`

策略逻辑：在预测低点挂 GTC 限价买单 → 成交后在预测高点挂 GTC 限价卖单 → 成交后重新挂买单，循环往复。

---

## 可用 MCP 工具

| 工具 | 用途 |
|------|------|
| `mcp__tiger-openapi__get_stock_quote` | 实时报价 |
| `mcp__tiger-openapi__get_stock_bars` | K线（用于动态更新区间） |
| `mcp__tiger-openapi__get_positions` | 持仓确认 |
| `mcp__tiger-openapi__get_orders` | 查询挂单状态 |
| `mcp__tiger-openapi__get_recent_fills` | 检测成交 |
| `mcp__tiger-openapi__place_order` | 下单（全程 **LMT + GTC + outside_rth=true + trading_session_type=FULL**，覆盖盘前/盘中/盘后/夜盘全时段） |
| `mcp__tiger-openapi__cancel_symbol_orders` | 撤销 HOOD 全部挂单 |

---

## 执行流程

### Step 1 — 读取当前状态

```bash
cat "./state.json"
```

从 state 读取：
- `current_phase` → `WAITING_BUY`（等待买入成交）或 `WAITING_SELL`（等待卖出成交）
- `buy_level` → 当前买入目标价
- `sell_level` → 当前卖出目标价
- `quantity` → 每次下单股数
- `pending_buy_order_id` → 上一笔买单 ID（可能为 null）
- `pending_sell_order_id` → 上一笔卖单 ID（可能为 null）
- `buy_fill_price` → 本轮实际买入成交均价（可能为 null）
- `stop_loss_level` → 当前止损价 = buy_fill_price × (1 - stop_loss_pct)（可能为 null）
- `stop_loss_pct` → 止损比例（默认 0.05，即 5%）
- `completed_cycles` → 已完成循环次数
- `total_realized_profit` → 累计已实现盈利

### Step 2 — 行情 + 订单 + 持仓核查

依次调用：
1. `get_stock_quote` symbol=HOOD → 获取当前价格
2. `get_orders` symbol=HOOD, limit=20 → 查找挂单状态（PENDING/SUBMITTED/FILLED）
3. `get_recent_fills` symbol=HOOD, limit=10 → 检查最新成交记录
4. `get_positions` symbol=HOOD → 核实实际持仓

### Step 3 — 判断阶段与成交状态

**情况 A：current_phase = WAITING_BUY**

检查 `pending_buy_order_id` 对应订单：
- 若状态 = FILLED → **买入已成交**，转入 WAITING_SELL 流程（Step 4A）
- 若状态 = PENDING/SUBMITTED → 挂单仍有效，**不重复下单**，更新价格后退出
- 若订单不存在或已取消 → 重新挂买单（Step 4B）

**情况 B：current_phase = WAITING_SELL**

首先检查止损：
- 若 `last_trigger.name == "low_alert"` 且 `current_price <= stop_loss_level` → **止损触发**，执行 Step 4F（优先于卖单检查）

否则检查止盈卖单：
- 若 `pending_sell_order_id` 状态 = FILLED → **卖出已成交**，完成一个循环，转入 WAITING_BUY 流程（Step 4C）
- 若状态 = PENDING/SUBMITTED → 挂单有效，**不重复下单**，更新后退出
- 若订单不存在或已取消 → 重新挂卖单（Step 4D）

**情况 C：current_phase = WAITING_BUY + 价格触及 high_alert（sell_level）**

触发条件：`last_trigger.name == "high_alert"` 且 `current_phase == "WAITING_BUY"` 且买单仍未成交（PENDING/SUBMITTED）

说明：价格未经过买入点直接上涨突破卖出目标，说明区间整体上移，原买入价已过低，需重新定位。

执行：Step 4E（ATR 重新分析 → 取消原订单 → 上移买入价重新挂单）

**情况 D：每日重置（daily_reset）**

触发条件：`last_trigger.name == "daily_reset"`

说明：每个交易日 0:00 ET 自动触发。无论当前 phase，均重算 ATR、更新区间、撤旧挂单、重新挂单，使策略始终基于最新价格结构运作。

执行：Step 4G（ATR 重算 → 按 phase 撤单并重新挂单）

**额外检查**：若实际持仓与 phase 不符（如持仓>0 但 phase=WAITING_BUY），以实际持仓为准修正 phase。

### Step 4 — 下单操作

#### Step 4A：买单成交 → 计算止损价 → 挂卖单

从 `get_recent_fills` 获取实际买入成交均价 `buy_fill_price`。

计算止损价：
```
stop_loss_level = round(buy_fill_price × (1 - stop_loss_pct), 2)
# 示例：buy_fill_price=$90.00，stop_loss_pct=0.05 → stop_loss_level=$85.50
```

挂止盈卖单：
```
cancel_symbol_orders(symbol=HOOD)   ← 清理残留挂单
place_order(
  symbol=HOOD, action=SELL,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=state.sell_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

更新 state：
- `current_phase` = "WAITING_SELL"
- `pending_sell_order_id` = 新订单 ID
- `pending_buy_order_id` = null
- `buy_fill_price` = 实际成交均价
- `stop_loss_level` = 计算所得止损价

#### Step 4B：无有效买单 → 重新挂买单

```
cancel_symbol_orders(symbol=HOOD)
place_order(
  symbol=HOOD, action=BUY,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=state.buy_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

更新 state：
- `pending_buy_order_id` = 新订单 ID

#### Step 4C：卖单成交 → 记录利润 + 挂新买单

计算本次循环利润：
```
cycle_profit = (sell_fill_price - buy_fill_price) × quantity
```

更新区间（基于最新 5 日 K 线动态调整，可选）：
- 获取 `get_stock_bars` period=day, limit=6
- 计算 5 日 ATR = 近 5 日 (High - Low) 均值
- new_buy_level = round(当前价 - ATR × 0.5, 2)
- new_sell_level = round(当前价 + ATR × 0.5, 2)
- 若 ATR 计算合理（buy > 当前价×0.9 且 sell < 当前价×1.15），则更新；否则保持原值

```
cancel_symbol_orders(symbol=HOOD)
place_order(
  symbol=HOOD, action=BUY,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=new_buy_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

更新 state：
- `current_phase` = "WAITING_BUY"
- `completed_cycles` += 1
- `total_realized_profit` += cycle_profit
- `buy_level` = new_buy_level
- `sell_level` = new_sell_level
- `pending_buy_order_id` = 新订单 ID
- `pending_sell_order_id` = null
- `cycle_history` 追加本次记录：`{buy_price, sell_price, profit, timestamp}`

#### Step 4F：止损触发 → 限价平仓

> 触发条件：WAITING_SELL 阶段，`last_trigger = "low_alert"`，`current_price <= stop_loss_level`

```
cancel_symbol_orders(symbol=HOOD)   ← 先撤止盈挂单
place_order(
  symbol=HOOD, action=SELL,
  quantity=state.quantity,          ← 全部持仓
  order_type=LMT,
  limit_price=round(current_price × 0.99, 2),   ← 略低于实时价，近乎保证成交
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

计算止损亏损：
```
stop_loss_pnl = (stop_fill_price - buy_fill_price) × quantity   ← 负值
```

更新 state：
- `current_phase` = "WAITING_BUY"
- `pending_sell_order_id` = 止损单 ID（等待确认成交）
- `stop_loss_level` = null
- `buy_fill_price` = null
- `total_realized_profit` += stop_loss_pnl（累计亏损）
- `cycle_history` 追加：`{type: "STOP_LOSS", buy_price, stop_price, pnl, timestamp}`

止损成交确认后（下次被唤醒时检查 recent_fills），重新按 ATR 计算新区间后挂买单（同 Step 4C 的区间更新逻辑）。

---

#### Step 4E：价格突破卖出目标但买单未成交 → 重新分析 ATR，上移买入价

> 触发自情况 C：WAITING_BUY 阶段价格先到达 sell_level，原区间已失效。

**1. 重新计算区间（基于最新 5 日 ATR）：**

```
get_stock_bars(symbol=HOOD, period=day, limit=6)
5日ATR = 近5根日线 (High - Low) 的均值
new_buy_level  = round(current_price - ATR × 0.5, 2)
new_sell_level = round(current_price + ATR × 0.5, 2)
```

校验规则（任一不满足则保持原区间并写告警日志）：
- `new_buy_level < current_price < new_sell_level`
- `new_sell_level - new_buy_level >= new_buy_level × 0.03`（利润空间至少 3%）
- `new_buy_level >= current_price × 0.85`（买入价不得偏离当前价超过 15%）

**2. 取消原订单 + 重新挂买单：**

```
cancel_symbol_orders(symbol=HOOD)
place_order(
  symbol=HOOD, action=BUY,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=new_buy_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

**3. 更新 state：**
- `buy_level` = new_buy_level
- `sell_level` = new_sell_level
- `pending_buy_order_id` = 新订单 ID
- `pending_sell_order_id` = null
- 在 `cycle_history` 追加一条记录（标记 type="RANGE_SHIFT"，记录旧区间和新区间）

---

#### Step 4D：无有效卖单 → 重新挂卖单

```
cancel_symbol_orders(symbol=HOOD)
place_order(
  symbol=HOOD, action=SELL,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=state.sell_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```

更新 state：
- `pending_sell_order_id` = 新订单 ID

---

#### Step 4G：每日重置 — 重算 ATR + 按 phase 重新挂单

> 触发条件：`last_trigger.name == "daily_reset"`
> 每个交易日 0:00 ET 触发一次，无论当前 phase 均执行。

**1. 获取最新 K 线，计算 ATR：**

```
get_stock_bars(symbol=HOOD, period=day, limit=16)
```

计算 14 日 ATR（标准真实波幅均值）：
```
TR_i = max(High_i - Low_i,
           abs(High_i - Close_{i-1}),
           abs(Low_i  - Close_{i-1}))
ATR14 = mean(TR_1 … TR_14)   ← 取最近 14 根日线
```

计算新区间：
```
new_buy_level  = round(current_price - ATR14 × 0.5, price_precision)
new_sell_level = round(current_price + ATR14 × 0.5, price_precision)
```

校验规则（任一不满足则保留原区间并写告警日志，跳过挂单步骤）：
- `new_buy_level < current_price < new_sell_level`
- `new_sell_level - new_buy_level >= new_buy_level × 0.03`（利润空间 ≥ 3%）
- `new_buy_level >= current_price × 0.85`（买入价不偏离当前价超过 15%）

**2. 撤销所有旧挂单：**

```
cancel_symbol_orders(symbol=HOOD)
```

**3. 按当前 phase 重新挂单：**

*若 `current_phase == "WAITING_BUY"`（空仓）：*
```
place_order(
  symbol=HOOD, action=BUY,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=new_buy_level,
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```
更新 state：
- `buy_level` = new_buy_level
- `sell_level` = new_sell_level
- `pending_buy_order_id` = 新订单 ID
- `low_alert` = new_buy_level（跌到此处检查买单）
- `high_alert` = new_sell_level（涨突破此处触发区间上移 Step 4E）

*若 `current_phase == "WAITING_SELL"`（持仓中）：*

不修改 `buy_fill_price` 和 `stop_loss_level`（止损基准不变）。
```
place_order(
  symbol=HOOD, action=SELL,
  quantity=state.quantity,
  order_type=LMT,
  limit_price=max(new_sell_level, buy_fill_price × 1.03),   ← 至少保 3% 利润
  time_in_force=GTC,
  outside_rth=true,
  trading_session_type=FULL
)
```
更新 state：
- `sell_level` = 实际挂单价格（取上方 max 的结果）
- `pending_sell_order_id` = 新订单 ID
- `high_alert` = sell_level（涨到止盈价触发检查）
- `low_alert` = stop_loss_level（不变，止损警报不因每日重置而移动）

**4. 在 `cycle_history` 追加记录：**
```json
{
  "type": "DAILY_RESET",
  "date": "YYYY-MM-DD",
  "atr14": <计算值>,
  "old_buy": <旧 buy_level>,
  "new_buy": new_buy_level,
  "old_sell": <旧 sell_level>,
  "new_sell": new_sell_level,
  "current_price": <当前价>
}
```

### Step 5 — 更新 state 文件

写回路径：`./state.json`

必须写回所有字段，包括：
- `current_phase`、`buy_level`、`sell_level`、`quantity`
- `pending_buy_order_id`、`pending_sell_order_id`
- `completed_cycles`、`total_realized_profit`、`cycle_history`
- `current_price`、`last_run`（当前 ISO 时间戳）、`last_trigger`
- `monitor_pid`
- `last_daily_reset_date`（从原 state 读取后原样写回，不得删除；由 price_monitor.py 自行维护）

警报更新规则：
- `WAITING_BUY`：
  - `low_alert` = buy_level（价格跌到此处 → 检查买单是否成交）
  - `high_alert` = sell_level（价格涨到此处且买单未成交 → 区间上移 Step 4E）
- `WAITING_SELL`：
  - `high_alert` = sell_level（价格涨到此处 → 检查止盈卖单是否成交）
  - `low_alert` = stop_loss_level（= buy_fill_price × 0.95，价格跌到此处 → 触发止损 Step 4F）

### Step 6 — 重启价格监控

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
  --symbol HOOD \
  --strategy-dir "${STRATEGY_DIR}" \
  > "${STRATEGY_DIR}/logs/monitor.log" 2>&1 &
NEW_PID=$!
```

将 `NEW_PID` 写回 `./state.json` 的 `monitor_pid` 字段。

### Step 7 — 写日志并退出

```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [HOOD] phase={current_phase}  price={current_price}  buy={buy_level}  sell={sell_level}  cycles={completed_cycles}  profit={total_realized_profit}" \
  >> "./logs/strategy.log"
```

---

## 风险控制

- **全程只用 LMT + GTC + outside_rth=true + trading_session_type=FULL**：覆盖盘前/盘中/盘后/夜盘全时段，Tiger 不支持 MKT/STP 在非正规时段
- **不重复挂单**：若挂单已存在且价格正确，跳过下单步骤
- **持仓保护**：若 SELL 挂单失败且有持仓，立即重试；重试 3 次失败则写日志告警
- **区间保护**：动态更新区间时，buy_level 不得高于当前价，sell_level 不得低于当前价
- **最小利润保护**：sell_level - buy_level 至少为 buy_level 的 3%，否则不更新区间
