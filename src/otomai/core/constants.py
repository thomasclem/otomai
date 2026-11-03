"""
Constants for the Otomai trading bot.

Only values shared across layers live here; venue and strategy constants live next
to the adapter or strategy that owns them.
"""

# %% TIME UNITS

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS

# %% RETRY CONFIGURATION

# Number of seconds to wait between retries for API calls
RETRY_DELAY_SECONDS = 5.0

# Maximum number of retry attempts for OHLCV data fetching
MAX_OHLCV_FETCH_RETRIES = 20

# Maximum number of retry attempts for market data fetching
MAX_MARKET_FETCH_RETRIES = 10

# Maximum number of concurrent requests for batch operations
MAX_CONCURRENT_REQUESTS = 10

# %% POSITION MONITORING

# Sleep interval in seconds when monitoring position opening
POSITION_OPENING_CHECK_INTERVAL = 1

# Sleep interval in seconds when monitoring position closing
POSITION_CLOSING_CHECK_INTERVAL = 60

# Default timeout in seconds for position opening
POSITION_OPENING_TIMEOUT = 600

# Maximum timeout in seconds for position closing monitoring
POSITION_CLOSING_MAX_TIMEOUT = 86400  # 24 hours
