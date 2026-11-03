"""Pure signal rules of the listing-volume short: universe, timing, volume and reference."""

import math
from statistics import median

from otomai.core.constants import HOUR_MS
from otomai.core.exceptions import OtomaiError
from otomai.core.models import Market
from otomai.core.utils import validate_ohlcv_bar
from otomai.strategies.listing_volume_short.params import ListingVolumeStrategyParams


class ListingDataError(OtomaiError, ValueError):
    """Exchange history cannot define a listing's first trading window."""


def in_universe(market: Market, excluded_bases: tuple[str, ...]) -> bool:
    """Crypto linear USDT perpetuals, matching the research universe."""
    return bool(
        market.get("swap")
        and market.get("linear")
        and market.get("settle") == "USDT"
        and not market.get("tradfi")
        and str(market.get("base") or "").upper() not in excluded_bases
    )


def listing_hour(market: Market) -> int | None:
    """Launch time floored to the UTC hour; None without a millisecond launch time.

    There is no first-candle fallback: truncated history must not become a fake listing.
    """
    launch = market.get("launchTime")
    try:
        launch = int(launch)
    except (TypeError, ValueError):
        return None
    if launch < 1_000_000_000_000:  # require milliseconds, reject guessed units
        return None
    return launch // HOUR_MS * HOUR_MS


def entry_window(listing_ms: int, params: ListingVolumeStrategyParams) -> tuple[int, int, int]:
    """(decision, scheduled entry, entry expiry) timestamps of a listing, in ms."""
    decision = listing_ms + params.decision_hours * HOUR_MS
    scheduled = decision + params.entry_delay_hours * HOUR_MS
    return decision, scheduled, scheduled + params.entry_grace_seconds * 1000


def reject_prelisting_trades(candles, listing_ms: int) -> None:
    """Require the launch hour to be the contract's first traded hour.

    Relaunched or early-started contracts already traded, so their launch-hour
    window is not the first market window the research rule measures. Zero-volume
    placeholder bars before launch are allowed.
    """
    for r in candles:
        if r[0] < listing_ms and len(r) >= 6 and float(r[5]) > 0:
            raise ListingDataError("Contract traded before its launch hour")


def initial_volume(
    candles, listing_ms: int, decision_hours: int, now_ms: int, *, require_positive=True
) -> float:
    """Sum of volume x (open + close) / 2 over the exact first closed hourly bars.

    Missing data is never filled flat. The launch hour's first bar may be partial.
    Duplicate timestamps and incoherent/non-finite OHLCV are rejected. Extra bars
    (including the currently forming bar) never enter the signal. Invalid history
    raises `ListingDataError`; calling before the decision is a scheduling error and
    raises a plain `ValueError`.
    """
    end = listing_ms + decision_hours * HOUR_MS
    if now_ms < end:
        raise ValueError("Decision bars are not all closed")
    window = sorted((r for r in candles if listing_ms <= r[0] < end), key=lambda r: r[0])
    if len(window) != decision_hours:
        raise ListingDataError("Incomplete or duplicate initial candle window")
    total = 0.0
    for i, r in enumerate(window):
        if len(r) < 6 or r[0] != listing_ms + i * HOUR_MS:
            raise ListingDataError("Missing, duplicate or misaligned initial candle")
        try:
            o, _, _, close, volume = validate_ohlcv_bar(r)
        except ValueError as exc:
            raise ListingDataError(str(exc)) from exc
        total += volume * (o + close) / 2
    if not math.isfinite(total) or (require_positive and total <= 0):
        raise ListingDataError("Initial volume must be positive and finite")
    return total


def volume_reference(listings, listing_ms: int, params: ListingVolumeStrategyParams):
    """Median volume of the last `reference_listings` strictly earlier listing hours.

    `listings` have `symbol`, `listing_ms` and `volume`. A missing member of that set is
    never replaced by an older one: None is returned instead. The whole simultaneous
    listing hour is excluded, and boundary ties are resolved by symbol as in the research.
    """
    earlier = sorted(
        (r for r in listings if r.listing_ms < listing_ms),
        key=lambda r: (r.listing_ms, r.symbol),
    )[-params.reference_listings :]
    if len(earlier) < params.min_reference_listings:
        return None
    values = [r.volume for r in earlier]
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return None
    return median(values)
