"""Reconcile JSON state with broker holdings."""

from state.state import StateStore


def restore_from_broker(state: StateStore, symbol: str, qty: int, avg_price: float) -> dict:
    """Update qty/avg from API; T and cash unchanged."""
    return state.sync_holdings(symbol, qty, avg_price)
