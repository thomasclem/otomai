"""
Custom exceptions for the Otomai trading bot.

This module defines specific exception classes to improve error handling
and make debugging easier.
"""


class OtomaiError(Exception):
    """Base exception for all Otomai errors."""

    pass


class StrategyExecutionError(OtomaiError):
    """Raised when a strategy fails to execute properly."""

    pass


class ExchangeConnectionError(OtomaiError):
    """Raised when there are issues connecting to or communicating with an exchange."""

    pass


class PositionMonitoringError(OtomaiError):
    """Raised when position monitoring encounters an error."""

    pass


class InvalidConfigurationError(OtomaiError):
    """Raised when configuration validation fails."""

    pass


class OrderExecutionError(OtomaiError):
    """Raised when an order fails to execute properly."""

    pass


class DataValidationError(OtomaiError):
    """Raised when data validation fails (e.g., empty DataFrames, invalid values)."""

    pass


class PositionTimeoutError(PositionMonitoringError):
    """Raised when position monitoring times out."""

    pass
