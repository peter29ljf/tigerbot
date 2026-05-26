# Client Setup & Configuration

## Table of Contents
1. [Loading Config from Properties File](#loading-config)
2. [Manual Configuration](#manual-config)
3. [Creating Clients](#creating-clients)
4. [Environment & Language Settings](#settings)

---

## Loading Config from Properties File {#loading-config}

The easiest way to initialize is from a `.properties` file:

```python
from tigeropen.tiger_open_client_config import TigerOpenClientConfig

# Load from properties file
client_config = TigerOpenClientConfig(props_path='path/to/tiger_openapi_config.properties')
```

The properties file must contain:
- `tiger_id` — Developer ID (string)
- `private_key_pk8` — RSA private key in PKCS8 format
- `account` — Trading account number
- `license` — License code (e.g., "TBNZ")

## Manual Configuration {#manual-config}

```python
from tigeropen.tiger_open_client_config import TigerOpenClientConfig
from tigeropen.common.consts import Language

client_config = TigerOpenClientConfig()
client_config.tiger_id = '20158215'
client_config.account = '6481265'
client_config.private_key = '''-----BEGIN RSA PRIVATE KEY-----
<PKCS8 key content here>
-----END RSA PRIVATE KEY-----'''
client_config.language = Language.en_US
```

## Creating Clients {#creating-clients}

```python
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.trade.trade_client import TradeClient
from tigeropen.push.push_client import PushClient

# Quote client — for market data
quote_client = QuoteClient(client_config)

# Trade client — for orders, positions, account
trade_client = TradeClient(client_config)

# Push client — for real-time WebSocket
push_client = PushClient(client_config)
```

## Environment & Language Settings {#settings}

```python
from tigeropen.common.consts import Language

# Language options
client_config.language = Language.en_US   # English
client_config.language = Language.zh_CN   # Chinese
client_config.language = Language.zh_TW   # Traditional Chinese

# The env field in properties controls PROD vs SANDBOX
# PROD = real trading, SANDBOX = paper trading
```

## Using the Helper Script

The skill includes `scripts/tiger_client_init.py` which provides a ready-made initialization function:

```python
import sys
sys.path.insert(0, '<skill-scripts-path>')
from tiger_client_init import get_client_config, get_quote_client, get_trade_client

config = get_client_config('/path/to/tiger_openapi_config.properties')
quote_client = get_quote_client(config)
trade_client = get_trade_client(config)
```
