"""BingX USDT perpetual swaps adapter (one-way mode)."""

import re
import typing as T

import ccxt

from otomai.adapters.exchanges.ccxt import CcxtExchange, first, flag, number
from otomai.core.enums import TradeSide
from otomai.core.exceptions import OrderNotFound

# BingX lists stocks, commodities, FX and indices as USDT perpetuals under these bases,
# e.g. NCSKAAPU2USD, NCCOXPT2USD, NCFXEURSGD2USD, NCSIDXY2USD.
TRADFI_BASE = re.compile(r"NC(?:SK|CO|FX|SI)[A-Z0-9]+|NC[A-Z]{2}[A-Z0-9]*2[A-Z]{3}")


class BingXExchange(CcxtExchange):
    KIND: T.Literal["BingX"] = "BingX"
    default_type: T.Literal["future", "swap"] = "swap"
    # Stops and targets trigger on the last traded price, like the research backtests.
    trigger_params: T.ClassVar[dict] = {"workingType": "CONTRACT_PRICE"}

    def initialize_session(self):
        return ccxt.bingx(self._session_config())

    def normalize_market(self, market):
        normalized = super().normalize_market(market)
        launch = (market.get("info") or {}).get("launchTime")
        try:
            normalized["launchTime"] = int(launch) if int(launch) >= 1_000_000_000_000 else None
        except (TypeError, ValueError):
            normalized["launchTime"] = None
        return normalized

    def is_tradfi_market(self, market):
        return bool(TRADFI_BASE.fullmatch(str(market.get("base") or "")))

    def _balance(self, b):
        balances = (b.get("info") or {}).get("data")
        usdt = next((r for r in (balances or []) if r.get("asset") == "USDT"), None)
        if not usdt or usdt.get("equity") is None:
            raise ValueError("BingX raw USDT equity unavailable; admission is blocked")
        return usdt["equity"], b["USDT"]["free"]

    def normalize_order(self, o, symbol=None):
        info = o.get("info") or {}
        o = {
            **o,
            "clientOrderId": o.get("clientOrderId")
            or first(info, "clientOrderId", "clientOrderID"),
            "reduceOnly": o.get("reduceOnly")
            if o.get("reduceOnly") is not None
            else info.get("reduceOnly"),
            "timestamp": o.get("timestamp") or info.get("time"),
        }
        result = super().normalize_order(o, symbol)
        if result["timestamp"] is not None:
            result["timestamp"] = int(result["timestamp"])
        return result

    def normalize_fill(self, f):
        result = super().normalize_fill(f)
        info = f.get("info") or {}
        result["realized_pnl"] = number(
            first(info, "realizedProfit", "profit"), "realised fill PnL", optional=True
        )
        side = str(info.get("positionSide", "")).lower()
        if side in {"long", "short"}:
            result["is_close"] = (side == "long" and result["side"] == "sell") or (
                side == "short" and result["side"] == "buy"
            )
        elif info.get("reduceOnly") is not None:
            result["is_close"] = flag(info["reduceOnly"])
        return result

    def normalize_closed_position(self, p):
        result = super().normalize_closed_position(p)
        info = p.get("info") or {}
        result.update(
            timestamp=p.get("timestamp") or info.get("openTime"),
            closedTimestamp=info.get("updateTime") or p.get("lastUpdateTimestamp"),
            netPnl=number(info.get("netProfit"), "net position PnL", optional=True),
        )
        for key in ["timestamp", "closedTimestamp"]:
            if result[key] is not None:
                result[key] = int(result[key])
        return result

    def order_params(self, symbol, side, trade_side, margin_mode, reduce):
        return {"positionSide": "BOTH", "reduceOnly": bool(reduce or trade_side == TradeSide.CLOSE)}

    def set_margin_mode_and_leverage(self, symbol, margin_mode, leverage):
        self.require_live_credentials()
        if self.session.fetch_position_mode(symbol).get("hedged") is not False:
            raise ValueError("BingX wrapper requires one-way position mode")
        try:
            self.session.set_margin_mode(margin_mode, symbol)
        except ccxt.MarginModeAlreadySet:
            pass
        self.session.set_leverage(leverage, symbol, {"side": "BOTH"})

    def order_by_client_id(self, symbol, client_id):
        self.require_live_credentials()
        market = self.session.market(symbol)
        try:
            response = self.session.swapV2PrivateGetTradeOrder(
                {"symbol": market["id"], "clientOrderId": client_id}
            )
        except ccxt.OrderNotFound as exc:
            raise OrderNotFound(f"{symbol} has no order {client_id}") from exc
        data = response["data"]
        return self.normalize_order(
            self.session.parse_order(data.get("order", data), market), symbol
        )
