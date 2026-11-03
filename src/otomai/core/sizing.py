"""Pure position-sizing and liquidity rules shared by strategies."""

import math


def equity_amount(capital: float, equity_trade_pct: float, price: float) -> float:
    """Base quantity buying `equity_trade_pct` of `capital` at `price`."""
    return capital * equity_trade_pct / 100 / price


def batch_notional(
    equity: float,
    free_cash: float,
    gross: float,
    cohort: float,
    count: int,
    *,
    trade_pct: float,
    max_gross_pct: float,
    max_cohort_pct: float,
) -> float:
    """Equal notional per simultaneous candidate; caps are checked at entry only."""
    values = (equity, free_cash, gross, cohort)
    if count <= 0 or not all(math.isfinite(v) for v in values) or equity <= 0:
        return 0.0
    budget = min(
        count * equity * trade_pct / 100,
        equity * max_gross_pct / 100 - gross,
        equity * max_cohort_pct / 100 - cohort,
        free_cash,
    )
    return max(0.0, budget) / count


def executable_bid(
    book: dict,
    notional: float,
    *,
    max_spread_bps: float,
    max_slippage_bps: float,
    max_participation: float,
) -> float:
    """Best bid of a normalized order book, if a short of `notional` passes the liquidity gates."""
    if not book["bids"] or not book["asks"]:
        raise ValueError("Empty order book")
    bid, ask = book["bids"][0][0], book["asks"][0][0]
    if bid <= 0 or ask < bid or (ask - bid) / ((ask + bid) / 2) * 10_000 > max_spread_bps:
        raise ValueError("Spread exceeds admission limit")
    floor = bid * (1 - max_slippage_bps / 10_000)
    depth = sum(price * qty for price, qty in book["bids"] if price >= floor)
    if not math.isfinite(depth) or depth <= 0 or notional > depth * max_participation:
        raise ValueError("Order exceeds available bid-depth participation")
    return bid
