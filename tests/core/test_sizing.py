import pytest

from otomai.core.sizing import batch_notional, equity_amount, executable_bid

CAPS = {"trade_pct": 5, "max_gross_pct": 30, "max_cohort_pct": 10}
GATES = {"max_spread_bps": 50, "max_slippage_bps": 50, "max_participation": 0.01}


def test_equity_amount():
    assert equity_amount(1000, 10, 20) == 5


def test_simultaneous_budget_pro_rata_and_caps():
    assert batch_notional(10000, 10000, 0, 0, 3, **CAPS) == pytest.approx(1000 / 3)
    assert batch_notional(10000, 50, 0, 0, 1, **CAPS) == 50
    assert batch_notional(10000, 10000, 3000, 0, 1, **CAPS) == 0
    assert batch_notional(10000, 10000, 0, 900, 1, **CAPS) == 100
    assert batch_notional(0, 10000, 0, 0, 1, **CAPS) == 0


def test_executable_bid_liquidity_gates():
    book = {"bids": [(100.0, 1000.0)], "asks": [(100.1, 1000.0)]}
    assert executable_bid(book, 500, **GATES) == 100
    with pytest.raises(ValueError, match="depth"):
        executable_bid(book, 2000, **GATES)
    with pytest.raises(ValueError, match="Spread"):
        executable_bid({"bids": [(100.0, 1e6)], "asks": [(101.0, 1e6)]}, 10, **GATES)
    with pytest.raises(ValueError, match="Empty"):
        executable_bid({"bids": [], "asks": []}, 10, **GATES)
