"""Exchange-neutral position monitoring with per-call state and confirmed closure."""

import asyncio
import time
from datetime import UTC, datetime

import pydantic as pdt

from otomai.core import utils
from otomai.core.constants import (
    POSITION_CLOSING_CHECK_INTERVAL,
    POSITION_CLOSING_MAX_TIMEOUT,
    POSITION_OPENING_CHECK_INTERVAL,
    POSITION_OPENING_TIMEOUT,
)
from otomai.core.exceptions import PositionMonitoringError, PositionTimeoutError
from otomai.core.models import Trade
from otomai.logger import Logger
from otomai.ports import Database, Exchange, Notifier

logger = Logger(__name__)


class PositionMonitor(pdt.BaseModel):
    exchange_service: Exchange
    notifier_service: Notifier
    database_service: Database
    strategy_name: str
    model_config = pdt.ConfigDict(arbitrary_types_allowed=True)

    async def monitor_position_opening(self, symbol, order_timeout=POSITION_OPENING_TIMEOUT):
        started = time.monotonic()
        while True:
            try:
                position = await asyncio.to_thread(self.exchange_service.position, symbol)
                if position is not None:
                    await self.notifier_service.send_message(
                        f"{self.strategy_name}: position opened for {symbol}"
                    )
                    return position
                if time.monotonic() - started >= order_timeout:
                    raise PositionTimeoutError(f"Position did not open for {symbol}")
                await asyncio.sleep(POSITION_OPENING_CHECK_INTERVAL)
            except PositionTimeoutError:
                raise
            except Exception as exc:
                raise PositionMonitoringError(f"Cannot monitor opening for {symbol}") from exc

    async def monitor_position_closing(
        self,
        symbol,
        open_date,
        hold_side=None,
        max_timeout=POSITION_CLOSING_MAX_TIMEOUT,
        *,
        open_price=None,
        expected_amount=None,
        position_id=None,
    ):
        started = time.monotonic()
        since = utils.get_ts_in_ms_from_date(open_date)
        collected = {}
        while True:
            try:
                if time.monotonic() - started >= max_timeout:
                    raise PositionTimeoutError(f"Position monitoring timed out for {symbol}")
                fills = await asyncio.to_thread(self.exchange_service.fills, symbol, since)
                required = (
                    "sell" if hold_side == "long" else "buy" if hold_side == "short" else None
                )
                for fill in fills:
                    if fill["symbol"] != symbol or fill["timestamp"] < since:
                        continue
                    if fill["is_close"] is False or (required and fill["side"] != required):
                        continue
                    if required is None and fill["is_close"] is not True:
                        continue
                    key = fill["id"] or (
                        fill["order"],
                        fill["timestamp"],
                        fill["amount"],
                        fill["price"],
                        fill["side"],
                    )
                    collected[key] = fill
                position = await asyncio.to_thread(
                    self.exchange_service.position, symbol, hold_side
                )
                # A closing fill can be partial, and its realised PnL can be exactly zero.
                # Neither a nonzero PnL nor the first opposite-side fill proves closure.
                amount = sum(f["amount"] for f in collected.values())
                complete = (
                    expected_amount is None
                    or amount + max(1e-10, expected_amount * 1e-6) >= expected_amount
                )
                if position is None and collected and complete:
                    ordered = sorted(collected.values(), key=lambda f: f["timestamp"])
                    close_ms = ordered[-1]["timestamp"]
                    price = sum(f["amount"] * f["price"] for f in ordered) / amount
                    history = await asyncio.to_thread(
                        self.exchange_service.position_history, [symbol], since
                    )
                    matched = []
                    for result in history:
                        if result["symbol"] != symbol or (
                            hold_side and result["side"] != hold_side
                        ):
                            continue
                        if result["timestamp"] is None or int(result["timestamp"]) < since:
                            continue
                        if (
                            result["closedTimestamp"] is None
                            or int(result["closedTimestamp"]) < close_ms
                        ):
                            continue
                        if position_id and result["id"] != position_id:
                            continue
                        matched.append(result)
                    net = matched[0]["netPnl"] if len(matched) == 1 else None
                    # A true net value is used only if the exchange reports it for this
                    # position, including its fees/funding. Unknown is never manufactured.
                    trade = Trade(
                        symbol=symbol,
                        net_profit=str(net) if net is not None else None,
                        open_price=str(open_price) if open_price is not None else "",
                        close_price=str(price),
                        hold_side=hold_side or "",
                        open_date=open_date,
                        close_date=datetime.fromtimestamp(close_ms / 1000, UTC).isoformat(),
                        amount=str(amount),
                        strategy=self.strategy_name,
                    )
                    self.database_service.insert_trade(trade)
                    await self.notifier_service.send_message(
                        f"{self.strategy_name}: position closed for {symbol}; net P&L: {net if net is not None else 'not yet confirmed'}"
                    )
                    return
                await asyncio.sleep(POSITION_CLOSING_CHECK_INTERVAL)
            except (PositionMonitoringError, PositionTimeoutError):
                raise
            except Exception as exc:
                raise PositionMonitoringError(f"Cannot monitor closure for {symbol}") from exc

    async def monitor_position(
        self,
        symbol,
        open_date,
        opening_timeout=POSITION_OPENING_TIMEOUT,
        closing_max_timeout=POSITION_CLOSING_MAX_TIMEOUT,
    ):
        position = await self.monitor_position_opening(symbol, opening_timeout)
        await self.monitor_position_closing(
            symbol,
            open_date,
            hold_side=position["side"],
            max_timeout=closing_max_timeout,
            open_price=position["entryPrice"],
            expected_amount=position["contracts"],
            position_id=position["id"],
        )
