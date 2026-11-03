"""Shared CCXT implementation of the exchange port; venues override the differences."""

import abc
import asyncio
import hashlib
import math
import os
import time
import typing as T

import ccxt
import pandas as pd
import pydantic as pdt

from otomai.core.constants import (
    MAX_CONCURRENT_REQUESTS,
    MAX_MARKET_FETCH_RETRIES,
    MAX_OHLCV_FETCH_RETRIES,
    RETRY_DELAY_SECONDS,
)
from otomai.core.enums import OrderSide, TradeSide
from otomai.core.exceptions import ExchangeConnectionError, InsufficientFunds
from otomai.core.models import (
    ClosedPosition,
    ExchangeFill,
    ExchangeOrder,
    ExchangePosition,
    OrderBook,
)
from otomai.logger import Logger
from otomai.ports.exchange import Exchange

logger = Logger(__name__)


def number(value, name, *, optional=False):
    if value is None or value == "":
        if optional:
            return None
        raise ValueError(f"Missing {name}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite {name}")
    return result


def first(data, *keys):
    return next((data[k] for k in keys if data.get(k) is not None and data[k] != ""), None)


def flag(value):
    if value is None:
        return None
    if value is True or str(value).lower() in {"true", "yes", "1"}:
        return True
    if value is False or str(value).lower() in {"false", "no", "0"}:
        return False
    raise ValueError("Unknown exchange boolean")


class CcxtExchange(Exchange):
    """Credentials come from fields or `<KIND>_API_KEY`-style variables; the session is lazy."""

    apiKey: str | bytes | None = pdt.Field(default=None, repr=False, exclude=True)
    secret: str | bytes | None = pdt.Field(default=None, repr=False, exclude=True)
    password: str | bytes | None = pdt.Field(default=None, repr=False, exclude=True)
    auth_object: dict | None = pdt.Field(default=None, repr=False, exclude=True)
    default_type: T.Literal["future", "swap"] = "swap"
    # Extra options of every trigger (stop/take-profit) order, e.g. the price that triggers it.
    trigger_params: T.ClassVar[dict] = {}
    _session: T.Any = pdt.PrivateAttr(default=None)

    def _session_config(self):
        config = dict(self.auth_object or {})
        for name, suffix in [("apiKey", "API_KEY"), ("secret", "SECRET"), ("password", "PASSWORD")]:
            value = (
                getattr(self, name)
                or config.get(name)
                or os.getenv(f"{self.KIND.upper()}_{suffix}")
            )
            if value:
                config[name] = value
        config["options"] = {"defaultType": self.default_type, **config.get("options", {})}
        config.setdefault("enableRateLimit", True)
        config.setdefault("timeout", 15000)
        return config

    @property
    def session(self):
        """Raw transport is reserved for wrapper implementations and adapter tests."""
        if self._session is None:
            self._session = self.initialize_session()
        return self._session

    @abc.abstractmethod
    def initialize_session(self):
        raise NotImplementedError

    def require_live_credentials(self):
        self.session.check_required_credentials()

    def is_authenticated(self):
        return bool(self.session.check_required_credentials(False))

    def account_fingerprint(self):
        return hashlib.sha256(str(self.session.apiKey).encode()).hexdigest()

    def markets(self):
        return {
            s: self.normalize_market(m) for s, m in self.session.load_markets(reload=True).items()
        }

    def normalize_market(self, market):
        normalized = {
            key: market.get(key)
            for key in (
                "symbol",
                "base",
                "swap",
                "linear",
                "settle",
                "active",
                "contractSize",
                "limits",
                "precision",
                "launchTime",
            )
        }
        normalized["tradfi"] = self.is_tradfi_market(market)
        return normalized

    def is_tradfi_market(self, market) -> bool:
        """Whether a contract tracks a traditional asset (stock, FX, commodity, index)."""
        return False

    def candles(self, symbol, timeframe, since=None, until=None, limit=None):
        params = {"until": until} if until is not None else {}
        return self.session.fetch_ohlcv(symbol, timeframe, since=since, limit=limit, params=params)

    def order_book(self, symbol, depth=50) -> OrderBook:
        book = self.session.fetch_order_book(symbol, limit=depth)
        return {
            side: [(number(p, "book price"), number(q, "book quantity")) for p, q, *_ in book[side]]
            for side in ("bids", "asks")
        }

    def ticker_price(self, symbol):
        price = number(self.session.fetch_ticker(symbol).get("last"), "last price")
        if price <= 0:
            raise ValueError("Invalid last price")
        return price

    def balance(self):
        self.require_live_credentials()
        balance = self.session.fetch_balance()
        equity, free = self._balance(balance)
        equity, free = number(equity, "USDT equity"), number(free, "USDT available margin")
        if equity <= 0 or free < 0:
            raise ValueError("Invalid USDT account balance")
        return equity, free

    def _balance(self, balance):
        return balance["USDT"]["total"], balance["USDT"]["free"]

    def normalize_position(self, p) -> ExchangePosition:
        contracts = abs(number(p.get("contracts"), "position contracts"))
        side = str(p.get("side") or "").lower()
        if side not in {"long", "short"}:
            raise ValueError("Missing normalized position side")
        entry = number(p.get("entryPrice"), "entry price", optional=True)
        mark = number(p.get("markPrice"), "mark price", optional=True)
        notional = number(p.get("notional"), "marked notional", optional=True)
        if notional is None and mark is not None:
            notional = contracts * number(p.get("contractSize") or 1, "contract size") * mark
        return {
            "id": str(p["id"]) if p.get("id") is not None else None,
            "symbol": p["symbol"],
            "side": side,
            "contracts": contracts,
            "entryPrice": entry,
            "markPrice": mark,
            "notional": abs(notional) if notional is not None else None,
            "unrealizedPnl": number(p.get("unrealizedPnl"), "unrealised PnL", optional=True),
            "percentage": number(p.get("percentage"), "return percentage", optional=True),
            "timestamp": p.get("timestamp"),
        }

    def positions(self, symbols=None) -> list[ExchangePosition]:
        self.require_live_credentials()
        raw = (
            self.session.fetch_positions(symbols=symbols)
            if symbols is not None
            else self.session.fetch_positions()
        )
        positions = []
        for p in raw:
            if p.get("contracts") is not None and number(p["contracts"], "contracts") == 0:
                continue
            normalized = self.normalize_position(p)
            if normalized["contracts"] > 0:
                positions.append(normalized)
        return positions

    def normalize_order(self, o, symbol=None) -> ExchangeOrder:
        return {
            "id": str(o["id"]) if o.get("id") is not None else None,
            "clientOrderId": o.get("clientOrderId"),
            "symbol": o.get("symbol") or symbol,
            "side": str(o["side"]).lower() if o.get("side") else None,
            "type": str(o["type"]).lower() if o.get("type") else None,
            "status": o.get("status"),
            "amount": number(o.get("amount"), "order amount", optional=True),
            "filled": number(o.get("filled"), "filled amount", optional=True),
            "average": number(o.get("average"), "average fill", optional=True),
            "price": number(o.get("price"), "order price", optional=True),
            "timestamp": o.get("timestamp"),
            "lastTradeTimestamp": o.get("lastTradeTimestamp"),
            "reduceOnly": flag(o.get("reduceOnly")),
            "stopLossPrice": number(o.get("stopLossPrice"), "stop price", optional=True),
            "triggerPrice": number(o.get("triggerPrice"), "trigger price", optional=True),
        }

    def open_orders(self, symbol=None) -> list[ExchangeOrder]:
        self.require_live_credentials()
        return [self.normalize_order(o, symbol) for o in self.session.fetch_open_orders(symbol)]

    def order_by_client_id(self, symbol, client_id) -> ExchangeOrder:
        raise NotImplementedError(f"{self.KIND} does not support client-ID order lookup")

    def normalize_fill(self, f) -> ExchangeFill:
        return {
            "id": str(f["id"]) if f.get("id") is not None else None,
            "order": f.get("order"),
            "symbol": f["symbol"],
            "side": str(f["side"]).lower(),
            "amount": number(f.get("amount"), "fill quantity"),
            "price": number(f.get("price"), "fill price"),
            "timestamp": int(f["timestamp"]),
            "is_close": None,
            "realized_pnl": None,
        }

    def fills(self, symbol, since) -> list[ExchangeFill]:
        self.require_live_credentials()
        return [
            self.normalize_fill(f) for f in self.session.fetch_my_trades(symbol=symbol, since=since)
        ]

    def normalize_closed_position(self, p) -> ClosedPosition:
        return {
            "id": str(p["id"]) if p.get("id") is not None else None,
            "symbol": p["symbol"],
            "side": p.get("side"),
            "timestamp": p.get("timestamp"),
            "closedTimestamp": p.get("lastUpdateTimestamp"),
            "netPnl": None,
        }

    def position_history(self, symbols=None, since=None) -> list[ClosedPosition]:
        self.require_live_credentials()
        if not self.session.has.get("fetchPositionsHistory"):
            return []
        rows = [
            self.normalize_closed_position(p)
            for p in self.session.fetch_positions_history(symbols=symbols, since=since)
        ]
        return sorted(rows, key=lambda p: p["closedTimestamp"] or p["timestamp"] or 0, reverse=True)

    def order_amount(self, symbol, notional, price):
        market = self.session.market(symbol)
        size = number(market.get("contractSize") or 1, "contract size")
        amount = number(
            self.session.amount_to_precision(symbol, notional / price / size), "order quantity"
        )
        actual = amount * size * price
        if amount <= 0 or actual > notional * (1 + 1e-10):
            raise ValueError("Amount precision rounds beyond the risk budget")
        for name, value in [("amount", amount), ("cost", actual)]:
            bounds = (market.get("limits") or {}).get(name) or {}
            if bounds.get("min") is not None and value < float(bounds["min"]):
                raise ValueError(f"Order below exchange {name} minimum")
            if bounds.get("max") is not None and value > float(bounds["max"]):
                raise ValueError(f"Order above exchange {name} maximum")
        return amount, actual

    def cancel(self, symbol, order_id):
        self.require_live_credentials()
        try:
            self.session.cancel_order(order_id, symbol)
        except ccxt.OrderNotFound:
            pass

    def create_order(
        self,
        symbol,
        side,
        amount,
        type,
        trade_side,
        margin_mode,
        price=None,
        reduce=False,
        take_profit_price=None,
        stop_loss_price=None,
        client_id=None,
    ):
        self.require_live_credentials()
        side = side if isinstance(side, OrderSide) else OrderSide(side)
        params = self.order_params(symbol, side, trade_side, margin_mode, reduce)
        if client_id:
            params["clientOrderId"] = client_id
        if take_profit_price is not None:
            params["takeProfit"] = {"triggerPrice": take_profit_price, **self.trigger_params}
        if stop_loss_price is not None:
            params["stopLoss"] = {"triggerPrice": stop_loss_price, **self.trigger_params}
        try:
            raw = self.session.create_order(
                symbol=symbol, type=type, side=side.value, amount=amount, price=price, params=params
            )
        except ccxt.InsufficientFunds as exc:
            raise InsufficientFunds(str(exc)) from exc
        order = self.normalize_order(raw, symbol)
        order["side"] = (
            side.value
        )  # logical execution direction, independent of venue hedge encoding
        return order

    def create_stop_order(self, symbol, side, amount, trigger_price, client_id=None):
        self.require_live_credentials()
        side = side if isinstance(side, OrderSide) else OrderSide(side)
        params = self.order_params(symbol, side, TradeSide.CLOSE, "isolated", True)
        params.update(stopLossPrice=trigger_price, **self.trigger_params)
        if client_id:
            params["clientOrderId"] = client_id
        order = self.normalize_order(
            self.session.create_order(
                symbol=symbol,
                type="market",
                side=side.value,
                amount=amount,
                price=None,
                params=params,
            ),
            symbol,
        )
        order["side"] = side.value
        return order

    @abc.abstractmethod
    def order_params(self, symbol, side, trade_side, margin_mode, reduce):
        raise NotImplementedError

    @abc.abstractmethod
    def set_margin_mode_and_leverage(self, symbol, margin_mode, leverage):
        raise NotImplementedError

    def fetch_ohlcv_df(
        self,
        symbol: str,
        timeframe: str,
        window: int,
        max_retries: int = MAX_OHLCV_FETCH_RETRIES,
        retry_delay: float = RETRY_DELAY_SECONDS,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data from Bitget and return as a DataFrame with retry logic.

        Args:
            symbol (str): The trading pair or market symbol.
            timeframe (str): The timeframe for OHLCV data (e.g., "1m", "1h").
            window (int): The number of data points to fetch.
            max_retries (int): Maximum number of retry attempts (default: 20).
            retry_delay (float): Constant delay in seconds between retries (default: 5.0).

        Returns:
            pd.DataFrame: A DataFrame with OHLCV data.

        Raises:
            RuntimeError: If all retry attempts fail or session is not initialized.
        """

        for attempt in range(1, max_retries + 1):
            try:
                data = self.session.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=window)

                if not data:
                    logger.warning(
                        f"No OHLCV data fetched for {symbol} (attempt {attempt}/{max_retries})."
                    )
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        return pd.DataFrame()

                columns = ["date", "open", "high", "low", "close", "volume"]
                df = pd.DataFrame(data, columns=columns)

                df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
                df["symbol"] = symbol
                df.set_index("date", inplace=True)

                if attempt > 1:
                    logger.info(
                        f"Successfully fetched OHLCV data for {symbol} after {attempt} attempts"
                    )

                return df

            except Exception as e:
                logger.warning(
                    f"Failed to fetch OHLCV data for {symbol} (attempt {attempt}/{max_retries}): {e}"
                )

                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"Failed to fetch OHLCV data for {symbol} after {max_retries} attempts"
                    )
                    raise RuntimeError(
                        f"Error fetching OHLCV data after {max_retries} retries: {e}"
                    ) from e

        return pd.DataFrame()

    async def fetch_all_symbols_ohlcv_df(
        self, timeframe: str = "1h", ohlcv_window: int = 20
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for all symbols asynchronously, respecting the API rate limit.

        Args:
            timeframe (str): The timeframe for the OHLCV data (e.g., '1h').
            ohlcv_window (int): The window size for fetching OHLCV data.

        Returns:
            pd.DataFrame: A pandas DataFrame containing OHLCV data for all symbols.
        """
        try:
            symbol_list = await self.fetch_all_futures_symbol_names()
        except Exception as e:
            logger.error(f"Failed to fetch symbols list: {e}")
            return pd.DataFrame()

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        loop = asyncio.get_running_loop()

        async def fetch_symbol_ohlcv(sem: asyncio.Semaphore, symbol: str) -> pd.DataFrame | None:
            """
            Fetch OHLCV data for a single symbol asynchronously.
            """
            async with sem:
                try:
                    # logger.debug(f"Fetching OHLCV data for {symbol}")
                    # Run synchronous fetch_ohlcv_df in a thread executor to avoid blocking the loop
                    df = await loop.run_in_executor(
                        None,
                        lambda: self.fetch_ohlcv_df(
                            symbol=symbol,
                            timeframe=timeframe,
                            window=ohlcv_window,
                            max_retries=2,
                            retry_delay=1,
                        ),
                    )

                    if not df.empty and len(df) >= ohlcv_window:
                        return df
                    return None
                except Exception as e:
                    logger.warning(f"Failed to fetch OHLCV data for {symbol}: {e}")
                    return None

        tasks = [fetch_symbol_ohlcv(semaphore, symbol) for symbol in symbol_list]
        ohlcv_data = await asyncio.gather(*tasks)

        valid_dataframes = [df for df in ohlcv_data if df is not None]

        # Calculate failure rate
        total_symbols = len(symbol_list)
        failed_count = total_symbols - len(valid_dataframes)

        if total_symbols > 0 and (failed_count / total_symbols) > 0.1:
            logger.warning(
                f"Failed to fetch OHLCV data for {failed_count} symbols out of {total_symbols} "
                f"({(failed_count / total_symbols) * 100:.1f}% failure rate)"
            )

        if valid_dataframes:
            return pd.concat(valid_dataframes)

        return pd.DataFrame()

    async def fetch_all_futures_symbol_names(self, max_retries: int = MAX_MARKET_FETCH_RETRIES):
        """
        Fetch all futures symbol names from the exchange.

        Args:
            max_retries: Maximum number of retry attempts

        Returns:
            List of futures symbol names

        Raises:
            ExchangeConnectionError: If unable to fetch markets after max retries
        """
        future_symbol_names = []
        retries = 0

        while not future_symbol_names and retries < max_retries:
            try:
                exchange_market = self.session.load_markets(reload=True)
                future_symbol_names = [s for s in exchange_market.keys() if s.endswith(":USDT")]

                if not future_symbol_names:
                    retries += 1
                    logger.warning(f"No futures markets found (attempt {retries}/{max_retries})")
                    if retries < max_retries:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)

            except Exception as e:
                retries += 1
                logger.error(f"Error fetching market info (attempt {retries}/{max_retries}): {e}")
                if retries < max_retries:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    raise ExchangeConnectionError(
                        f"Failed to fetch markets after {max_retries} attempts"
                    ) from e

        if not future_symbol_names:
            raise ExchangeConnectionError(f"No futures markets found after {max_retries} attempts")

        return future_symbol_names
