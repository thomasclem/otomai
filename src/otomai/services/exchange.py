import abc
import asyncio
import os
import typing as T

import ccxt
import pydantic as pdt
from ccxt import bitget
import pandas as pd
from dotenv import load_dotenv

from otomai.core.enums import OrderSide, TradeSide, OrderMarginMode
from otomai.logger import Logger

logger = Logger(__name__)


class Exchange(abc.ABC, pdt.BaseModel):
    """
    Abstract Base Client for any exchange or service.
    """

    KIND: str  # Used to identify the type of client (e.g., "bitget", "binance")
    apiKey: T.Optional[T.Union[str, bytes]] = None
    secret: T.Optional[T.Union[str, bytes]] = None
    password: T.Optional[T.Union[str, bytes]] = None
    auth_object: T.Optional[T.Dict[str, T.Any]] = None
    default_type: T.Literal["future", "swap"] = "futures"

    def __init__(self, **kwargs):
        """
        Initialize the base exchange client.
        """
        super().__init__(**kwargs)

        load_dotenv(dotenv_path=f"{os.getenv('ENV', 'dev')}.env")

        self.auth_object = self.auth_object or {}
        self.auth_object["apiKey"] = self.apiKey or os.getenv(
            f"{self.KIND.upper()}_API_KEY"
        )
        self.auth_object["secret"] = self.secret or os.getenv(
            f"{self.KIND.upper()}_SECRET"
        )
        self.auth_object["password"] = self.password or os.getenv(
            f"{self.KIND.upper()}_PASSWORD"
        )
        self.auth_object["options"] = {"defaultType": self.default_type}

        self._auth = all(
            self.auth_object.get(key) for key in ["apiKey", "secret", "password"]
        )
        if not self._auth:
            raise ValueError(
                f"Missing credentials for {self.KIND} exchange. Check environment variables or input."
            )

        self._session = self.initialize_session()

    @abc.abstractmethod
    def initialize_session(self):
        """
        Initialize the session for the client.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement `initialize_session`.")

    @abc.abstractmethod
    def load_markets(self):
        """
        Load markets for the exchange.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement `load_markets`.")

    def is_authenticated(self) -> bool:
        """
        Check if the client is authenticated.
        """
        return self._auth

    @property
    def session(self):
        return self._session


class BitgetExchange(Exchange):
    KIND: T.Literal["Bitget"] = "Bitget"

    def initialize_session(self):
        """
        Initialize the Bitget session using authentication data.
        """
        try:
            if self._auth:
                logger.info("Initializing authenticated Bitget session.")
                return bitget(self.auth_object)
            else:
                logger.info("Initializing unauthenticated Bitget session.")
                return bitget()
        except Exception as e:
            logger.error(f"Failed to initialize Bitget session: {e}")
            raise

    def load_markets(self):
        """
        Load market data from Bitget.
        """
        try:
            if self._session is None:
                raise RuntimeError("Session is not initialized.")
            self._session.load_markets()
            logger.info("Markets loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            raise RuntimeError(f"Failed to load markets: {e}")

    def fetch_ohlcv_df(self, symbol: str, timeframe: str, window: int) -> pd.DataFrame:
        """
        Fetch OHLCV data from Bitget and return as a DataFrame.

        Args:
            symbol (str): The trading pair or market symbol.
            timeframe (str): The timeframe for OHLCV data (e.g., "1m", "1h").
            window (int): The number of data points to fetch.

        Returns:
            pd.DataFrame: A DataFrame with OHLCV data.
        """
        try:
            if self._session is None:
                raise RuntimeError("Session is not initialized.")

            data = self._session.fetch_ohlcv(
                symbol=symbol, timeframe=timeframe, limit=window
            )
            if not data:
                logger.warning("No OHLCV data fetched.")
                return pd.DataFrame()

            columns = ["date", "open", "high", "low", "close", "volume"]
            df = pd.DataFrame(data, columns=columns)

            df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
            df["symbol"] = symbol
            df.set_index("date", inplace=True)
            return df

        except Exception as e:
            logger.error(f"Failed to fetch OHLCV data for {symbol}: {e}")
            raise RuntimeError(f"Error fetching OHLCV data: {e}")

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        type: str,
        trade_side: TradeSide,
        margin_mode: str,
        price: T.Optional[float] = None,
        reduce: T.Optional[bool] = False,
        take_profit_price: T.Optional[float] = None,
        stop_loss_price: T.Optional[float] = None,
    ) -> T.Dict:
        try:
            logger.info(
                f"Trying to open position for: {symbol}, amount: {amount}, price: {price}"
            )
            params = {
                "reduceOnly": reduce,
                "tradeSide": trade_side.value,
                "marginMode": margin_mode,
                "productType": "UMCBL",
            }

            if take_profit_price is not None:
                params.update({"takeProfit": {"triggerPrice": take_profit_price}})

            if stop_loss_price is not None:
                params.update({"stopLoss": {"triggerPrice": stop_loss_price}})

            return self._session.create_order(
                symbol=symbol,
                type=type,
                side=side.value,
                amount=amount,
                price=price,
                params=params,
            )
        except ccxt.ExchangeError as e:
            logger.error(f"ExchangeError occurred: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise

    def set_margin_mode_and_leverage(
        self, symbol: str, margin_mode: str, leverage: int
    ):
        try:
            self._session.set_margin_mode(
                marginMode=margin_mode,
                symbol=symbol,
                params={"productType": "UMCBL", "marginCoin": "USDT"},
            )
            logger.info(f"Margin mode set to {margin_mode} for {symbol}")
        except Exception as e:
            logger.error(f"Error setting margin mode for {symbol}: {e}")
        try:
            if margin_mode == OrderMarginMode.ISOLATED.value:
                self._session.set_leverage(
                    leverage=leverage,
                    symbol=symbol,
                    params={
                        "productType": "UMCBL",
                        "holdSide": "long",
                    },
                )
                self._session.set_leverage(
                    leverage=leverage,
                    symbol=symbol,
                    params={
                        "productType": "UMCBL",
                        "holdSide": "short",
                    },
                )
                leverage = self._session.fetch_leverage(symbol=symbol)
                assert leverage["shortLeverage"] == leverage

            else:
                self._session.set_leverage(
                    leverage=leverage,
                    symbol=symbol,
                    params={"productType": "UMCBL", "marginCoin": "USDT"},
                )
            logger.info(f"Leverage set to {leverage} for {symbol}")
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")

    async def fetch_all_symbols_ohlcv(
        self, timeframe="1h", ohlcv_window=20
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for all symbols asynchronously, respecting the API rate limit.

        Args:
            timeframe (str): The timeframe for the OHLCV data (e.g., '1h').
            ohlcv_window (int): The window size for fetching OHLCV data.

        Returns:
            pd.DataFrame: A pandas DataFrame containing OHLCV data for all symbols.
        """
        symbol_list = self.fetch_all_symbol_names()
        semaphore = asyncio.Semaphore(20)

        async def fetch_symbol_ohlcv(semaphore, symbol: str):
            """
            Fetch OHLCV data for a single symbol asynchronously.

            Args:
                semaphore (asyncio.Semaphore): A semaphore to control the rate limit.
                symbol (str): The trading symbol.

            Returns:
                pd.DataFrame: A pandas DataFrame containing OHLCV data for the symbol, or None if data is not available.
            """
            async with semaphore:
                try:
                    data = self.fetch_ohlcv_df(
                        symbol=symbol, timeframe=timeframe, window=ohlcv_window
                    )
                    if data.shape[0] >= ohlcv_window:
                        return data
                    else:
                        return None
                except Exception as e:
                    logger.error(f"Failed to fetch data for {symbol}: {e}")
                    return None

        tasks = [fetch_symbol_ohlcv(semaphore, symbol) for symbol in symbol_list]
        ohlcv_data = await asyncio.gather(*tasks)

        valid_dataframes = [df for df in ohlcv_data if df is not None]
        failed_symbols_count = len(symbol_list) - len(valid_dataframes)

        if failed_symbols_count / len(symbol_list) > 0.1:
            logger.error(
                f"Failed to fetch OHLCV data for {failed_symbols_count} symbols out of {len(symbol_list)}"
            )

        if valid_dataframes:
            return pd.concat(valid_dataframes)

        return pd.DataFrame()

    def fetch_free_amount_in_balance(self) -> float:
        balance = self._session.fetch_balance()
        return balance["USDT"]["free"]

    def fetch_all_symbol_names(self) -> T.List[str]:
        try:
            tickers = self._session.fetch_tickers()
            return list(tickers.keys())
        except Exception as e:
            logger.error(f"Error fetching symbol names: {e}")
            return []
