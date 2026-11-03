"""Bitget USDT-futures adapter (hedge mode)."""

import typing as T

import ccxt
from ccxt import bitget

from otomai.adapters.exchanges.ccxt import CcxtExchange, first, number
from otomai.core.enums import TradeSide

# Default product type and margin coin of Bitget USDT futures
BITGET_PRODUCT_TYPE = "USDT-FUTURES"
BITGET_MARGIN_COIN = "USDT"


class BitgetExchange(CcxtExchange):
    KIND: T.Literal["Bitget"] = "Bitget"
    default_type: T.Literal["future", "swap"] = "future"
    hedged: bool = True  # matches the existing strategies' long/short leverage setup

    def initialize_session(self):
        return bitget(self._session_config())

    def _balance(self, b):
        raw = b.get("info") or []
        if isinstance(raw, dict):
            raw = raw.get("data", raw)
        if isinstance(raw, dict):
            raw = [raw]
        account = next((r for r in raw if r.get("marginCoin") == "USDT"), None)
        if account:
            return first(account, "accountEquity", "usdtEquity"), first(
                account, "available", "crossedMaxAvailable", "maxTransferOut"
            )
        return super()._balance(b)

    def ticker_price(self, symbol):
        ticker = self.session.fetch_ticker(symbol=symbol)
        price = number(ticker.get("last") or (ticker.get("info") or {}).get("lastPr"), "last price")
        if price <= 0:
            raise ValueError("Invalid last price")
        return price

    def normalize_position(self, p):
        info = p.get("info") or {}
        p = {
            **p,
            "contracts": first(p, "contracts")
            if p.get("contracts") is not None
            else first(info, "total", "size"),
            "side": p.get("side") or first(info, "holdSide", "posSide"),
            "entryPrice": first(p, "entryPrice")
            if p.get("entryPrice") is not None
            else first(info, "openPriceAvg", "openAvgPrice"),
        }
        return super().normalize_position(p)

    def normalize_order(self, o, symbol=None):
        info = o.get("info") or {}
        o = {
            **o,
            "clientOrderId": o.get("clientOrderId") or info.get("clientOid"),
            "timestamp": o.get("timestamp") or first(info, "cTime", "ctime"),
            "reduceOnly": o.get("reduceOnly")
            if o.get("reduceOnly") is not None
            else info.get("reduceOnly"),
        }
        result = super().normalize_order(o, symbol)
        if str(info.get("tradeSide", "")).lower() == "close" or info.get("planType") in {
            "pos_loss",
            "pos_profit",
            "loss_plan",
            "profit_plan",
        }:
            result["reduceOnly"] = True
        if result["timestamp"] is not None:
            result["timestamp"] = int(result["timestamp"])
        if str(info.get("tradeSide", "")).lower() == "close" and self.hedged and result["side"]:
            result["side"] = "sell" if result["side"] == "buy" else "buy"
        return result

    def open_orders(self, symbol=None):
        self.require_live_credentials()
        streams = [self.session.fetch_open_orders(symbol)]
        for plan_type in ["normal_plan", "profit_loss", "track_plan"]:
            streams.append(
                self.session.fetch_open_orders(
                    symbol, params={"trigger": True, "planType": plan_type}
                )
            )
        orders = {}
        for stream in streams:
            for raw in stream:
                order = self.normalize_order(raw, symbol)
                if order["id"] is None:
                    raise ValueError("Bitget open order has no stable identifier")
                orders[order["id"]] = order
        return list(orders.values())

    def normalize_fill(self, f):
        result = super().normalize_fill(f)
        info = f.get("info") or {}
        trade_side = str(info.get("tradeSide", "")).lower()
        result["is_close"] = (
            True if trade_side == "close" else False if trade_side == "open" else None
        )
        if (
            result["is_close"]
            and str(info.get("posMode", "hedge_mode" if self.hedged else "")).lower()
            == "hedge_mode"
        ):
            result["side"] = "sell" if result["side"] == "buy" else "buy"
        result["realized_pnl"] = number(
            first(info, "profit", "pnl"), "realised fill PnL", optional=True
        )
        return result

    def normalize_closed_position(self, p):
        result = super().normalize_closed_position(p)
        info = p.get("info") or {}
        result.update(
            timestamp=p.get("timestamp") or first(info, "ctime", "cTime", "createdTime"),
            closedTimestamp=first(info, "utime", "uTime", "updatedTime")
            or p.get("lastUpdateTimestamp"),
            netPnl=number(info.get("netProfit"), "net position PnL", optional=True),
        )
        for key in ["timestamp", "closedTimestamp"]:
            if result[key] is not None:
                result[key] = int(result[key])
        return result

    def order_params(self, symbol, side, trade_side, margin_mode, reduce):
        # CCXT maps logical buy/sell to Bitget's position-direction side in hedge
        # mode when hedged+reduceOnly are set. Never forward a contradictory tradeSide.
        return {
            "reduceOnly": bool(reduce or trade_side == TradeSide.CLOSE),
            "hedged": self.hedged,
            "marginMode": margin_mode,
            "productType": BITGET_PRODUCT_TYPE,
        }

    def set_margin_mode_and_leverage(self, symbol, margin_mode, leverage):
        self.require_live_credentials()
        try:
            self.session.set_margin_mode(
                marginMode=margin_mode,
                symbol=symbol,
                params={"productType": BITGET_PRODUCT_TYPE, "marginCoin": BITGET_MARGIN_COIN},
            )
        except ccxt.MarginModeAlreadySet:
            pass
        sides = ["long", "short"] if self.hedged and margin_mode == "isolated" else [None]
        for side in sides:
            params = {"productType": BITGET_PRODUCT_TYPE, "marginCoin": BITGET_MARGIN_COIN}
            if side:
                params["holdSide"] = side
            self.session.set_leverage(leverage=leverage, symbol=symbol, params=params)
