#!/usr/bin/env python3
"""
Tiger OpenAPI Client Initialization Helper

Provides convenience functions to quickly set up Tiger API clients
from a properties configuration file.

Usage:
    from tiger_client_init import get_client_config, get_quote_client, get_trade_client, get_push_client

    config = get_client_config('/path/to/tiger_openapi_config.properties')
    quote_client = get_quote_client(config)
    trade_client = get_trade_client(config)
"""

import os
import sys


def get_client_config(props_path: str):
    """
    Create a TigerOpenClientConfig from a properties file.

    Args:
        props_path: Path to the tiger_openapi_config.properties file

    Returns:
        TigerOpenClientConfig instance ready for use with any client
    """
    from tigeropen.tiger_open_client_config import TigerOpenClientConfig
    from tigeropen.common.consts import Language

    if not os.path.exists(props_path):
        raise FileNotFoundError(f"Config file not found: {props_path}")

    client_config = TigerOpenClientConfig(props_path=props_path)
    client_config.language = Language.en_US
    return client_config


def get_quote_client(client_config):
    """Create a QuoteClient for market data queries."""
    from tigeropen.quote.quote_client import QuoteClient
    return QuoteClient(client_config)


def get_trade_client(client_config):
    """Create a TradeClient for order management and account queries."""
    from tigeropen.trade.trade_client import TradeClient
    return TradeClient(client_config)


def get_push_client(client_config):
    """Create a PushClient for real-time WebSocket streaming."""
    from tigeropen.push.push_client import PushClient
    return PushClient(client_config)


def get_all_clients(props_path: str):
    """
    Convenience function: create config + all three clients at once.

    Args:
        props_path: Path to the tiger_openapi_config.properties file

    Returns:
        tuple: (client_config, quote_client, trade_client, push_client)
    """
    config = get_client_config(props_path)
    return (
        config,
        get_quote_client(config),
        get_trade_client(config),
        get_push_client(config),
    )


# ─── Quick-start templates ───────────────────────────────────────────

def demo_get_stock_quotes(props_path: str, symbols: list):
    """Quick demo: fetch stock quotes and print them."""
    config = get_client_config(props_path)
    qc = get_quote_client(config)
    df = qc.get_stock_briefs(symbols)
    print(df.to_string())
    return df


def demo_get_positions(props_path: str):
    """Quick demo: fetch all positions and print them."""
    config = get_client_config(props_path)
    tc = get_trade_client(config)
    positions = tc.get_positions()
    for pos in positions:
        sym = pos.contract.symbol
        qty = pos.quantity
        cost = pos.average_cost
        pnl = getattr(pos, 'unrealized_pnl', 'N/A')
        print(f"{sym}: {qty} shares @ ${cost:.2f}, Unrealized P&L: {pnl}")
    return positions


def demo_get_account(props_path: str):
    """Quick demo: fetch account summary and print it."""
    config = get_client_config(props_path)
    tc = get_trade_client(config)
    account = tc.get_account()
    print(f"Account:          {account.account}")
    print(f"Net Liquidation:  {account.net_liquidation}")
    print(f"Available Funds:  {account.available_funds}")
    print(f"Buying Power:     {account.buying_power}")
    print(f"Cash:             {account.cash}")
    return account


if __name__ == '__main__':
    # Simple CLI usage: python tiger_client_init.py <props_path> <command> [args...]
    if len(sys.argv) < 3:
        print("Usage: python tiger_client_init.py <props_path> <command> [args...]")
        print("Commands: quotes <SYM1,SYM2,...> | positions | account")
        sys.exit(1)

    props = sys.argv[1]
    cmd = sys.argv[2]

    if cmd == 'quotes' and len(sys.argv) > 3:
        symbols = sys.argv[3].split(',')
        demo_get_stock_quotes(props, symbols)
    elif cmd == 'positions':
        demo_get_positions(props)
    elif cmd == 'account':
        demo_get_account(props)
    else:
        print(f"Unknown command: {cmd}")
