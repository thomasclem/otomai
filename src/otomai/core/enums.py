from enum import Enum

# %% ORDER


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


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
