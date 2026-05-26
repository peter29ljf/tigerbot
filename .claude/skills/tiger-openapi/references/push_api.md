# Push API Reference (Real-time WebSocket)

## Table of Contents
1. [PushClient Setup](#setup)
2. [Quote Subscriptions](#quote-sub)
3. [Order Status Subscriptions](#order-sub)
4. [Asset & Position Subscriptions](#asset-sub)
5. [Callback Handlers](#callbacks)
6. [Connection Management](#connection)

---

## PushClient Setup {#setup}

```python
from tigeropen.push.push_client import PushClient

push_client = PushClient(client_config)

# Connect to WebSocket server
push_client.connect(timeout=30)

# Check connection status
print(push_client.is_connected())
```

The PushClient uses Protocol Buffers (v3.0.0+) for efficient data serialization over WebSocket.

---

## Quote Subscriptions {#quote-sub}

### subscribe_quote — Real-time Quote Updates

```python
push_client.subscribe_quote(
    symbols=['AAPL', 'TSLA', 'GOOG']
)
```

### subscribe_tick — Real-time Tick Data

```python
push_client.subscribe_tick(
    symbols=['AAPL']
)
```

### subscribe_depth_quote — Level 2 / Order Book

```python
push_client.subscribe_depth_quote(
    symbols=['AAPL']
)
```

### subscribe_option — Option Quote Updates

```python
push_client.subscribe_option(
    symbols=['AAPL  230120C00150000']  # option identifiers
)
```

### subscribe_future — Future Quote Updates

```python
push_client.subscribe_future(
    symbols=['CLmain']
)
```

### Unsubscribe

```python
push_client.unsubscribe_quote(symbols=['AAPL'])
push_client.unsubscribe_tick(symbols=['AAPL'])
push_client.unsubscribe_depth_quote(symbols=['AAPL'])
```

---

## Order Status Subscriptions {#order-sub}

### subscribe_order — Order Status Changes

```python
push_client.subscribe_order(account='6481265')
```

Receives callbacks when order status changes (filled, cancelled, etc.)

---

## Asset & Position Subscriptions {#asset-sub}

### subscribe_asset — Asset Changes

```python
push_client.subscribe_asset(account='6481265')
```

### subscribe_position — Position Changes

```python
push_client.subscribe_position(account='6481265')
```

---

## Callback Handlers {#callbacks}

Set up callback functions before subscribing:

```python
from tigeropen.push.push_client import PushClient

push_client = PushClient(client_config)

# Quote data callback
def on_quote_changed(symbol, data, trading_session):
    print(f"Quote update: {symbol}")
    print(f"  Price: {data.get('latest_price')}")
    print(f"  Volume: {data.get('volume')}")

# Order status callback
def on_order_changed(account, data):
    print(f"Order update: {data}")

# Asset change callback
def on_asset_changed(account, data):
    print(f"Asset update: {data}")

# Position change callback
def on_position_changed(account, data):
    print(f"Position update: {data}")

# Connection callbacks
def on_connected():
    print("Connected to push server")
    # Subscribe after connection established
    push_client.subscribe_quote(['AAPL', 'TSLA'])

def on_disconnected():
    print("Disconnected from push server")

def on_error(error):
    print(f"Push error: {error}")

# Register callbacks
push_client.quote_changed = on_quote_changed
push_client.order_changed = on_order_changed
push_client.asset_changed = on_asset_changed
push_client.position_changed = on_position_changed
push_client.connect_callback = on_connected
push_client.disconnect_callback = on_disconnected
push_client.error_callback = on_error

# Connect and start receiving
push_client.connect(timeout=30)
```

---

## Connection Management {#connection}

```python
# Check connection
push_client.is_connected()

# Disconnect
push_client.disconnect()

# Reconnect
push_client.connect(timeout=30)

# Query currently subscribed symbols
push_client.query_subscribed_quote()
```

**Full working example — stream AAPL quotes:**
```python
import time
from tigeropen.tiger_open_client_config import TigerOpenClientConfig
from tigeropen.push.push_client import PushClient

client_config = TigerOpenClientConfig(props_path='tiger_openapi_config.properties')
push_client = PushClient(client_config)

def on_quote_changed(symbol, data, trading_session):
    price = data.get('latest_price', 'N/A')
    vol = data.get('volume', 'N/A')
    print(f"[{symbol}] Price: {price}, Volume: {vol}")

push_client.quote_changed = on_quote_changed
push_client.connect(timeout=30)
push_client.subscribe_quote(['AAPL'])

# Keep running for 60 seconds
try:
    time.sleep(60)
finally:
    push_client.disconnect()
```
