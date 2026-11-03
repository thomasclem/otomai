"""
Custom exceptions for the Otomai trading bot.

This module defines specific exception classes to improve error handling
and make debugging easier.
"""


class OtomaiError(Exception):
    """Base exception for all Otomai errors."""

    pass


class ExchangeConnectionError(OtomaiError):
    """Raised when there are issues connecting to or communicating with an exchange."""

    pass


class PositionMonitoringError(OtomaiError):
    """Raised when position monitoring encounters an error."""

    pass


class OrderExecutionError(OtomaiError):
    """Raised when an order fails to execute properly."""

    pass


class PositionTimeoutError(PositionMonitoringError):
    """Raised when position monitoring times out."""

    pass


class OrderNotFound(OtomaiError):
    """Raised by the exchange port when a venue has no order for a client ID."""

    pass


class InsufficientFunds(OrderExecutionError):
    """Raised by the exchange port when the venue explicitly rejects an order for margin."""

    pass
