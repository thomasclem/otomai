"""Listing discovery and signals, composed with the entry and position services."""

import asyncio
import threading
import time
import typing as T

import pydantic as pdt

from otomai.adapters import BingXExchange
from otomai.core.constants import HOUR_MS
from otomai.logger import Logger
from otomai.strategies.base import Strategy
from otomai.strategies.listing_volume_short.execution import EntryExecution
from otomai.strategies.listing_volume_short.lifecycle import PositionLifecycle
from otomai.strategies.listing_volume_short.params import (
    ListingVolumeRiskParams,
    ListingVolumeStrategyParams,
)
from otomai.strategies.listing_volume_short.signal import (
    ListingDataError,
    entry_window,
    in_universe,
    initial_volume,
    listing_hour,
    reject_prelisting_trades,
    volume_reference,
)
from otomai.strategies.listing_volume_short.state import Listing, ListingState

logger = Logger(__name__)

VOLUME_RETRY_MS = 60_000


class ListingVolumeShortStrategy(Strategy):
    KIND: T.Literal["ListingVolumeShortStrategy"] = "ListingVolumeShortStrategy"
    strategy_params: ListingVolumeStrategyParams = pdt.Field(
        default_factory=ListingVolumeStrategyParams
    )
    trading_params: ListingVolumeRiskParams = pdt.Field(default_factory=ListingVolumeRiskParams)
    # Client-ID order lookup is what makes restarts safe; only the BingX adapter has it.
    exchange_service: BingXExchange = pdt.Field(default_factory=BingXExchange)
    _state: T.Any = pdt.PrivateAttr(default=None)
    _last_summary: T.Any = pdt.PrivateAttr(default=None)
    _cycle_lock: T.Any = pdt.PrivateAttr(default_factory=threading.Lock)
    _lifecycle: T.Any = pdt.PrivateAttr(default=None)
    _execution: T.Any = pdt.PrivateAttr(default=None)

    def __enter__(self):
        self._ensure_state()
        return self

    def __exit__(self, *args):
        if self._state:
            self._state.close()
            self._state = None

    def _ensure_state(self):
        if self._state is not None:
            return
        p, x = self.strategy_params, self.exchange_service
        x.require_live_credentials()
        # Freeze all signal, execution and risk choices against silent restart drift.
        identity = p.model_dump(exclude={"state_path", "poll_seconds", "history_batch_size"})
        identity["risk"] = self.trading_params.model_dump()
        identity["account_fingerprint"] = x.account_fingerprint()
        self._state = ListingState(p.state_path, identity)
        self._lifecycle = PositionLifecycle(x, self._state, self.trading_params, p.holding_hours)
        self._execution = EntryExecution(x, self._state, self.trading_params, self._lifecycle)

    # %% SIGNAL

    def _discover(self, markets):
        for symbol, market in markets.items():
            if not in_universe(market, self.strategy_params.excluded_bases):
                continue
            hour = listing_hour(market)
            if hour is not None:
                self._state.discover(symbol, hour)

    def _load_volumes(self, listings: list[Listing], now: int):
        """Backfill first-window volumes, newest first, a batch per cycle."""
        p = self.strategy_params
        completed = [
            r for r in listings if not r.excluded and entry_window(r.listing_ms, p)[0] <= now
        ]
        missing = [
            r
            for r in completed[-p.bootstrap_listings :]
            if r.volume is None and r.volume_retry_after_ms <= now
        ]
        for listing in list(reversed(missing))[: p.history_batch_size]:
            try:
                candles = self.exchange_service.candles(
                    listing.symbol,
                    "1h",
                    since=listing.listing_ms - p.prelisting_lookback_hours * HOUR_MS,
                    until=entry_window(listing.listing_ms, p)[0] - 1,
                    limit=p.prelisting_lookback_hours + p.decision_hours,
                )
                reject_prelisting_trades(candles, listing.listing_ms)
                volume = initial_volume(candles, listing.listing_ms, p.decision_hours, now)
                self._state.save(listing, now, volume=volume)
            except ListingDataError as exc:
                # The last bars can lag at the decision; after the entry window the history
                # is final. Like the research sample, a listing without a valid first window
                # then leaves the universe instead of blocking the next references.
                if now > entry_window(listing.listing_ms, p)[1]:
                    status = "excluded" if listing.status == "observing" else listing.status
                    self._state.save(listing, now, status=status, excluded_reason=str(exc))
                else:
                    self._retry_volume(listing, now, exc)
            except Exception as exc:
                # Transient failures keep the missing reference in its real place.
                self._retry_volume(listing, now, exc)

    def _retry_volume(self, listing: Listing, now: int, exc):
        self._state.save(
            listing, now, volume_error=str(exc), volume_retry_after_ms=now + VOLUME_RETRY_MS
        )

    def _classify(self, listings: list[Listing], now: int):
        p = self.strategy_params
        universe = [r for r in listings if not r.excluded]
        for listing in listings:
            if listing.status not in {"observing", "qualified"}:
                continue
            decision, expiry = entry_window(listing.listing_ms, p)
            if now > expiry:
                self._state.save(listing, now, status="expired", reason="Entry window passed")
                continue
            if now < decision or listing.volume is None or listing.status == "qualified":
                continue
            ref = volume_reference(universe, listing.listing_ms, p)
            if ref is None:
                continue
            self._state.save(
                listing,
                now,
                status="qualified" if listing.volume > p.volume_multiplier * ref else "no_signal",
                reference=ref,
                entry_expiry_ms=expiry,
                volume_ratio=listing.volume / ref,
            )

    # %% CYCLE

    def cycle(self, now_ms=None):
        with self._cycle_lock:
            return self._cycle(now_ms)

    def _cycle(self, now_ms=None):
        self._ensure_state()
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        # Existing positions and elapsed deadlines take priority over signal discovery.
        self._lifecycle.reconcile(self._state.rows(), self.exchange_service.positions(), now)
        markets = self.exchange_service.markets()
        self._discover(markets)
        listings = self._state.rows()
        self._load_volumes(listings, now)
        self._classify(listings, now)
        # Qualification happens at or after the decision, so qualified listings are due.
        candidates = [r for r in listings if r.status == "qualified"]
        self._execution.admit(listings, markets, now, candidates)
        statuses = {}
        for listing in listings:
            statuses[listing.status] = statuses.get(listing.status, 0) + 1
        summary = {"states": statuses}
        logger.info(str(summary))
        return summary

    async def run_once(self):
        """One cycle in a worker thread, then a notification when the summary changed."""
        self._ensure_state()
        task = asyncio.create_task(asyncio.to_thread(self.cycle))
        try:
            summary = await asyncio.shield(task)
        except asyncio.CancelledError:
            # A worker may be inside an exchange POST. Finish its durable bookkeeping
            # before the context manager closes the SQLite connection.
            await task
            raise
        if summary != self._last_summary:
            await self.notifier_service.send_message(f"{self.strategy_params.name}: {summary}")
            self._last_summary = summary
        return summary

    async def run(self):
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logger.exception(f"Listing-volume cycle failed: {exc}")
            await asyncio.sleep(self.strategy_params.poll_seconds)
