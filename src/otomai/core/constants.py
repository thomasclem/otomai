"""
Constants for the Otomai trading bot.

This module centralizes all magic numbers and configuration constants
to improve maintainability and reduce code duplication.
"""

# %% RETRY CONFIGURATION

# Number of seconds to wait between retries for API calls
RETRY_DELAY_SECONDS = 5.0

# Maximum number of retry attempts for OHLCV data fetching
MAX_OHLCV_FETCH_RETRIES = 20

# Maximum number of retry attempts for order placement
MAX_ORDER_RETRIES = 3

# Maximum number of retry attempts for market data fetching
MAX_MARKET_FETCH_RETRIES = 10

# %% POSITION MONITORING

# Sleep interval in seconds when monitoring position opening
POSITION_OPENING_CHECK_INTERVAL = 1

# Sleep interval in seconds when monitoring position closing
POSITION_CLOSING_CHECK_INTERVAL = 60

# Default timeout in seconds for position opening
POSITION_OPENING_TIMEOUT = 600

# Maximum timeout in seconds for position closing monitoring
POSITION_CLOSING_MAX_TIMEOUT = 86400  # 24 hours

# %% STRATEGY EXECUTION

# Sleep interval in seconds when checking for new listings
NEW_LISTING_CHECK_INTERVAL = 10

# Sleep interval in seconds after detecting new listings before processing
NEW_LISTING_PROCESSING_DELAY = 60

# Minimum ghost candle threshold for data validation (%)
GHOST_CANDLE_THRESHOLD = 0.5

# %% SAFETY MARGINS

# Default safety margin for order sizing (2%)
DEFAULT_SAFETY_MARGIN = 0.02

# %% ORDER CONFIGURATION

# Default product type for Bitget futures
BITGET_PRODUCT_TYPE = "UMCBL"

# Default margin coin for Bitget
BITGET_MARGIN_COIN = "USDT"

# Time to wait before querying another time the OHLCV data for a new listing
LISTING_DATA_AVAILABILITY_WINDOW = 60 * 30

# Maximum number of concurrent requests for batch operations
MAX_CONCURRENT_REQUESTS = 10
