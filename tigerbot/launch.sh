#!/bin/bash
set -euo pipefail

SYMBOL="${1:?用法: ./launch.sh TSLA}"

DIR="$(cd "$(dirname "$0")" && pwd)"
STATE="$DIR/state-$SYMBOL.json"
LOG="$DIR/logs/$SYMBOL"
mkdir -p "$LOG"

echo "┌─────────────────────────────────────────┐"
echo "│  ${SYMBOL} 美股策略启动                  │"
echo "└─────────────────────────────────────────┘"

# ── 检测 Claude Code CLI ─────────────────────────────
CLAUDE_BIN=""
for candidate in \
  "$HOME/.local/bin/claude" \
  "/usr/local/bin/claude" \
  "/opt/homebrew/bin/claude"
do
  if [ -x "$candidate" ]; then
    CLAUDE_BIN="$candidate"
    break
  fi
done
if [ -z "$CLAUDE_BIN" ]; then
  CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
fi
if [ -z "$CLAUDE_BIN" ]; then
  echo "❌ Claude Code CLI 未安装"
  echo "   先安装: npm install -g @anthropic-ai/claude-code"
  exit 1
fi

# ── 检查 Python 依赖 ─────────────────────────────────
python3 -c "import tigeropen, pytz" 2>/dev/null || \
  pip3 install tigeropen pytz --break-system-packages -q
echo "✅ 依赖检查通过  claude=$($CLAUDE_BIN --version 2>/dev/null | head -1)"

# ── 停止同股票旧监控 ─────────────────────────────────
pkill -f "price_monitor.py.*--symbol.*$SYMBOL" 2>/dev/null && echo "⏹  旧监控已停止" || true
sleep 1

# ── 若无 state 文件，从 config.json 初始化 ───────────
if [ ! -f "$STATE" ]; then
  python3 - <<PY
import json
from pathlib import Path

symbol    = "$SYMBOL"
dir_      = Path("$DIR")
cfg_path  = dir_ / "config.json"
state_path = dir_ / f"state-{symbol}.json"

cfg      = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
defaults = cfg.get("_defaults", {})
sym_cfg  = {**defaults, **cfg.get("symbols", {}).get(symbol, {})}

initial_state = {
    "symbol":            symbol,
    "last_run":          None,
    "last_trigger":      None,
    "signal":            None,
    "current_price":     None,
    "market_open":       None,
    "indicators":        {},
    "placed_orders":     [],
    "fills_summary":     [],
    "alerts": {
        "low_alert":  sym_cfg.get("low_alert", 0),
        "high_alert": sym_cfg.get("high_alert", 999999),
    },
    "alert_labels": {
        "low_alert":  "buy_level",
        "high_alert": "breakout_watch",
    },
    "monitor_pid":        None,
    "position_status":    "FLAT",
    "position_qty":       0,
    "position_avg_price": None,
    "capital_limit_usd":  sym_cfg.get("capital_usd", 1000.0),
    "price_precision":    sym_cfg.get("price_precision", 2),
    "qty_precision":      sym_cfg.get("qty_precision", 0),
    "min_order_usd":      sym_cfg.get("min_order_usd", 10.0),
}
state_path.write_text(json.dumps(initial_state, indent=2, ensure_ascii=False))
print(f"✅ 初始化 state-{symbol}.json 完成")
PY
else
  echo "✅ 读取现有 $STATE"
fi

# ── 首次执行策略分析 ─────────────────────────────────
echo ""
echo "▶ 首次执行策略分析（Claude Code CLI）..."
"$CLAUDE_BIN" \
  --dangerously-skip-permissions \
  -p "执行当前目录 CLAUDE.md 中定义的完整交易策略循环。交易品种: $SYMBOL" \
  2>&1 | tee "$LOG/first_run.log"
echo "✅ 首次策略执行完毕"

# ── 显示状态摘要 ─────────────────────────────────────
MPID="$(python3 - <<PY
import json, pathlib
state = pathlib.Path("$STATE")
try:
    print(json.loads(state.read_text()).get("monitor_pid", "") or "")
except Exception:
    print("")
PY
)"

echo ""
echo "┌─────────────────────────────────────────┐"
echo "│  🚀 ${SYMBOL} 美股系统运行中              │"
echo "├─────────────────────────────────────────┤"
echo "│  监控 PID : ${MPID:-unknown}"
echo "│  当前警报 :"
python3 - <<PY
import json
from pathlib import Path
state = Path("$STATE")
data = json.loads(state.read_text()) if state.exists() else {}
for key, value in data.get("alerts", {}).items():
    print(f"│    {key}: {value}")
PY
echo "├─────────────────────────────────────────┤"
echo "│  注意：仅盘中（9:30-16:00 ET）轮询价格   │"
echo "├─────────────────────────────────────────┤"
echo "│  监控日志 : tail -f $LOG/monitor.log"
echo "│  策略日志 : tail -f $LOG/strategy.log"
echo "│  Claude日志: tail -f $LOG/claude_run.log"
echo "│  停止监控 : pkill -f 'price_monitor.py.*--symbol.*$SYMBOL'"
echo "└─────────────────────────────────────────┘"
