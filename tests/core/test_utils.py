import pytest
from otomai.core.enums import OrderSide
from otomai.core.utils import (
    calculate_take_profit_price,
    calculate_stop_loss_price,
    get_ts_in_ms_from_date,
    get_date_from_ts_in_ms,
)

# %% TEST TAKE PROFIT PRICE


@pytest.mark.parametrize(
    "price, order_side, take_profit_pct, leverage, expected_tp",
    [
        (100.0, OrderSide.BUY, 10.0, 1, 110.0),  # BUY order, 10% TP
        (100.0, OrderSide.SELL, 10.0, 1, 90.0),  # SELL order, 10% TP
        (200.0, OrderSide.BUY, 5.0, 2, 205.0),  # BUY order, 5% TP with 2x leverage
        (200.0, OrderSide.SELL, 5.0, 2, 195.0),  # SELL order, 5% TP with 2x leverage
    ],
)
def test_calculate_take_profit_price(
    price, order_side, take_profit_pct, leverage, expected_tp
):
    """Test calculate_take_profit_price function."""
    tp = calculate_take_profit_price(price, order_side, take_profit_pct, leverage)
    assert tp == pytest.approx(expected_tp, rel=1e-2)


def test_calculate_take_profit_price_invalid_order_side():
    """Test calculate_take_profit_price with invalid order side."""
    tp = calculate_take_profit_price(100.0, "INVALID", 10.0)
    assert tp == 0.0


# %% TEST STOP LOSS PRICE


@pytest.mark.parametrize(
    "price, order_side, stop_loss_pct, leverage, expected_sl",
    [
        (100.0, OrderSide.BUY, 10.0, 1, 90.0),  # BUY order, 10% SL
        (100.0, OrderSide.SELL, 10.0, 1, 110.0),  # SELL order, 10% SL
        (200.0, OrderSide.BUY, 5.0, 2, 195.0),  # BUY order, 5% SL with 2x leverage
        (200.0, OrderSide.SELL, 5.0, 2, 205.0),  # SELL order, 5% SL with 2x leverage
    ],
)
def test_calculate_stop_loss_price(
    price, order_side, stop_loss_pct, leverage, expected_sl
):
    """Test calculate_stop_loss_price function."""
    sl = calculate_stop_loss_price(price, order_side, stop_loss_pct, leverage)
    assert sl == pytest.approx(expected_sl, rel=1e-2)


def test_calculate_stop_loss_price_invalid_order_side():
    """Test calculate_stop_loss_price with invalid order side."""
    sl = calculate_stop_loss_price(100.0, "INVALID", 10.0)
    assert sl == 0.0


# %% TEST DATE CONVERSIONS


@pytest.mark.parametrize(
    "date, expected_ts",
    [
        ("2024-02-29 12:00:00", 1709208000000),  # Leap year date
    ],
)
def test_get_ts_in_ms_from_date(date, expected_ts):
    ts = get_ts_in_ms_from_date(date)
    assert ts == expected_ts


@pytest.mark.parametrize(
    "timestamp_ms, expected_date",
    [
        (1709208000000, "2024-02-29 12:00:00"),  # Leap year date
    ],
)
def test_get_date_from_ts_in_ms(timestamp_ms, expected_date):
    date = get_date_from_ts_in_ms(timestamp_ms)
    assert date == expected_date
