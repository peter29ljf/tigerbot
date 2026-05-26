# Trade API Reference

## Table of Contents
1. [Contract Creation](#contracts)
2. [Order Creation Helpers](#order-helpers)
3. [Place Order](#place-order)
4. [Preview Order](#preview-order)
5. [Modify Order](#modify-order)
6. [Cancel Order](#cancel-order)
7. [Query Orders](#query-orders)
8. [Order Types & Enums](#enums)

---

## Contract Creation {#contracts}

Before placing any order, you need a Contract object:

```python
from tigeropen.trade.domain.contract import Contract
from tigeropen.common.consts import SecurityType, Currency, Market

# Stock contract
stock_contract = Contract(
    symbol='AAPL',
    sec_type=SecurityType.STK,
    currency=Currency.USD
)

# Option contract
option_contract = Contract(
    symbol='AAPL',
    sec_type=SecurityType.OPT,
    currency=Currency.USD,
    expiry='2024-01-19',       # expiration date
    strike=150.0,              # strike price
    put_call='CALL'            # 'CALL' or 'PUT'
)

# Future contract
future_contract = Contract(
    symbol='CL',
    sec_type=SecurityType.FUT,
    currency=Currency.USD,
    exchange='NYMEX',          # exchange code
    expiry='20240120',         # expiry date
    multiplier=1000            # contract multiplier
)
```

**SecurityType enum:**
- `SecurityType.STK` — Stock
- `SecurityType.OPT` — Option
- `SecurityType.FUT` — Future
- `SecurityType.CASH` — Forex

**Currency enum:**
- `Currency.USD`, `Currency.HKD`, `Currency.CNH`, `Currency.SGD`, `Currency.AUD`, `Currency.GBP`, `Currency.EUR`

---

## Order Creation Helpers {#order-helpers}

The SDK provides utility functions that simplify order creation:

```python
from tigeropen.common.util.order_utils import (
    market_order,
    limit_order,
    stop_order,
    stop_limit_order,
    trailing_stop_order
)

# Market order
order = market_order(
    account='6481265',
    contract=stock_contract,
    action='BUY',          # 'BUY' or 'SELL'
    quantity=100
)

# Limit order
order = limit_order(
    account='6481265',
    contract=stock_contract,
    action='BUY',
    quantity=100,
    limit_price=150.0
)

# Stop order
order = stop_order(
    account='6481265',
    contract=stock_contract,
    action='SELL',
    quantity=100,
    aux_price=145.0          # stop trigger price
)

# Stop-limit order
order = stop_limit_order(
    account='6481265',
    contract=stock_contract,
    action='SELL',
    quantity=100,
    limit_price=144.0,
    aux_price=145.0
)

# Trailing stop order
order = trailing_stop_order(
    account='6481265',
    contract=stock_contract,
    action='SELL',
    quantity=100,
    trailing_percent=5.0     # trail by 5%
)
```

**Common order attributes you can set after creation:**
```python
order.time_in_force = 'GTC'       # Good-Til-Canceled (default: DAY)
order.outside_rth = True          # Allow outside regular trading hours
order.order_legs = [...]          # For attached orders (profit target / stop loss)
```

---

## Place Order {#place-order}

```python
# WARNING: This executes a real trade in PROD environment!
trade_client.place_order(order)

# After placement, order.id is set
print(f"Order placed, ID: {order.id}")
```

**Full example — buy 100 shares of AAPL at limit $150:**
```python
from tigeropen.trade.trade_client import TradeClient
from tigeropen.trade.domain.contract import Contract
from tigeropen.common.util.order_utils import limit_order
from tigeropen.common.consts import SecurityType, Currency

trade_client = TradeClient(client_config)
contract = Contract(symbol='AAPL', sec_type=SecurityType.STK, currency=Currency.USD)
order = limit_order(account='6481265', contract=contract, action='BUY', quantity=100, limit_price=150.0)
trade_client.place_order(order)
print(f"Order ID: {order.id}")
```

---

## Preview Order {#preview-order}

Preview order to check margin requirements without actually placing it:

```python
preview = trade_client.preview_order(order)
# Returns dict with margin info, buying power impact, etc.
print(preview)
```

---

## Modify Order {#modify-order}

```python
trade_client.modify_order(
    order,                    # the Order object (must have order.id set)
    limit_price=155.0,        # new limit price (optional)
    quantity=200              # new quantity (optional)
)
```

---

## Cancel Order {#cancel-order}

```python
trade_client.cancel_order(id=order.id)
```

---

## Query Orders {#query-orders}

### get_orders — Get Order History

```python
orders = trade_client.get_orders(
    account=None,              # defaults to configured account
    sec_type=None,             # SecurityType filter
    market=Market.ALL,         # Market filter
    symbol=None,               # symbol filter
    start_time=None,           # start timestamp (ms)
    end_time=None,             # end timestamp (ms)
    limit=100,                 # max results
    is_brief=False,            # brief mode
    states=None,               # list of order states to filter
    sort_by=None,              # sort field
    seg_type=None              # segment type
)
```

Returns a list of `Order` objects. Each Order has:
- `id` — Order ID
- `order_type` — MKT, LMT, STP, STP_LMT, TRAIL
- `action` — BUY, SELL
- `quantity` — Ordered quantity
- `filled` — Filled quantity
- `avg_fill_price` — Average fill price
- `limit_price` — Limit price
- `aux_price` — Stop price
- `status` — Order status string
- `contract` — Contract object

### get_active_orders — Currently Active Orders

```python
active_orders = trade_client.get_orders(states=['Submitted', 'Initial', 'PendingSubmit'])
```

---

## Order Types & Enums {#enums}

**OrderType:**
- `MKT` — Market order (execute immediately at best price)
- `LMT` — Limit order (execute at specified price or better)
- `STP` — Stop order (trigger at stop price, then market order)
- `STP_LMT` — Stop-limit order (trigger at stop, then limit order)
- `TRAIL` — Trailing stop order

**Action:**
- `BUY` — Buy to open / Buy to cover
- `SELL` — Sell to close / Sell short

**TimeInForce:**
- `DAY` — Valid for current trading day only
- `GTC` — Good-Til-Canceled
- `OPG` — Pre-market auction order
- `IOC` — Immediate or Cancel
- `GTD` — Good-Til-Date

**Order States:**
- `Initial` — Order created, not yet submitted
- `PendingSubmit` — Pending submission
- `Submitted` — Submitted to exchange
- `Filled` — Fully filled
- `Cancelled` — Canceled
- `Inactive` — Inactive
- `PendingCancel` — Pending cancellation
