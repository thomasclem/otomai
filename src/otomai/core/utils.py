# %% IMPORTS

import typing as T
from datetime import datetime, timezone

import pandas as pd

from otomai.core.enums import OrderSide

# %% TRADING


def calculate_take_profit_price(
    price: float, order_side: OrderSide, take_profit_pct: float, leverage: int = 1
) -> float:
    adjustment = (take_profit_pct / 100) / leverage
    if order_side == OrderSide.SELL:
        tp = price * (1 - adjustment)
    elif order_side == OrderSide.BUY:
        tp = price * (1 + adjustment)
    else:
        tp = 0.0
    return tp


def calculate_stop_loss_price(
    price: float, order_side: OrderSide, stop_loss_pct: float, leverage: int = 1
) -> float:
    adjustment = (stop_loss_pct / 100) / leverage
    if order_side == OrderSide.SELL:
        sl = price * (1 + adjustment)
    elif order_side == OrderSide.BUY:
        sl = price * (1 - adjustment)
    else:
        sl = 0.0
    return sl

# %% DATE FORMATTING


def get_ts_in_ms_from_date(date: str) -> int:
    """
    Converts a given date string into a Unix timestamp in milliseconds (UTC).
    """
    ts = pd.Timestamp(date, tz="UTC")
    return int(ts.timestamp()) * 1000


def get_date_from_ts_in_ms(timestamp_ms: int) -> str:
    """
    Converts a Unix timestamp in milliseconds to a date string in the format "YYYY-MM-DD HH:MM:SS" (UTC).
    """
    ts = pd.Timestamp(timestamp_ms, unit="ms", tz="UTC")
    return ts.strftime("%Y-%m-%d %H:%M:%S")
