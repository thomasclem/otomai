"""Open-position management on a dedicated exchange (sub)account.

The exchange is the source of truth: every short position and order on the account
belongs to this strategy. The state caches listing keys, client IDs and fill times,
and keeps the durable entry intent: an ambiguous entry is never resubmitted, because
it could add exposure. Reduce-only protection and closes cannot add exposure, so an
ambiguous one is replaced by a fresh attempt instead of waiting for an operator.
"""

from otomai.core.constants import HOUR_MS
from otomai.core.enums import OrderSide, TradeSide
from otomai.core.exceptions import OrderNotFound
from otomai.core.utils import positive_number as positive
from otomai.logger import Logger
from otomai.ports import Exchange
from otomai.strategies.listing_volume_short.params import ListingVolumeRiskParams
from otomai.strategies.listing_volume_short.state import (
    ENTRY,
    OWNED,
    Listing,
    ListingState,
)

logger = Logger(__name__)

TERMINAL = {"closed", "canceled", "rejected", "expired"}  # order statuses
MARGIN_MODE = "isolated"


class PositionLifecycle:
    def __init__(
        self,
        exchange: Exchange,
        state: ListingState,
        risk: ListingVolumeRiskParams,
        holding_hours: int,
    ):
        self.exchange, self.state, self.risk = exchange, state, risk
        self.holding_hours = holding_hours

    def mark_uncertain(self, listing: Listing, now: int, phase: str, exc) -> None:
        self.state.save(listing, now, status="uncertain", phase=phase, error=str(exc))
        logger.error(f"Unresolved {phase} for {listing.symbol}: {exc}")

    @staticmethod
    def _attempt_id(listing: Listing, kind: str, now: int) -> str:
        """Fresh client ID per reduce-only attempt, so retries never reuse an ID."""
        return listing.order_id_for(f"{kind}{now // 1000:x}")

    def reconcile(self, listings: list[Listing], positions, now: int) -> None:
        shorts = {}
        for p in positions:
            if p.get("side") == "short":
                shorts[p["symbol"]] = p
            else:
                logger.error(f"Ignoring {p.get('side')} position on {p['symbol']}: short-only")
        owned = {r.symbol: r for r in listings if r.status in OWNED}
        for symbol in shorts.keys() - owned.keys():
            listing = self._adopt(listings, symbol, now)
            if listing is not None:
                owned[symbol] = listing
        for symbol, listing in owned.items():
            phase = listing.phase or "entry"
            try:
                self._reconcile(listing, shorts.get(symbol), now)
            except Exception as exc:
                self.mark_uncertain(listing, now, listing.phase or phase, exc)

    def _reconcile(self, listing: Listing, position, now: int) -> None:
        if listing.status in ENTRY or (listing.phase or "entry") == "entry":
            if not self._confirm_entry(listing, now):
                return
        if position is None:
            self._finish(listing, now)  # stop, target or close filled
        elif now >= listing.deadline_ms:
            self._close(listing, position, now)
        else:
            self._protect(listing, position, now)

    def _confirm_entry(self, listing: Listing, now: int) -> bool:
        """Resolve the entry by its client ID; OrderNotFound never authorizes a resubmission."""
        order = self.exchange.order_by_client_id(listing.symbol, listing.client_id)
        if order.get("status") not in TERMINAL:
            # Cancel any unfilled market-order remainder rather than sizing from an assumed fill.
            if order.get("id"):
                self.exchange.cancel(listing.symbol, str(order["id"]))
            self.state.save(listing, now, status="entry_pending")
            return False
        if float(order.get("filled") or 0) == 0:
            self.state.save(listing, now, status="rejected", reason="Entry not filled")
            return False
        self._record_fill(listing, order, now)
        return True

    def _record_fill(self, listing: Listing, order, now: int) -> None:
        entry = positive(order.get("average"), "confirmed average fill")
        filled = positive(order.get("filled"), "confirmed filled amount")
        stamp = order.get("lastTradeTimestamp") or order.get("timestamp")
        if stamp is None:
            raise ValueError("Entry fill time unavailable; deadline unknown")
        self.state.save(
            listing,
            now,
            status="open",
            phase="open",
            entry=entry,
            amount=filled,
            notional=filled * entry,
            entry_ms=int(stamp),
            deadline_ms=int(stamp) + self.holding_hours * HOUR_MS,
        )

    def _adopt(self, listings: list[Listing], symbol: str, now: int) -> Listing | None:
        """Rebuild a missing record from the listing key's deterministic entry ID."""
        candidates = [r for r in listings if r.symbol == symbol]
        if not candidates:
            logger.warning(f"Short on {symbol} not yet matched to a discovered listing")
            return None
        listing = max(candidates, key=lambda r: r.listing_ms)
        client_id = listing.client_id or listing.order_id_for("e")
        try:
            order = self.exchange.order_by_client_id(symbol, client_id)
            if order.get("status") not in TERMINAL or not float(order.get("filled") or 0):
                raise ValueError("Entry order is not a completed fill")
            self.state.save(listing, now, client_id=client_id, adopted_ms=now)
            self._record_fill(listing, order, now)
        except Exception as exc:
            logger.error(f"Short on {symbol} has no matching entry order; not managed: {exc}")
            return None
        return listing

    def _finish(self, listing: Listing, now: int) -> None:
        # Dedicated account: every order left on the symbol is a leftover of this trade.
        for order in self.exchange.open_orders(listing.symbol):
            if order.get("id"):
                self.exchange.cancel(listing.symbol, str(order["id"]))
        self.state.save(listing, now, status="closed", closed_ms=now)

    def _protect(self, listing: Listing, position, now: int) -> None:
        """Keep exactly one stop and one target; replace them when either is missing."""
        x, symbol = self.exchange, listing.symbol
        orders = x.open_orders(symbol)
        current = {listing.stop_client_id, listing.target_client_id} - {None}
        if len(current) < 2 or not current <= {o.get("clientOrderId") for o in orders}:
            stop_id, target_id = (
                self._attempt_id(listing, "s", now),
                self._attempt_id(listing, "t", now),
            )
            # Persist the attempt first, so a restart knows which orders are current.
            self.state.save(
                listing,
                now,
                status="uncertain",
                phase="protection",
                stop_client_id=stop_id,
                target_client_id=target_id,
            )
            amount = position["contracts"]
            x.create_stop_order(
                symbol,
                OrderSide.BUY,
                amount,
                listing.entry * (1 + self.risk.stop_loss_pct / 100),
                client_id=stop_id,
            )
            x.create_order(
                symbol,
                OrderSide.BUY,
                amount,
                "limit",
                TradeSide.CLOSE,
                MARGIN_MODE,
                price=listing.entry * (1 - self.risk.take_profit_pct / 100),
                reduce=True,
                client_id=target_id,
            )
            current = {stop_id, target_id}
        # Cancel only after the replacement is acknowledged: the stop attached to the entry
        # and any earlier attempt keep protecting the position until then.
        for order in orders:
            if order.get("clientOrderId") not in current and order.get("id"):
                x.cancel(symbol, str(order["id"]))
        if listing.status != "open":
            self.state.save(listing, now, status="open", phase="open")

    def _close(self, listing: Listing, position, now: int) -> None:
        x, symbol = self.exchange, listing.symbol
        if listing.close_client_id:
            try:
                if (
                    x.order_by_client_id(symbol, listing.close_client_id).get("status")
                    not in TERMINAL
                ):
                    return  # the earlier close is still working
            except OrderNotFound:
                pass  # never reached the venue; a reduce-only retry cannot add exposure
        client_id = self._attempt_id(listing, "c", now)
        self.state.save(listing, now, status="closing", phase="close", close_client_id=client_id)
        x.create_order(
            symbol,
            OrderSide.BUY,
            position["contracts"],
            "market",
            TradeSide.CLOSE,
            MARGIN_MODE,
            reduce=True,
            client_id=client_id,
        )
