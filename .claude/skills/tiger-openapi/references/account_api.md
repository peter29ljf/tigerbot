# Account API Reference

## Table of Contents
1. [Get Account Info](#account-info)
2. [Get Assets](#assets)
3. [Get Positions](#positions)
4. [Get Transactions](#transactions)

All account methods are on `TradeClient`.

---

## Get Account Info {#account-info}

### get_account — Account Summary

```python
from tigeropen.trade.trade_client import TradeClient

trade_client = TradeClient(client_config)
account = trade_client.get_account()
```

**Account object fields:**
- `account` — Account number
- `net_liquidation` — Total net liquidation value
- `gross_position_value` — Total securities market value
- `available_funds` — Available funds for trading
- `buying_power` — Buying power
- `cash` — Cash balance
- `regt_equity` — Regulation T equity
- `regt_margin` — Regulation T margin
- `sma` — Special Memorandum Account (overnight risk value)
- `excess_liquidity` — Excess liquidity
- `day_trades_remaining` — Remaining day trades (PDT rule)
- `leverage` — Account leverage ratio

**Example:**
```python
account = trade_client.get_account()
print(f"Net Liquidation: ${account.net_liquidation:,.2f}")
print(f"Available Funds: ${account.available_funds:,.2f}")
print(f"Buying Power:    ${account.buying_power:,.2f}")
print(f"Cash:            ${account.cash:,.2f}")
```

---

## Get Assets {#assets}

### get_assets — Currency-based Asset Breakdown

```python
assets = trade_client.get_assets(
    account=None,           # defaults to configured account
    sub_accounts=None,      # sub-account filter
    segment=False,          # whether to segment by category
    market_value=False      # include market value details
)
```

Returns asset information grouped by currency. Each asset segment includes:
- `currency` — Currency code
- `cash` — Cash in this currency
- `cash_available_for_trade` — Cash available for trading
- `cash_available_for_withdrawal` — Cash available for withdrawal
- `gross_position_value` — Position value in this currency
- `net_liquidation` — Net liquidation in this currency
- `realized_pnl` — Realized P&L
- `unrealized_pnl` — Unrealized P&L

**Example:**
```python
assets = trade_client.get_assets()
for asset in assets:
    print(f"Currency: {asset.currency}")
    print(f"  Cash: {asset.cash}")
    print(f"  Position Value: {asset.gross_position_value}")
    print(f"  Unrealized P&L: {asset.unrealized_pnl}")
```

---

## Get Positions {#positions}

### get_positions — Current Holdings

```python
positions = trade_client.get_positions(
    account=None,            # defaults to configured account
    sec_type=None,           # SecurityType filter (STK, OPT, FUT)
    currency=None,           # Currency filter
    market=None,             # Market filter
    symbol=None,             # specific symbol
    sub_accounts=None,       # sub-account filter
    expiry=None,             # expiry filter (for options/futures)
    strike=None,             # strike filter (for options)
    put_call=None            # PUT/CALL filter (for options)
)
```

Returns a list of `Position` objects. Each Position has:
- `contract` — Contract object (symbol, sec_type, etc.)
- `quantity` — Number of shares/contracts held (negative = short)
- `average_cost` — Average cost per share
- `market_price` — Current market price
- `market_value` — Current market value
- `realized_pnl` — Realized P&L for this position
- `unrealized_pnl` — Unrealized P&L
- `latest_price` — Latest price

**Example — print all positions:**
```python
positions = trade_client.get_positions()
for pos in positions:
    symbol = pos.contract.symbol
    qty = pos.quantity
    avg_cost = pos.average_cost
    pnl = pos.unrealized_pnl
    print(f"{symbol}: {qty} shares @ ${avg_cost:.2f}, P&L: ${pnl:.2f}")
```

**Example — filter option positions:**
```python
from tigeropen.common.consts import SecurityType
opt_positions = trade_client.get_positions(sec_type=SecurityType.OPT)
```

---

## Get Transactions {#transactions}

### get_transactions — Trade History

```python
transactions = trade_client.get_transactions(
    account=None,
    symbol=None,
    sec_type=None,
    start_time=None,          # timestamp ms
    end_time=None,            # timestamp ms
    limit=100,
    sub_accounts=None,
    expiry=None
)
```

Returns a list of transaction records with:
- `id` — Transaction ID
- `order_id` — Associated order ID
- `contract` — Contract object
- `action` — BUY/SELL
- `filled_quantity` — Filled quantity
- `filled_price` — Fill price
- `commission` — Commission charged
- `realized_pnl` — Realized P&L from this transaction
- `transaction_time` — Execution timestamp
