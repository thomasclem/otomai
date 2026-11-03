# Listing-volume short on BingX

This is the runtime counterpart of `backtest/strategies/listing_volume_short_challenger.ipynb`.
Notebooks remain local research artifacts, ignored by Git. The Python signal,
runtime, adapter, state store and tests are tracked. The checked-in configurations
trade live; installing this change does not start a bot or submit orders.

## Run

From the repository root:

```bash
uv sync
uv run otomai --files conf/dev/listing_volume_short.yml --check-config
uv run otomai --files conf/dev/listing_volume_short.yml
```

Export `BINGX_API_KEY` and `BINGX_SECRET` of the environment's sub-account first;
`--check-config` needs no credentials. The first cycles only bootstrap the volume
reference, so start before the listings you want to trade. The bot must run
continuously: deadline exits happen on its polls. The console notifier reports
changes in state counts; normal logs summarize each poll.

## Default rule

| Component | Rule |
|---|---|
| Universe | Active BingX linear USDT-settled crypto swaps, unit contract size, exchange `launchTime` in milliseconds; TradFi contracts (stocks, commodities, FX, indices) and `excluded_bases` (PAXG, XAUT) are never discovered |
| Listing hour L | Launch timestamp floored to UTC hour; the first candle can be partial. A contract with traded bars in the 24 hours before L (relaunch or early start) is excluded |
| Decision | L + 4 hours; exactly four contiguous, valid, closed hourly candles |
| Volume proxy | Sum of base volume × (open + close) / 2 |
| Reference | Median of the last 30 strictly earlier listing hours; minimum 10 during warmup |
| Tied boundary | Sort by listing hour then symbol, matching the research notebook |
| Signal | Volume strictly greater than 2 × reference median |
| Entry | First eligible quote at/after L + 4 hours; no extra hour of delay; at most 120 seconds scheduling grace |
| Direction / margin | Short, isolated, 1×; size means notional, not margin |
| Stop | Stop-market at actual average fill × 1.20 |
| Target | Reduce-only limit buy at actual average fill × 0.40 |
| Deadline | Actual entry fill time + 504 hours, persisted across restarts |
| Size | Up to 5% of current equity as entry notional |
| Admission caps | 30% marked gross exposure, 10% entry notional per UTC listing day, 6 positions |
| Liquidity gates | Spread ≤50bp; order ≤1% of visible bid depth within 50bp of best bid |

Simultaneous candidates split the available budget equally. Failed members' shares
are not redistributed. Skip the entire batch if it exceeds the position-slot limit.
Caps apply on admission; later price/equity changes can exceed them. Quantities round
down to exchange precision, and exchange amount/cost limits are checked.

Entry is due at the decision, with no extra delay. The worker polls
every 30 seconds: it needs four confirmed closed bars and a ready historical
reference, then uses the current executable quote after portfolio/liquidity checks.
It does not assume a fill at the fourth candle's close. Delayed data/setup beyond
the 120-second entry window causes a skip. Deadlines use the actual fill time, not
the earlier poll start.

The earlier challenger/optimization notebooks deliberately modeled a one-hour
latency scenario. Their saved results remain historical research; they do not
validate this exact no-extra-delay production policy. Smaller size and liquidity
gates are explicit implementation choices; historical books were unavailable.
No fitted funding or price-action filter is added to the production rule.

State lives in `listing_volume_short.live.sqlite`. Any rule change freezes a new
identity, so use a new `state_path` rather than deleting state to bypass a mismatch,
and never switch an account to new rules/state while it owns trades.

## Structure

The strategy is the package `strategies/listing_volume_short/`:

- `params.py`: signal and risk parameters.
- `signal.py`: pure rules (universe, listing hour, entry window, first-window volume, reference).
- `state.py`: the typed `Listing` record and its SQLite store.
- `execution.py`: portfolio admission and entry orders.
- `lifecycle.py`: protection, deadline exits and adoption after state loss.
- `strategy.py`: discovery and the polling cycle.

It uses the shared `core/sizing.py` rules and the exchange port; the BingX adapter
supplies the venue details. The normal discriminated settings union and
`otomai --files ...` runner are unchanged.

See [the architecture contract](../architecture/overview.md) for venue differences,
configuration compatibility and execution safeguards.

## Data, gaps and exits

Discovery uses exchange listing metadata, never a truncated first downloaded candle.
Listings are keyed by symbol plus UTC listing hour and archived locally, including
non-signals and listings later removed from the live catalog. Startup backfills the
most recent 60 completed listing windows, 10 requests per cycle. Missing windows
retry after a one-minute backoff. Delisted contracts never observed by this instance
cannot be recovered from today's catalog; this is not a complete historical universe.

A missing member of the actual last-30 set is never replaced by an older available
one. Without the required window/reference, no signal is accepted. A listing whose
first window is still invalid after its own entry window (missing, misaligned or
zero-volume bars, or trades before the launch hour) gets `excluded_reason` and
leaves the universe, as in the research sample; it no longer blocks the next 30
references. Network failures are transient: they retry and keep blocking. Expired entry
windows are never chased. Start before the listing decision to leave bootstrap time.

Stop and target are server-side orders on BingX. Time exits happen on the first poll
at/after the deadline; after downtime the bot closes with a reduce-only market order
on resumption. The process must stay running for timely deadline execution.

## Persistent state and live operation

Each state file freezes a hash of the API key (never the credential), which identifies
the sub-account, and the signal/risk rules. Incompatible restarts fail.
A SQLite exclusive transaction in a separate lock file permits one process per
state path across macOS/Linux/Windows. Use durable local storage. Do not run
multiple live state files against the same account: this is a local path lock,
not an exchange-wide lock. Stop the runner before copying/backing up state.

Live code is implemented and mock-tested; no real BingX orders were used to validate
it. It requires a **dedicated, one-way** USDT futures sub-account per strategy and
environment. The runner checks mode, requests isolated margin and 1× leverage, and
does not swallow setup failures. Never place manual orders or run another bot on that
sub-account. Export `BINGX_API_KEY` and `BINGX_SECRET` through the environment, keeping
credentials out of YAML.


### Exchange as the source of truth

Live mode assumes the sub-account is dedicated to this strategy and environment, so
every short position and every order on it belongs to the strategy. Each poll starts
from BingX: raw account equity (including unrealised P&L) is the sizing denominator,
and account positions give exposure and slots. SQLite is a cache of listing keys,
client IDs and fill times, plus the durable entry intent.

- **Entry.** Persist a deterministic client ID and a `submitting` intent, then send a
  market sell carrying a bootstrap stop from the current quote. An ambiguous entry is
  `uncertain` and blocks new admissions until its client ID resolves. A not-found
  lookup **never authorizes resubmission**, because a second entry adds exposure.
  An unfilled remainder is cancelled; the confirmed average fill and fill time set the
  entry and the 504-hour deadline.
- **Protection.** The position must carry the current stop (fill × 1.20) and target
  (fill × 0.40), sized to the contracts on the exchange. If either is missing, a new
  pair is placed with fresh client IDs; only after both are acknowledged are all other
  orders on the symbol (the bootstrap stop, an earlier attempt) cancelled. Reduce-only
  orders cannot add exposure, so an ambiguous attempt is simply replaced next poll and
  does not block admissions.
- **Deadline.** At the deadline a reduce-only market buy closes the exchange quantity.
  A working close is never duplicated; a close that never reached the venue or left a
  remainder is replaced by a fresh reduce-only close.
- **Flat.** When the exchange shows no position (stop, target or close filled), the
  remaining orders on the symbol are cancelled and the listing is closed.
- **Lost state.** A short with no cached record is adopted from the listing's
  deterministic entry ID once discovery has seen the listing: its fill restores the
  deadline, then protection is rebuilt. A short that matches no entry order is logged
  and left alone. Long positions are never touched.

Admission skips a symbol that already has a position or any open order, since a
leftover reduce-only order could close the new position early. Deadline exits only
run while the bot runs; server-side stop and target orders protect it meanwhile.

Inspect unresolved state with a read-only SQLite viewer, or while stopped:

```bash
sqlite3 -readonly data/listing_volume_short.live.sqlite \
  'SELECT symbol,status,volume,data FROM listings WHERE status IN ("uncertain","open","closing","entry_pending","submitting");'
```

Only an `uncertain` entry needs a human: compare its client ID with the BingX order
history. Never reset it to `observing` or start a second instance to retry it. Losing
the state file is recoverable (open shorts are adopted), but it also loses the
reference history and the record of an entry still in flight; keep it on durable storage.

Adapter references: [BingX swap orders](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md)
and [BingX account equity/positions](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-account/api-reference.md).

## Tests

```bash
uv sync --extra test
uv run pytest tests/strategies/test_listing_volume_short.py -v
uv run pytest tests/ -q
```

Tests forbid CCXT network access. They cover signal timing/missing data, concurrent
sizing, deadlines, restart locking/identity, entry intent ordering,
timeouts without duplicate entries, protection replacement, state-loss adoption,
reduce-only exits and exchange precision/equity/request construction.
