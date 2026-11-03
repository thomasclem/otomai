"""Portfolio admission and entry orders for qualified listings."""

import math
import time

from otomai.core.constants import DAY_MS
from otomai.core.enums import OrderSide, TradeSide
from otomai.core.models import Market
from otomai.core.sizing import batch_notional, executable_bid
from otomai.core.utils import positive_number as positive
from otomai.ports import Exchange
from otomai.strategies.listing_volume_short.lifecycle import MARGIN_MODE, PositionLifecycle
from otomai.strategies.listing_volume_short.params import ListingVolumeRiskParams
from otomai.strategies.listing_volume_short.state import OWNED, Listing, ListingState


class EntryExecution:
    def __init__(
        self,
        exchange: Exchange,
        state: ListingState,
        risk: ListingVolumeRiskParams,
        lifecycle: PositionLifecycle,
    ):
        self.exchange, self.state, self.risk, self.lifecycle = exchange, state, risk, lifecycle

    def _bid(self, symbol: str, notional: float) -> float:
        """Best bid, if the order book can absorb a short of `notional`."""
        bid = executable_bid(
            self.exchange.order_book(symbol),
            notional,
            max_spread_bps=self.risk.max_spread_bps,
            max_slippage_bps=self.risk.max_entry_slippage_bps,
            max_participation=self.risk.max_book_participation,
        )
        return positive(bid, "executable bid")

    def _portfolio(self):
        equity, free = self.exchange.balance()
        if equity <= 0:
            raise ValueError("Portfolio equity is not positive")
        positions = self.exchange.positions()
        if any(
            p.get("notional") is None or not math.isfinite(float(p["notional"])) for p in positions
        ):
            raise ValueError("Missing marked position notional; admission is blocked")
        gross = sum(abs(float(p["notional"])) for p in positions)
        return equity, free, gross, positions

    def admit(self, listings: list[Listing], markets: dict[str, Market], now: int, candidates):
        """Admit the earliest simultaneous batch; later batches wait for fresh positions."""
        if not candidates or any(r.blocks_admission for r in listings):
            return
        # Do not rank by volume or future outcome.
        tm = min(r.listing_ms for r in candidates)
        batch = [r for r in candidates if r.listing_ms == tm]
        equity, free, gross, positions = self._portfolio()
        owned = [r for r in listings if r.status in OWNED]
        cohort = sum(r.notional or 0 for r in owned if r.listing_ms // DAY_MS == tm // DAY_MS)
        notional = batch_notional(
            equity,
            free,
            gross,
            cohort,
            len(batch),
            trade_pct=self.risk.equity_trade_pct,
            max_gross_pct=self.risk.max_gross_exposure_pct,
            max_cohort_pct=self.risk.max_listing_day_pct,
        )
        if len(positions) + len(batch) > self.risk.max_simultaneous_positions or notional <= 0:
            for listing in batch:
                self.state.save(listing, now, status="skipped", reason="Portfolio admission budget")
            return
        # Validate all members before submitting any; skipped shares are not redistributed.
        owned_symbols = {p["symbol"] for p in positions} | {r.symbol for r in owned}
        plans = [p for r in batch if (p := self._plan(r, markets, notional, owned_symbols, now))]
        for listing, budget in plans:
            if not self._submit(listing, budget, now):
                return  # an ambiguous entry reserves the whole request; no further entries

    def _plan(self, listing, markets, notional, owned_symbols, now):
        """Equal allocation, rounded down to exchange precision; None when skipped."""
        try:
            market = markets[listing.symbol]
            if market.get("active") is not True or float(market.get("contractSize") or 1) != 1:
                raise ValueError("Require active unit-sized linear USDT contract")
            if listing.symbol in owned_symbols:
                raise ValueError("Symbol already owned")
            price = self._bid(listing.symbol, notional)
            _, actual = self.exchange.order_amount(listing.symbol, notional, price)
            return listing, actual
        except Exception as exc:
            self.state.save(listing, now, status="skipped", reason=str(exc))
            return None

    @staticmethod
    def _expired(listing: Listing) -> bool:
        return int(time.time() * 1000) > listing.entry_expiry_ms

    def _submit(self, listing: Listing, budget: float, now: int) -> bool:
        """Return False only when the entry outcome is unknown."""
        x, symbol = self.exchange, listing.symbol
        try:
            if self._expired(listing):
                raise ValueError("Entry window passed during admission checks")
            # A leftover reduce-only order could close the new position early.
            if x.open_orders(symbol):
                raise ValueError("Symbol has existing orders")
            x.set_margin_mode_and_leverage(symbol, MARGIN_MODE, 1)
            # Refresh the book after account-setup requests; preserve the allocated budget.
            bid = self._bid(symbol, budget)
            amount, actual = x.order_amount(symbol, budget, bid)
            if self._expired(listing):
                raise ValueError("Entry window passed during account setup")
        except Exception as exc:
            self.state.save(listing, now, status="skipped", reason=str(exc))
            return True
        client_id = listing.order_id_for("e")
        submitted = max(now, int(time.time() * 1000))
        self.state.save(
            listing,
            now,
            status="submitting",
            phase="entry",
            client_id=client_id,
            amount=amount,
            notional=actual,
            quote=bid,
            submitted_ms=submitted,
        )
        try:
            order = x.create_order(
                symbol,
                OrderSide.SELL,
                amount,
                "market",
                TradeSide.OPEN,
                MARGIN_MODE,
                # Bootstrap stop from the quote; replaced at the fill price once confirmed.
                stop_loss_price=bid * (1 + self.risk.stop_loss_pct / 100),
                client_id=client_id,
            )
        except Exception as exc:
            self.lifecycle.mark_uncertain(listing, now, "entry", exc)
            return False
        self.state.save(listing, now, status="entry_pending", order_id=str(order.get("id") or ""))
        return True
