# Position Monitor Service

The Position Monitor service handles all position lifecycle tracking, implementing separation of concerns by extracting monitoring logic from strategy classes.

## Purpose

- Monitor position opening with timeout
- Monitor position closing with retry logic
- Save completed positions to database
- Send notifications on position events
- Support concurrent position monitoring

## Usage

```python
# Strategies access via property
asyncio.create_task(
    self.position_monitor.monitor_position(
        symbol="ETH/USDT:USDT",
        open_date="2024-02-04 19:00:00"
    )
)
```

## Configuration

Timeouts and intervals are configured in `core/constants.py`:

```python
POSITION_OPENING_TIMEOUT = 600  # 10 minutes
POSITION_CLOSING_MAX_TIMEOUT = 86400  # 24 hours
POSITION_OPENING_CHECK_INTERVAL = 1  # 1 second
POSITION_CLOSING_CHECK_INTERVAL = 60  # 1 minute
```

## Error Handling

- `PositionTimeoutError`: Position didn't open/close within timeout
- `PositionMonitoringError`: General monitoring failure

## Benefits

- **Testable**: Can unit test independently
- **Reusable**: Shared across all strategies  
- **Maintainable**: All position logic in one place
- **Configurable**: Centralized timeout settings
