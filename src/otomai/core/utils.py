# %% IMPORTS


import math

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
    ts = pd.Timestamp(date)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int(ts.timestamp() * 1000)


def validate_ohlcv_bar(row):
    """Validate a six-field observed candle; zero volume is valid after listing."""
    if len(row) < 6:
        raise ValueError("Incomplete OHLCV row")
    o, hi, lo, close, volume = map(float, row[1:6])
    if not all(math.isfinite(x) for x in (o, hi, lo, close, volume)):
        raise ValueError("Non-finite OHLCV")
    if min(o, hi, lo, close) <= 0 or volume < 0:
        raise ValueError("Invalid price or volume")
    if hi < max(o, lo, close) or lo > min(o, hi, close):
        raise ValueError("Incoherent OHLC")
    return o, hi, lo, close, volume


def positive_number(value, name):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid {name}")
    return number
