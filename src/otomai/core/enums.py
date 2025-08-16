from enum import Enum

# %% ORDER


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"
    NONE = "none"


class OrderMarginMode(Enum):
    ISOLATED = "isolated"
    CROSS = "cross"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


# %% SIDE


class TradeSide(Enum):
    OPEN = "open"
    CLOSE = "close"


# %% TIMEFRAME


class OHLCVTimeframe(Enum):
    """
    Enumeration of supported OHLCV timeframes.
    Values correspond to ccxt standard timeframe strings.
    """

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1M"

    def __str__(self) -> str:
        return self.value
