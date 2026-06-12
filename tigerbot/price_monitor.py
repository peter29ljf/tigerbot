#!/usr/bin/env python3
"""
Tiger OpenAPI 美股价格监控器 — 多股票版
盘中每30秒轮询价格，触发时用 claude --dangerously-skip-permissions -p 唤醒 Claude Code CLI
用法: python3 price_monitor.py --symbol TSLA
"""
import argparse, json, os, shutil, subprocess, time, urllib.request, urllib.parse
from datetime import datetime, time as dtime
from pathlib import Path

import pytz

# ── CLI 参数 ──────────────────────────────────────────
parser = argparse.ArgumentParser(description="Tiger 美股价格监控器")
parser.add_argument("--symbol", required=True, help="股票代码，如 TSLA")
args = parser.parse_args()
SYMBOL = args.symbol

# ── 路径 ──────────────────────────────────────────────
STRATEGY_DIR = Path(__file__).parent
STATE_FILE   = STRATEGY_DIR / f"state-{SYMBOL}.json"
LOG_DIR      = STRATEGY_DIR / "logs" / SYMBOL
LOG_FILE     = LOG_DIR / "monitor.log"
POLL_SEC     = 30
ET_TZ        = pytz.timezone("America/New_York")

# ── 从 config.json 读取默认值 ─────────────────────────
def load_symbol_config(symbol: str) -> dict:
    try:
        cfg = json.loads((STRATEGY_DIR / "config.json").read_text())
        defaults = cfg.get("_defaults", {})
        return {**defaults, **cfg.get("symbols", {}).get(symbol, {})}
    except Exception:
        return {"price_precision": 2, "qty_precision": 0,
                "low_alert": 0, "high_alert": 999999}

SYMBOL_CONFIG   = load_symbol_config(SYMBOL)
PRICE_PRECISION = SYMBOL_CONFIG.get("price_precision", 2)
LOG_THRESHOLD   = 10 ** (-(PRICE_PRECISION - 1))
PRICE_FMT       = f"{{:.{PRICE_PRECISION}f}}"

DEFAULT = {
    "low_alert":  SYMBOL_CONFIG.get("low_alert", 0),
    "high_alert": SYMBOL_CONFIG.get("high_alert", 999999),
}
DEFAULT_LABELS = {"low_alert": "低点警报", "high_alert": "高点警报"}
DIRECTION      = {"low_alert": "below", "high_alert": "above"}

# ── 价格获取：Bitget 合约价优先，YF 按 session fallback ──
def get_price() -> float:
    """
    1. Bitget USDT 永续（SYMBOLUSDT 合约，无需认证，速度快）
    2. Bitget 现货（SYMBOLUSDT）
    3. Bitget 现货代币化美股（R{SYMBOL}USDT，如 GEV→RGEVUSDT）
    4. Yahoo Finance：根据当前 ET session 选正确价格字段
       pytz 自动处理夏令时（EDT/EST）
       marketState: REGULAR / PRE / PREPRE / POST / POSTPOST / CLOSED
    """
    # ── 1. Bitget 合约 ───────────────────────────────────
    try:
        bitget_sym = f"{SYMBOL.upper()}USDT"
        qs  = urllib.parse.urlencode({"category": "USDT-FUTURES", "symbol": bitget_sym})
        req = urllib.request.Request(
            f"https://api.bitget.com/api/v3/market/tickers?{qs}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        if str(data.get("code")) == "00000" and data.get("data"):
            return float(data["data"][0]["lastPrice"])
    except Exception:
        pass

    # ── 2 & 3. Bitget 现货（直接 + R 前缀代币化美股）────────
    try:
        req = urllib.request.Request(
            "https://api.bitget.com/api/v2/spot/market/tickers",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            spot_data = json.loads(resp.read())
        spot_map = {t["symbol"]: float(t["lastPr"]) for t in spot_data.get("data", [])}
        for candidate in (f"{SYMBOL.upper()}USDT", f"R{SYMBOL.upper()}USDT"):
            if candidate in spot_map:
                return spot_map[candidate]
    except Exception:
        pass

    # ── 4. Yahoo Finance fallback ────────────────────────
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}"
           f"?interval=1m&range=1d&includePrePost=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    meta  = data["chart"]["result"][0]["meta"]
    state = meta.get("marketState", "CLOSED").upper()

    if state == "REGULAR":
        return float(meta["regularMarketPrice"])
    elif state in ("PRE", "PREPRE"):
        return float(meta.get("preMarketPrice") or meta["regularMarketPrice"])
    elif state in ("POST", "POSTPOST"):
        return float(meta.get("postMarketPrice") or meta["regularMarketPrice"])
    else:
        # CLOSED / 夜盘 / 周末：regularMarketPrice = 今日正式收盘价
        # 不使用 previousClose（那是昨收，更旧）
        return float(meta["regularMarketPrice"])

# ── 市场时间检查 ──────────────────────────────────────
def is_market_open() -> bool:
    now_et = datetime.now(ET_TZ)
    if now_et.weekday() >= 5:  # 周六/周日
        return False
    t = now_et.time()
    return dtime(9, 30) <= t <= dtime(16, 0)

# ── 警报加载 ──────────────────────────────────────────
def load_alerts() -> dict:
    try:
        state  = json.loads(STATE_FILE.read_text())
        raw    = state.get("alerts", DEFAULT)
        labels = state.get("alert_labels", {})
        merged = {
            "low_alert":  raw.get("low_alert",  DEFAULT["low_alert"]),
            "high_alert": raw.get("high_alert", DEFAULT["high_alert"]),
        }
        return {
            key: {
                "price":     float(merged[key]),
                "direction": DIRECTION[key],
                "label":     labels.get(key, DEFAULT_LABELS[key]),
            }
            for key in DIRECTION
        }
    except Exception:
        return {k: {"price": DEFAULT[k], "direction": DIRECTION[k], "label": DEFAULT_LABELS[k]}
                for k in DIRECTION}

# ── 工具 ─────────────────────────────────────────────
def log(msg: str):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    open(LOG_FILE, "a").write(line + "\n")

def notify(title: str, msg: str):
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{msg}" with title "{title}" sound name "Glass"'],
            capture_output=True, timeout=5)
    except Exception:
        pass

def update_state_monitor_pid(pid: int):
    try:
        data = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        data["monitor_pid"] = pid
        STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as exc:
        log(f"⚠️  写入 monitor_pid 失败: {exc}")

def cleanup_duplicate_monitors():
    current_pid = os.getpid()
    update_state_monitor_pid(current_pid)
    try:
        proc = subprocess.run(
            ["pgrep", "-f", f"price_monitor.py.*--symbol.*{SYMBOL}"],
            capture_output=True, text=True, timeout=5)
        if proc.returncode not in (0, 1):
            return
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
            except ValueError:
                continue
            if pid == current_pid:
                continue
            try:
                os.kill(pid, 15)
                log(f"🧹 清理重复监控进程 PID={pid}")
            except ProcessLookupError:
                pass
            except Exception as exc:
                log(f"⚠️  清理重复监控 PID={pid} 失败: {exc}")
    except Exception as exc:
        log(f"⚠️  重复监控清理失败: {exc}")

# ── 查找 Claude Code CLI ──────────────────────────────
def get_claude_bin() -> str:
    candidates = [
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    path = shutil.which("claude")
    if path:
        return path
    raise FileNotFoundError("claude")

# ── 唤醒 Claude Code CLI ──────────────────────────────
def wake_claude(trigger_name: str, price_str: str, alert_label: str):
    log(f"⚡ 触发 [{trigger_name}] 价格={price_str}  唤醒 Claude Code CLI...")
    notify(f"{SYMBOL} 警报", f"{alert_label} @ {price_str}")

    try:
        s = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        s["last_trigger"] = {
            "name":  trigger_name,
            "price": price_str,
            "time":  datetime.now().isoformat(),
        }
        STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))
    except Exception as e:
        log(f"⚠️  写触发信息失败: {e}")

    prompt = f"执行当前目录 CLAUDE.md 中定义的完整交易策略循环。交易品种: {SYMBOL}"
    try:
        claude_bin = get_claude_bin()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [claude_bin, "--dangerously-skip-permissions", "-p", prompt],
            cwd=str(STRATEGY_DIR),
            stdout=open(LOG_DIR / "claude_run.log", "a"),
            stderr=subprocess.STDOUT,
        )
        log(f"🚀 Claude Code CLI 已启动 PID={proc.pid}")
        notify(f"{SYMBOL}", f"Claude CLI 运行中 PID={proc.pid}")
        try:
            proc.wait(timeout=600)
            log(f"✅ Claude Code CLI 完成 returncode={proc.returncode}")
        except subprocess.TimeoutExpired:
            log("⚠️  Claude Code CLI 超时(10min)")
    except FileNotFoundError:
        log("❌ 找不到 claude 命令，请先安装: npm install -g @anthropic-ai/claude-code")
        notify(f"{SYMBOL} 错误", "找不到 claude CLI")

# ── 主循环 ────────────────────────────────────────────
def main():
    cleanup_duplicate_monitors()
    log("=" * 55)
    log(f"🔍 {SYMBOL} 美股监控启动  轮询={POLL_SEC}s（仅盘中）  目录={STRATEGY_DIR}")
    notify(f"{SYMBOL} Monitor", f"已启动，盘中 {POLL_SEC}s 轮询")

    fired       = set()
    last_price  = None
    last_run_ts = None
    errors      = 0

    while True:
        # 非交易时间：休眠后直接继续，不轮询价格
        if not is_market_open():
            now_et = datetime.now(ET_TZ)
            log(f"🌙 市场未开盘（ET {now_et:%H:%M}），休眠 60s")
            time.sleep(60)
            continue

        try:
            price  = get_price()
            errors = 0
            alerts = load_alerts()

            if last_price is None or abs(price - last_price) >= LOG_THRESHOLD:
                alert_summary = {k: v["price"] for k, v in alerts.items()}
                log(f"📊 {PRICE_FMT.format(price)}  警报: {alert_summary}")
                last_price = price

            # 检测 Claude Code CLI 是否已完成（state 更新），解锁警报
            try:
                ts = json.loads(STATE_FILE.read_text()).get("last_run")
                if ts and ts != last_run_ts:
                    fired.clear()
                    log("🔓 Claude Code CLI 已完成，警报解锁")
                    last_run_ts = ts
            except Exception:
                pass

            for name, cfg in alerts.items():
                if name in fired:
                    continue
                hit = (
                    (cfg["direction"] == "below" and price <= cfg["price"]) or
                    (cfg["direction"] == "above" and price >= cfg["price"])
                )
                if hit:
                    fired.add(name)
                    wake_claude(name, PRICE_FMT.format(price), cfg["label"])
                    break

        except Exception as e:
            errors += 1
            log(f"⚠️  错误({errors}): {e}")
            if errors >= 5:
                notify(f"{SYMBOL} Monitor", "连续5次错误，请检查")
                errors = 0

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
