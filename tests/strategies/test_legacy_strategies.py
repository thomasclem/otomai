"""The single-order strategies use the exchange port and the shared order service."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest
from pydantic import ValidationError

from otomai.adapters import ConsoleNotifier
from otomai.core.enums import OrderSide
from otomai.core.parameters import TradingParams
from otomai.services import orders
from otomai.strategies.dumb_rsi import DumbRSIStrategy, DumbRSIStrategyParams
from otomai.strategies.mrat_zscore import MratZscoreStrategy, MratZscoreStrategyParams


def test_mrat_checks_occupied_symbol_before_empty_history():
    x = SimpleNamespace(
        positions=Mock(return_value=[{"contracts": 1}]),
        open_orders=Mock(return_value=[]),
        position_history=Mock(return_value=[]),
    )
    bot = MratZscoreStrategy.model_construct(
        symbol="NEW/USDT:USDT",
        exchange_service=x,
        strategy_params=MratZscoreStrategyParams(),
        trading_params=TradingParams(),
    )
    assert not bot._should_open_position(pd.DataFrame(), 10, 2)
    x.position_history.assert_not_called()


def test_mrat_moving_averages_must_be_ordered():
    with pytest.raises(ValidationError):
        MratZscoreStrategyParams(fast_ma_length=60, slow_ma_length=51)


def strategy(kind, params, x):
    bot = kind.model_construct(
        exchange_service=x,
        notifier_service=ConsoleNotifier(),
        strategy_params=params,
        trading_params=TradingParams(),
    )
    bot._position_monitor = SimpleNamespace(monitor_position=AsyncMock())
    return bot


@pytest.mark.asyncio
@pytest.mark.parametrize("side,opened", [(OrderSide.SELL, 1), (OrderSide.BUY, 0)])
async def test_allowed_signals_open_and_monitor_a_position(monkeypatch, side, opened):
    place = Mock(return_value={"id": "o"})
    monkeypatch.setattr(orders, "open_position", place)
    bot = strategy(DumbRSIStrategy, DumbRSIStrategyParams(), SimpleNamespace())
    await bot._process_signal("NEW/USDT:USDT", side, bot.trading_params)  # SELL is allowed
    await asyncio.sleep(0)
    assert place.call_count == opened
    assert bot._position_monitor.monitor_position.call_count == opened
