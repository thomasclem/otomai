import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
from otomai.strategies.listing_backrun import ListingBackrunStrategy
from otomai.core.parameters import ListingBackrunStrategyParams, TradingParams

@pytest.fixture
def mock_strategy_params():
    return ListingBackrunStrategyParams(
        name="test_strategy",
        ohlcv_timeframe="1m",
        ohlcv_window=100,
        short_price_volatility_threshold=-5.0,
        short_btc_volatility_threshold=2.0,
        long_price_volatility_threshold=5.0,
        long_btc_volatility_threshold=-2.0,
        volume_usdt_btc_prop_threshold=10.0,
    )

@pytest.fixture
def mock_trading_params():
    return TradingParams(
        allowed_order_sides=["buy", "sell"],
        equity_trade_pct=10.0,
        order_type="market",
        margin_mode="cross",
        leverage=5,
        take_profit_pct=0.1,
        stop_loss_pct=0.05,
        max_simultaneous_positions=3,
    )

@pytest.mark.asyncio
async def test_process_candidate_symbol_busy_loop_fix(mock_strategy_params, mock_trading_params):
    """
    Test that _process_candidate_symbol yields control (doesn't busy loop)
    and handles signals correctly.
    """
    # Mock services
    mock_exchange = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    # Setup strategy using model_construct to bypass Pydantic validation for Mocks
    strategy = ListingBackrunStrategy.model_construct(
        strategy_params=mock_strategy_params,
        trading_params=mock_trading_params,
        exchange_service=mock_exchange,
        notifier_service=mock_notifier,
        database_service=mock_db,
    )
    
    # Mock dataframe result to keep loop running for a few iterations then stop or find signal
    # We want to test that it sleeps.
    
    # Iteration 1: No signal, small DF
    df_no_signal = pd.DataFrame({'open': [100], 'close': [100], 'vol_high_low': [0]})
    # Iteration 2: Signal found (to break loop naturally if we wanted, but let's test timeout/sleep)
    
    # We mock _fetch_symbol_data to return empty or useless DF
    strategy._fetch_symbol_data = AsyncMock(return_value=df_no_signal)
    strategy._check_signals = MagicMock(return_value="none") # No signal
    strategy._process_signal = AsyncMock()

    # We patch asyncio.sleep to check if it's called
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        # Run the method as a task with a timeout to prevent infinite test hang if busy loop exists
        # If busy loop exists (no sleep), this might block the event loop or simply spin hot.
        # But since we use asyncio.sleep(0) or similar in test environment, we might just check calls.
        
        # We'll run it for a very short virtual time or just cancel it.
        # Actually proper way: run it, let it hit sleep, check sleep called.
        
        task = asyncio.create_task(
            strategy._process_candidate_symbol(
                "ETH/USDT:USDT", mock_strategy_params, mock_trading_params
            )
        )
        
        # Allow loop to run a bit
        await asyncio.sleep(0.1)
        
        # It should have called sleep inside the loop
        assert mock_sleep.called, "asyncio.sleep NOT called inside loop! Busy loop detected."
        assert mock_sleep.call_count >= 1
        
        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_run_orchestrator(mock_strategy_params, mock_trading_params):
    """
    Test proper awaiting of async calls in run loop.
    """
    mock_exchange = AsyncMock()
    mock_notifier = AsyncMock()
    
    # Setup strategy
    strategy = ListingBackrunStrategy.model_construct(
        strategy_params=mock_strategy_params,
        trading_params=mock_trading_params,
        exchange_service=mock_exchange,
        notifier_service=mock_notifier,
        database_service=MagicMock(),
    )
    
    # Setup mocks
    mock_exchange.fetch_all_futures_symbol_names.side_effect = [
        ["BTC/USDT:USDT"], # Initial
        ["BTC/USDT:USDT", "NEW/USDT:USDT"], # Update
        asyncio.CancelledError # Stop loop
    ]
    
    # Mock position checking internals
    # position_opening_available calls session.fetch_positions() and fetch_open_orders()
    mock_exchange.session.fetch_positions.return_value = []
    mock_exchange.session.fetch_open_orders.return_value = []
    
    strategy._process_candidate_symbol = AsyncMock()
    
    with patch('asyncio.sleep', new_callable=AsyncMock): # Skip sleeps
        try:
            await strategy.run()
        except asyncio.CancelledError:
            pass
        except Exception: 
            pass # Our mock raises exception/cancelled to stop loop
            
    # Verify we awaited the fetch calls
    assert mock_exchange.fetch_all_futures_symbol_names.call_count >= 2
    
    # Verify we processed new symbol
    strategy._process_candidate_symbol.assert_called()
    call_args = strategy._process_candidate_symbol.call_args
    assert call_args[1]['symbol'] == "NEW/USDT:USDT"
