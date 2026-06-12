#!/usr/bin/env python3
"""
Tiger Brokers OpenAPI — MCP Server
====================================
在你的本机运行，通过 MCP 协议把 Tiger API 暴露给 Cowork/Claude Code 调用。

启动方式:
    python3 server.py --config /path/to/tiger_openapi_config.properties

MCP 工具列表:
    get_option_expirations — 期权到期日
    get_option_chain      — 期权链（含OI/IV/Greeks）
    get_oi_analysis       — 任意标的 OI 支撑压力分析
    get_account           — 账户总览
    get_positions         — 持仓查询
    get_assets            — 资产查询
    place_order           — 下单（需确认）
    cancel_order          — 撤单
    get_orders            — 订单查询
    get_market_status     — 市场状态
"""

import argparse
import json
import sys
import os
import datetime
from typing import Any

# ── MCP SDK ──────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    print("请先安装 MCP SDK: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── tigeropen ────────────────────────────────────────────────────────────────
try:
    from tigeropen.tiger_open_config import TigerOpenClientConfig
    from tigeropen.quote.quote_client import QuoteClient
    from tigeropen.trade.trade_client import TradeClient
    from tigeropen.common.consts import Language, Market, SecurityType, Currency
    from tigeropen.trade.domain.contract import Contract
    from tigeropen.common.util.order_utils import (
        market_order, limit_order, stop_order, stop_limit_order, trail_order
    )
except ImportError:
    print("请先安装 tigeropen: pip install tigeropen", file=sys.stderr)
    sys.exit(1)

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────

app = Server("tiger-openapi")
_quote_client: QuoteClient = None
_trade_client: TradeClient = None
_config_path: str = None


def _init_clients(config_path: str):
    global _quote_client, _trade_client
    cfg = TigerOpenClientConfig(props_path=config_path)
    cfg.language = Language.en_US

    # QuoteClient.__init__ 会调用 grab_quote_permission()
    # 若只有延时行情权限或设备未注册，该调用会抛异常但不影响数据获取
    # 直接 patch 掉，让客户端跳过权限预检
    original_grab = None
    try:
        from tigeropen.quote import quote_client as _qm
        original_grab = _qm.QuoteClient.grab_quote_permission
        _qm.QuoteClient.grab_quote_permission = lambda self: []   # 返回空权限列表
        _quote_client = QuoteClient(cfg)
        _qm.QuoteClient.grab_quote_permission = original_grab     # 还原
    except Exception as e:
        if original_grab:
            try:
                from tigeropen.quote import quote_client as _qm
                _qm.QuoteClient.grab_quote_permission = original_grab
            except Exception:
                pass
        print(f"⚠️  QuoteClient 初始化警告: {e}", file=sys.stderr)
        _quote_client = QuoteClient(cfg)

    _trade_client = TradeClient(cfg)


def _df_to_dict(df) -> list[dict]:
    """DataFrame 或 list → JSON 可序列化的 list[dict]"""
    if df is None:
        return []
    # tigeropen 新版某些方法返回 list 而非 DataFrame
    if isinstance(df, list):
        result = []
        for item in df:
            if hasattr(item, '__dict__'):
                result.append({k: v for k, v in vars(item).items() if not k.startswith('_')})
            elif isinstance(item, dict):
                result.append(item)
            else:
                result.append(str(item))
        return result
    if hasattr(df, 'empty') and df.empty:
        return []
    try:
        return json.loads(df.to_json(orient="records", date_format="iso"))
    except Exception:
        return df.to_dict(orient="records")


def _ok(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]


def _err(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))]


def _get_spot_price(symbol: str) -> tuple[float, str]:
    """获取股票现价，返回 (price, source)。
    优先级：
      1. Bitget USDT 永续合约（SYMBOLUSDT）
      2. Bitget 现货（SYMBOLUSDT）
      3. Bitget 现货代币化美股（R{SYMBOL}USDT，如 GEV→RGEVUSDT）
      4. Yahoo Finance（按当前 session 选价）
    pytz 自动处理夏令时（EDT/EST）。
    """
    import urllib.request, urllib.parse, pytz
    from datetime import datetime as _dt

    # ── 1. Bitget USDT 永续合约（无需认证，速度最快）──────────
    try:
        bitget_symbol = f"{symbol.upper()}USDT"
        qs = urllib.parse.urlencode({"category": "USDT-FUTURES", "symbol": bitget_symbol})
        req = urllib.request.Request(
            f"https://api.bitget.com/api/v3/market/tickers?{qs}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        if str(data.get("code")) == "00000" and data.get("data"):
            return float(data["data"][0]["lastPrice"]), "bitget_futures"
    except Exception:
        pass

    # ── 2 & 3. Bitget 现货（直接 + R 前缀代币化美股）──────────
    try:
        req = urllib.request.Request(
            "https://api.bitget.com/api/v2/spot/market/tickers",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            spot_data = json.loads(resp.read())
        spot_tickers = {t["symbol"]: t for t in spot_data.get("data", [])}

        # 先试 SYMBOLUSDT，再试 R{SYMBOL}USDT
        for candidate in (f"{symbol.upper()}USDT", f"R{symbol.upper()}USDT"):
            if candidate in spot_tickers:
                pr = float(spot_tickers[candidate]["lastPr"])
                tag = "bitget_spot" if not candidate.startswith("R") else "bitget_spot_tokenized"
                return pr, f"{tag} ({candidate})"
    except Exception:
        pass

    # ── 4. Yahoo Finance fallback：按 session 选合适的价格字段 ─
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1m&range=1d&includePrePost=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    meta = data["chart"]["result"][0]["meta"]
    # marketState: PRE | PREPRE | REGULAR | POST | POSTPOST | CLOSED
    state = meta.get("marketState", "CLOSED").upper()

    if state == "REGULAR":
        price = meta["regularMarketPrice"]
        src   = "yf_regular"
    elif state in ("PRE", "PREPRE"):
        # 盘前：优先盘前价，fallback 今日最近收盘
        price = meta.get("preMarketPrice") or meta["regularMarketPrice"]
        src   = "yf_premarket"
    elif state in ("POST", "POSTPOST"):
        # 盘后（16:00–20:00 ET）：优先盘后价，fallback 今日收盘
        price = meta.get("postMarketPrice") or meta["regularMarketPrice"]
        src   = "yf_afterhours"
    else:
        # CLOSED / 夜盘 / 周末：regularMarketPrice = 今日正式收盘价，
        # 比 previousClose（昨收）更新，不使用 previousClose
        price = meta["regularMarketPrice"]
        src   = "yf_closed"

    # 附加调试信息（ET 时间，含夏令时）
    et_now = _dt.now(pytz.timezone("America/New_York"))
    et_str = et_now.strftime("%H:%M %Z")  # 显示 EDT 或 EST

    return float(price), f"{src} (ET {et_str}, state={state})"


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 定义
# ═══════════════════════════════════════════════════════════════════════════

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_option_expirations",
            description="获取标的股票的期权到期日列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 NVDA"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_option_chain",
            description="获取期权链完整数据（行权价/OI/IV/Delta/Gamma/Theta/Vega/买卖价）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码"},
                    "expiry": {"type": "string", "description": "到期日 YYYY-MM-DD"},
                    "right": {"type": "string", "enum": ["ALL","CALL","PUT"], "default": "ALL"}
                },
                "required": ["symbol", "expiry"]
            }
        ),
        types.Tool(
            name="get_oi_analysis",
            description="对任意股票进行期权OI分析：支撑位、压力位、Max Pain、PCR、走势概率",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 NVDA"},
                    "num_expiries": {"type": "integer", "default": 3,
                                     "description": "分析最近N个到期日（1-6）"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_market_status",
            description="查询市场交易状态（美股/港股/A股）",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": ["ALL","US","HK","CN"], "default": "US"}
                }
            }
        ),
        types.Tool(
            name="get_account",
            description="查询账户总览：净值、可用资金、购买力、保证金",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_positions",
            description="查询当前所有持仓（含未实现盈亏）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "过滤特定股票，不填则返回全部"}
                }
            }
        ),
        types.Tool(
            name="get_assets",
            description="查询账户资产（按币种分类）",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_orders",
            description="查询订单历史",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "过滤特定股票"},
                    "limit": {"type": "integer", "default": 20}
                }
            }
        ),
        types.Tool(
            name="place_order",
            description=(
                "下单。支持订单类型：MKT(市价)、LMT(限价)、STP(止损)、STP_LMT(止损限价)、TRAIL(跟踪止损)。"
                "注意：这是真实交易，请谨慎使用"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "action": {"type": "string", "enum": ["BUY", "SELL"]},
                    "quantity": {"type": "integer"},
                    "order_type": {
                        "type": "string",
                        "enum": ["MKT", "LMT", "STP", "STP_LMT", "TRAIL"],
                        "default": "LMT"
                    },
                    "limit_price": {"type": "number", "description": "限价（LMT/STP_LMT 必填）"},
                    "aux_price": {
                        "type": "number",
                        "description": "辅助价格：STP/STP_LMT 的止损触发价；TRAIL 可选的跟踪金额（与 trailing_percent 二选一）"
                    },
                    "trailing_percent": {
                        "type": "number",
                        "description": "TRAIL 跟踪止损百分比（如 5 表示 5%），与 aux_price 二选一"
                    },
                    "time_in_force": {
                        "type": "string",
                        "enum": ["DAY", "GTC"],
                        "default": "DAY",
                        "description": "订单有效期：DAY=当日有效，GTC=撤销前有效"
                    },
                    "outside_rth": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否允许盘前/盘后交易（outside regular trading hours）。True = 允许盘前+盘后，配合 trading_session_type 可进一步控制夜盘"
                    },
                    "trading_session_type": {
                        "type": "string",
                        "enum": ["RTH", "PRE_RTH_POST", "OVERNIGHT", "FULL"],
                        "description": (
                            "交易时段类型（outside_rth=True 时生效）："
                            "RTH=仅正规时段(9:30-16:00 ET)；"
                            "PRE_RTH_POST=盘前+正规+盘后(4:00-20:00 ET)；"
                            "OVERNIGHT=仅夜盘(20:00-4:00 ET)；"
                            "FULL=全时段24小时含夜盘"
                        )
                    }
                },
                "required": ["symbol", "action", "quantity", "order_type"]
            }
        ),
        types.Tool(
            name="cancel_order",
            description="撤销订单",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单ID"}
                },
                "required": ["order_id"]
            }
        ),
        types.Tool(
            name="get_stock_quote",
            description="获取股票实时报价（最新价、买卖价、涨跌幅）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 TSLA"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_stock_bars",
            description="获取股票K线数据（OHLCV）。period: day=日线, week=周线, hour/1hour=1小时, 4hour=4小时",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 TSLA"},
                    "period": {
                        "type": "string",
                        "default": "day",
                        "description": "K线周期: day/week/hour/1hour/4hour"
                    },
                    "limit": {"type": "integer", "default": 100, "description": "返回根数"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_recent_fills",
            description="获取最近已成交订单（用于检测止盈/止损是否已触发出场）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "过滤特定股票，不填则返回全部"},
                    "limit": {"type": "integer", "default": 20}
                }
            }
        ),
        types.Tool(
            name="cancel_symbol_orders",
            description="撤销某只股票的全部未成交挂单",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 TSLA"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="close_position",
            description="市价平掉某只股票的全部持仓（全仓卖出）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 TSLA"}
                },
                "required": ["symbol"]
            }
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 实现
# ═══════════════════════════════════════════════════════════════════════════

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "get_option_expirations":
            df = _quote_client.get_option_expirations(symbols=[arguments["symbol"]])
            return _ok(_df_to_dict(df))

        elif name == "get_option_chain":
            df = _quote_client.get_option_chain(
                symbol=arguments["symbol"],
                expiry=arguments["expiry"]
            )
            if df is None or df.empty:
                return _ok([])
            right_filter = arguments.get("right", "ALL").upper()
            if right_filter != "ALL":
                df = df[df["right"].str.upper() == right_filter]
            cols = [c for c in ["strike","right","expiry","bid","ask","open_interest",
                                  "implied_volatility","delta","gamma","theta","vega"] if c in df.columns]
            return _ok(_df_to_dict(df[cols]))

        elif name == "get_oi_analysis":
            return _ok(await _oi_analysis(arguments["symbol"],
                                          arguments.get("num_expiries", 3)))

        elif name == "get_market_status":
            market_map = {"ALL": Market.ALL, "US": Market.US, "HK": Market.HK, "CN": Market.CN}
            market = market_map.get(arguments.get("market", "US"), Market.US)
            df = _quote_client.get_market_status(market=market)
            return _ok(_df_to_dict(df))

        elif name == "get_account":
            # tigeropen 不同版本方法名不同，逐个尝试
            acct = None
            for method in ['get_account', 'get_prime_assets', 'get_managed_accounts']:
                if hasattr(_trade_client, method):
                    try:
                        result = getattr(_trade_client, method)()
                        if isinstance(result, list) and result:
                            acct = result[0]
                        elif result:
                            acct = result
                        break
                    except Exception:
                        continue
            if acct is None:
                return _err("无法获取账户信息，请检查账户权限")
            fields = ['account','net_liquidation','available_funds','buying_power',
                      'cash','gross_position_value','equity_with_loan','buying_power']
            info = {}
            for f in fields:
                val = getattr(acct, f, None)
                if val is not None:
                    info[f] = val
            return _ok(info)

        elif name == "get_positions":
            symbol = arguments.get("symbol")
            positions = _trade_client.get_positions(symbol=symbol)
            result = []
            for p in positions:
                result.append({
                    "symbol": p.contract.symbol,
                    "sec_type": str(p.contract.sec_type),
                    "quantity": p.quantity,
                    "average_cost": p.average_cost,
                    "market_price": getattr(p, "market_price", None),
                    "market_value": getattr(p, "market_value", None),
                    "unrealized_pnl": getattr(p, "unrealized_pnl", None),
                    "realized_pnl": getattr(p, "realized_pnl", None),
                })
            return _ok(result)

        elif name == "get_assets":
            assets = _trade_client.get_assets()
            result = []
            for a in (assets if isinstance(assets, list) else [assets]):
                result.append({
                    "currency": str(getattr(a, "currency", "")),
                    "cash": getattr(a, "cash", None),
                    "net_liquidation": getattr(a, "net_liquidation", None),
                    "gross_position_value": getattr(a, "gross_position_value", None),
                    "unrealized_pnl": getattr(a, "unrealized_pnl", None),
                    "realized_pnl": getattr(a, "realized_pnl", None),
                })
            return _ok(result)

        elif name == "get_orders":
            orders = _trade_client.get_orders(
                symbol=arguments.get("symbol"),
                limit=arguments.get("limit", 20)
            )
            result = []
            for o in orders:
                result.append({
                    "id": o.id,
                    "symbol": o.contract.symbol if o.contract else None,
                    "action": str(o.action),
                    "order_type": str(o.order_type),
                    "quantity": o.quantity,
                    "filled": getattr(o, "filled", None),
                    "limit_price": getattr(o, "limit_price", None),
                    "avg_fill_price": getattr(o, "avg_fill_price", None),
                    "status": str(o.status),
                })
            return _ok(result)

        elif name == "place_order":
            contract = Contract(
                symbol=arguments["symbol"],
                sec_type=SecurityType.STK,
                currency=Currency.USD
            )
            # 兼容不同版本 tigeropen：TradeClient 可能只有 get_managed_accounts
            acct_obj = None
            for method in ['get_account', 'get_prime_assets', 'get_managed_accounts']:
                if hasattr(_trade_client, method):
                    try:
                        result = getattr(_trade_client, method)()
                        if isinstance(result, list) and result:
                            acct_obj = result[0]
                        elif result:
                            acct_obj = result
                        break
                    except Exception:
                        continue
            if acct_obj is None:
                return _err("无法获取账户信息，请检查账户权限")
            acct = getattr(acct_obj, 'account', None) or str(acct_obj)
            order_type = arguments["order_type"]
            action = arguments["action"]
            quantity = arguments["quantity"]
            tif = arguments.get("time_in_force", "DAY")
            outside_rth = arguments.get("outside_rth", False)
            session_type_str = arguments.get("trading_session_type")

            # 解析 trading_session_type 枚举
            # 注意：工厂函数（limit_order 等）不接受 outside_rth / trading_session_type，
            # 必须在创建 Order 后手动赋值到对象属性上。
            trading_session_type = None
            if session_type_str:
                try:
                    from tigeropen.common.consts import TradingSessionType
                    trading_session_type = TradingSessionType[session_type_str]
                except (KeyError, ImportError):
                    trading_session_type = session_type_str  # fallback: 直接传字符串

            # 工厂函数只接受标准参数，outside_rth / trading_session_type 不在其签名内
            common = dict(account=acct, contract=contract, action=action,
                          quantity=quantity, time_in_force=tif)

            if order_type == "MKT":
                order = market_order(**common)
            elif order_type == "LMT":
                if arguments.get("limit_price") is None:
                    return _err("LMT 订单必须提供 limit_price")
                order = limit_order(limit_price=arguments["limit_price"], **common)
            elif order_type == "STP":
                if arguments.get("aux_price") is None:
                    return _err("STP 订单必须提供 aux_price（止损触发价）")
                order = stop_order(aux_price=arguments["aux_price"], **common)
            elif order_type == "STP_LMT":
                if arguments.get("limit_price") is None or arguments.get("aux_price") is None:
                    return _err("STP_LMT 订单必须提供 limit_price 与 aux_price")
                order = stop_limit_order(
                    limit_price=arguments["limit_price"],
                    aux_price=arguments["aux_price"],
                    **common
                )
            elif order_type == "TRAIL":
                trailing_percent = arguments.get("trailing_percent")
                aux_price = arguments.get("aux_price")
                if trailing_percent is None and aux_price is None:
                    return _err("TRAIL 订单必须提供 trailing_percent 或 aux_price")
                order = trail_order(
                    trailing_percent=trailing_percent,
                    aux_price=aux_price,
                    **common
                )
            else:
                return _err(f"不支持的订单类型: {order_type}")

            # 工厂函数建完 Order 后，再手动赋值扩展属性（工厂函数签名不含这两个）
            if outside_rth:
                order.outside_rth = True
            if trading_session_type is not None:
                order.trading_session_type = trading_session_type

            _trade_client.place_order(order)
            return _ok({
                "order_id": order.id,
                "status": "submitted",
                "symbol": arguments["symbol"],
                "action": action,
                "quantity": quantity,
                "order_type": order_type,
                "time_in_force": tif,
                "outside_rth": outside_rth,
                "trading_session_type": session_type_str or "RTH(default)",
            })

        elif name == "cancel_order":
            _trade_client.cancel_order(id=arguments["order_id"])
            return _ok({"cancelled": arguments["order_id"]})

        elif name == "get_stock_quote":
            symbol = arguments["symbol"]
            price, source = _get_spot_price(symbol)
            return _ok({"symbol": symbol, "price": price, "source": source})

        elif name == "get_stock_bars":
            from tigeropen.common.consts import BarPeriod
            period_map = {
                "day":   BarPeriod.DAY,
                "week":  BarPeriod.WEEK,
                "hour":  BarPeriod.ONE_HOUR,
                "1hour": BarPeriod.ONE_HOUR,
                "4hour": BarPeriod.FOUR_HOURS,
            }
            period = period_map.get(arguments.get("period", "day"), BarPeriod.DAY)
            bars = _quote_client.get_bars(
                symbols=[arguments["symbol"]],
                period=period,
                limit=arguments.get("limit", 100)
            )
            return _ok(_df_to_dict(bars))

        elif name == "get_recent_fills":
            orders = _trade_client.get_orders(
                symbol=arguments.get("symbol"),
                limit=arguments.get("limit", 20)
            )
            filled = [o for o in orders
                      if str(o.status).upper() in ("FILLED", "PARTIALLY_FILLED")]
            result = [{
                "id": o.id,
                "symbol": o.contract.symbol if o.contract else None,
                "action": str(o.action),
                "quantity": o.quantity,
                "filled": getattr(o, "filled", None),
                "avg_fill_price": getattr(o, "avg_fill_price", None),
                "status": str(o.status),
            } for o in filled]
            return _ok(result)

        elif name == "cancel_symbol_orders":
            symbol = arguments["symbol"]
            orders = _trade_client.get_orders(symbol=symbol, limit=50)
            pending_statuses = {"PENDING", "SUBMITTED", "NEW", "PARTIALLY_FILLED",
                                "PENDING_SUBMIT", "PENDING_CANCEL"}
            pending = [o for o in orders
                       if str(o.status).upper() in pending_statuses]
            cancelled, errors = [], []
            for o in pending:
                try:
                    _trade_client.cancel_order(id=o.id)
                    cancelled.append(o.id)
                except Exception as e:
                    errors.append({"id": o.id, "error": str(e)})
            return _ok({"cancelled": cancelled, "errors": errors,
                        "total_cancelled": len(cancelled)})

        elif name == "close_position":
            symbol = arguments["symbol"]
            positions = _trade_client.get_positions(symbol=symbol)
            if not positions:
                return _ok({"message": "无持仓", "symbol": symbol})
            pos = positions[0]
            qty = abs(int(pos.quantity))
            if qty == 0:
                return _ok({"message": "持仓数量为0", "symbol": symbol})
            acct_obj = None
            for method in ['get_account', 'get_prime_assets', 'get_managed_accounts']:
                if hasattr(_trade_client, method):
                    try:
                        result = getattr(_trade_client, method)()
                        acct_obj = result[0] if isinstance(result, list) and result else result
                        if acct_obj:
                            break
                    except Exception:
                        continue
            if acct_obj is None:
                return _err("无法获取账户信息")
            acct = getattr(acct_obj, 'account', None) or str(acct_obj)
            contract = Contract(symbol=symbol, sec_type=SecurityType.STK, currency=Currency.USD)
            order = market_order(account=acct, contract=contract,
                                 action="SELL", quantity=qty, time_in_force="DAY")
            _trade_client.place_order(order)
            return _ok({"order_id": order.id, "action": "SELL", "quantity": qty,
                        "order_type": "MKT", "symbol": symbol, "status": "submitted"})

        else:
            return _err(f"未知工具: {name}")

    except Exception as e:
        return _err(f"{type(e).__name__}: {str(e)}")


async def _oi_analysis(symbol: str, num_expiries: int = 3) -> dict:
    """完整 OI 分析：支撑位、压力位、Max Pain、PCR、走势概率"""
    # 现价（优先 Bitget 合约价，fallback Yahoo Finance）
    spot, _src = _get_spot_price(symbol)

    # 到期日
    exp_df = _quote_client.get_option_expirations(symbols=[symbol])
    today = datetime.date.today()
    expiries = sorted([
        e for e in exp_df["expiry"].tolist()
        if datetime.date.fromisoformat(str(e)[:10]) >= today
    ])[:num_expiries]

    chains = {}
    for exp in expiries:
        df = _quote_client.get_option_chain(symbol=symbol, expiry=str(exp)[:10])
        if df is not None and not df.empty:
            chains[str(exp)[:10]] = df

    if not chains:
        return {"error": "无法获取期权链数据"}

    all_calls, all_puts = [], []
    per_expiry = {}

    for expiry, df in chains.items():
        calls = df[df["right"].str.upper() == "CALL"].groupby("strike")["open_interest"].sum().reset_index()
        puts  = df[df["right"].str.upper() == "PUT"].groupby("strike")["open_interest"].sum().reset_index()
        all_calls.append(calls.assign(expiry=expiry))
        all_puts.append(puts.assign(expiry=expiry))

        # Max Pain
        strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        pain = []
        for k in strikes:
            cp = sum(max(0, k - s) * oi for s, oi in zip(calls["strike"], calls["open_interest"]))
            pp = sum(max(0, s - k) * oi for s, oi in zip(puts["strike"], puts["open_interest"]))
            pain.append({"strike": k, "total_pain": cp + pp})
        pain_df = pd.DataFrame(pain)
        max_pain = float(pain_df.loc[pain_df["total_pain"].idxmin(), "strike"]) if not pain_df.empty else None

        per_expiry[expiry] = {
            "total_call_oi": int(calls["open_interest"].sum()),
            "total_put_oi": int(puts["open_interest"].sum()),
            "max_pain": max_pain,
            "top_call_strikes": calls.nlargest(5, "open_interest")[["strike","open_interest"]].to_dict("records"),
            "top_put_strikes": puts.nlargest(5, "open_interest")[["strike","open_interest"]].to_dict("records"),
        }

    agg_calls = pd.concat(all_calls).groupby("strike")["open_interest"].sum().reset_index()
    agg_puts  = pd.concat(all_puts).groupby("strike")["open_interest"].sum().reset_index()
    total_call_oi = int(agg_calls["open_interest"].sum())
    total_put_oi  = int(agg_puts["open_interest"].sum())
    pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None

    resistance = agg_calls[agg_calls["strike"] > spot].nlargest(5, "open_interest")
    support    = agg_puts[agg_puts["strike"] < spot].nlargest(5, "open_interest")

    all_oi = pd.concat([
        agg_calls.rename(columns={"open_interest": "oi"}),
        agg_puts.rename(columns={"open_interest": "oi"})
    ])
    oi_gravity = float(np.average(all_oi["strike"], weights=all_oi["oi"]))

    if pcr is not None:
        bull_prob = 65 if pcr < 0.7 else 58 if pcr < 0.9 else 50 if pcr < 1.1 else 42 if pcr < 1.3 else 35
    else:
        bull_prob = 50

    sentiment = "偏空 Bearish" if pcr and pcr > 1.1 else "偏多 Bullish" if pcr and pcr < 0.9 else "中性 Neutral"

    return {
        "symbol": symbol,
        "spot_price": spot,
        "analysis_time": datetime.datetime.now().isoformat(),
        "sentiment": sentiment,
        "pcr": pcr,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "oi_gravity_max_pain_zone": round(oi_gravity, 2),
        "bull_probability_pct": bull_prob,
        "bear_probability_pct": 100 - bull_prob,
        "resistance_levels": resistance[["strike", "open_interest"]].to_dict("records"),
        "support_levels": support[["strike", "open_interest"]].to_dict("records"),
        "per_expiry": per_expiry,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Tiger OpenAPI MCP Server")
    parser.add_argument("--config", default="tiger_openapi_config.properties",
                        help="tiger_openapi_config.properties 路径")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    if not os.path.exists(config_path):
        print(f"❌ 找不到配置文件: {config_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🐯 Tiger OpenAPI MCP Server 启动中...", file=sys.stderr)
    print(f"   配置文件: {config_path}", file=sys.stderr)
    _init_clients(config_path)
    print(f"✅ Tiger API 客户端初始化成功，共 {len(await list_tools())} 个工具", file=sys.stderr)
    print(f"   等待 MCP 连接...", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
