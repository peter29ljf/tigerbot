# Quote API Reference

## Table of Contents
1. [Stock Quotes](#stock-quotes)
2. [K-Line / Bars Data](#bars)
3. [Tick Data](#ticks)
4. [Market Status](#market-status)
5. [Option Quotes](#option-quotes)
6. [Option Chain](#option-chain)
7. [Future Quotes](#future-quotes)
8. [Symbol Search](#symbol-search)

All QuoteClient methods return **pandas DataFrames**.

---

## Stock Quotes {#stock-quotes}

### get_stock_briefs — Real-time Stock Snapshots

```python
quote_client.get_stock_briefs(
    symbols: List[str],              # e.g. ['AAPL', 'TSLA'] — max 50 per request
    include_hour_trading: bool = False,  # include pre/post market data
    lang: str = None                 # language override
) -> DataFrame
```

Returns: open, high, low, close, pre_close, latest_price, latest_time, volume, amount, etc.

**Example:**
```python
from tigeropen.quote.quote_client import QuoteClient

quote_client = QuoteClient(client_config)
df = quote_client.get_stock_briefs(['AAPL', 'GOOG', 'TSLA'])
print(df[['symbol', 'latest_price', 'volume', 'change', 'percent']])
```

---

## K-Line / Bars Data {#bars}

### get_bars — Historical OHLC Candlestick Data

```python
quote_client.get_bars(
    symbols: List[str],              # stock symbols
    period: BarPeriod = BarPeriod.DAY,  # candle period
    begin_time: int = -1,            # start timestamp (ms), -1 for default
    end_time: int = -1,              # end timestamp (ms), -1 for now
    right: QuoteRight = QuoteRight.BR,  # adjustment type
    limit: int = 251,                # max bars to return
    lang: str = None,
    page_token: str = None,          # for pagination
    trade_session: str = None        # trading session filter
) -> DataFrame
```

**BarPeriod enum values:**
```python
from tigeropen.common.consts import BarPeriod

BarPeriod.ONE_MINUTE      # 1min
BarPeriod.THREE_MINUTES   # 3min
BarPeriod.FIVE_MINUTES    # 5min
BarPeriod.TEN_MINUTES     # 10min
BarPeriod.FIFTEEN_MINUTES # 15min
BarPeriod.HALF_HOUR       # 30min
BarPeriod.ONE_HOUR        # 60min
BarPeriod.TWO_HOURS       # 2h
BarPeriod.FOUR_HOURS      # 4h
BarPeriod.DAY             # daily
BarPeriod.WEEK            # weekly
BarPeriod.MONTH           # monthly
BarPeriod.YEAR            # yearly
```

**QuoteRight enum values:**
```python
from tigeropen.common.consts import QuoteRight

QuoteRight.BR   # Before rights (backward adjusted) — default
QuoteRight.NR   # No rights (unadjusted)
```

**Example:**
```python
import time
from tigeropen.common.consts import BarPeriod

# Get daily bars for AAPL, last 60 days
end = int(time.time() * 1000)
begin = end - 60 * 24 * 3600 * 1000
df = quote_client.get_bars(['AAPL'], period=BarPeriod.DAY, begin_time=begin, end_time=end, limit=60)
print(df[['symbol', 'time', 'open', 'high', 'low', 'close', 'volume']])
```

---

## Tick Data {#ticks}

### get_trade_ticks — Tick-by-tick Trade Data

```python
quote_client.get_trade_ticks(
    symbols: List[str],
    begin_index: int = None,
    end_index: int = None,
    limit: int = None,
    lang: str = None
) -> DataFrame
```

Returns: time, price, volume, direction for each tick.

---

## Market Status {#market-status}

### get_market_status — Trading Session Status

```python
from tigeropen.common.consts import Market

quote_client.get_market_status(
    market: Market = Market.ALL,  # Market.US, Market.HK, Market.CN, Market.ALL
    lang: str = None
) -> DataFrame
```

Returns: market, status (Pre-Market Trading, Trading, Post-Market Trading, Closed), open_time.

---

## Option Quotes {#option-quotes}

### get_option_briefs — Option Contract Snapshots

```python
quote_client.get_option_briefs(
    identifiers: List[str]   # option identifiers e.g. ['AAPL  230120C00150000']
) -> DataFrame
```

### get_option_expirations — Available Expiration Dates

```python
quote_client.get_option_expirations(
    symbols: List[str]   # underlying symbols e.g. ['AAPL']
) -> DataFrame
```

### get_option_chain — Full Option Chain

```python
quote_client.get_option_chain(
    symbol: str,                    # underlying symbol
    expiry: str,                    # expiration date 'YYYY-MM-DD'
    option_filter: OptionFilter = None  # optional filter
) -> DataFrame
```

**OptionFilter:**
```python
from tigeropen.quote.domain.filter import OptionFilter

f = OptionFilter()
f.implied_volatility_min = 0.1
f.implied_volatility_max = 1.0
f.open_interest_min = 100
f.in_the_money = True  # only ITM options
```

Returns: identifier, strike, right (PUT/CALL), expiry, bid, ask, volume, open_interest, implied_volatility, delta, gamma, theta, vega, rho.

---

## Future Quotes {#future-quotes}

### get_future_bars — Futures OHLC Data

```python
quote_client.get_future_bars(
    identifiers: List[str],          # future contract identifiers e.g. ['CLmain']
    period: BarPeriod = BarPeriod.DAY,
    begin_time: int = -1,
    end_time: int = -1,
    limit: int = 251,
    lang: str = None
) -> DataFrame
```

### get_future_briefs — Futures Snapshots

```python
quote_client.get_future_briefs(
    identifiers: List[str]   # e.g. ['CLmain', 'GCmain']
) -> DataFrame
```

### get_future_trading_date — Futures Trading Calendar

```python
quote_client.get_future_trading_date(
    identifier: str,           # e.g. 'CLmain'
    trading_date: str = None   # specific date
) -> DataFrame
```

**Common future identifiers:**
- `CLmain` — WTI Crude Oil main contract
- `GCmain` — Gold main contract
- `SImain` — Silver main contract
- `ESmain` — E-mini S&P 500
- `NQmain` — E-mini Nasdaq 100
- `HSImain` — Hang Seng Index

---

## Symbol Search {#symbol-search}

### get_symbols — List Tradable Symbols

```python
from tigeropen.common.consts import Market, SecurityType

quote_client.get_symbols(
    market: Market = Market.ALL,
    sec_type: SecurityType = SecurityType.STK,
    lang: str = None
) -> list
```

### get_symbol_names — Symbol Name Mapping

```python
quote_client.get_symbol_names(
    symbols: List[str],
    lang: str = None
) -> DataFrame
```
