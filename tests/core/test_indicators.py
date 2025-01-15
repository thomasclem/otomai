import pytest
import pandas as pd
from ta.trend import sma_indicator
from otomai.core.indicators import MRAT


@pytest.fixture
def sample_values():
    """Sample data for testing."""
    return pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])


def test_mrat_initialization(sample_values):
    """Test if MRAT initializes correctly with valid inputs."""
    mrat = MRAT(slow_ma_length=5, fast_ma_length=3, values=sample_values)
    assert isinstance(mrat, MRAT)


def test_mrat_invalid_initialization(sample_values):
    """Test if MRAT raises an error when slow_ma_length <= fast_ma_length."""
    with pytest.raises(ValueError, match="slow_ma_length must be greater than fast_ma_length"):
        MRAT(slow_ma_length=3, fast_ma_length=3, values=sample_values)


def test_mrat_calculation(sample_values):
    """Test if MRAT ratio is calculated correctly."""
    slow_ma_length = 5
    fast_ma_length = 3
    mrat = MRAT(slow_ma_length=slow_ma_length, fast_ma_length=fast_ma_length, values=sample_values)

    # Calculate expected values using sma_indicator directly
    fast_ma_series = sma_indicator(close=sample_values, window=fast_ma_length)
    slow_ma_series = sma_indicator(close=sample_values, window=slow_ma_length)
    expected_mrat = fast_ma_series / slow_ma_series

    # Compare the calculated MRAT with the expected values
    pd.testing.assert_series_equal(mrat.calculate_mrat(), expected_mrat, check_names=False)


def test_mrat_empty_series():
    """Test MRAT with an empty Series."""
    empty_series = pd.Series([])
    with pytest.raises(ValueError):
        MRAT(slow_ma_length=5, fast_ma_length=3, values=empty_series)
