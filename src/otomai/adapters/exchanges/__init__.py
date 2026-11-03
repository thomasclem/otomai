from otomai.adapters.exchanges.bingx import BingXExchange
from otomai.adapters.exchanges.bitget import BitgetExchange
from otomai.adapters.exchanges.ccxt import CcxtExchange

ExchangeKind = BitgetExchange | BingXExchange

__all__ = ["BingXExchange", "BitgetExchange", "CcxtExchange", "ExchangeKind"]
