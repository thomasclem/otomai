# Pre-registration — attempts to beat the listing-volume short (written before any variant was run)
Date: 2026-10-28, before running any variant. Benchmark engine: ChatGPT optimisation notebook cells 1/3/5/7/9 executed verbatim
(1h entry delay, 10bp slippage/side, 5bp fees, 10bp/day funding debit, 5% equity per trade, 30% gross / 10% same-day / 6 slots).
Baseline rule unchanged: 4h decision, vol_rel > 2x, stop 20%, target 60%, 21 days.

## What "beat" means (all must hold)
1. Daily-equity Sharpe above baseline on the FULL history (entries 2024-04-30 .. 2026-10-01, equity to 2026-10-27).
2. Sharpe above baseline in BOTH halves, run as separate portfolios: entries before 2025-10-01, entries from 2025-10-01.
3. Paired 42-day circular block bootstrap: P(Sharpe_variant > Sharpe_baseline) >= 0.90 on the full history.
4. CAGR not lower than baseline by more than 5 percentage points (a pure de-risking that lowers return is reported, not claimed as a win).
Three primary hypotheses -> a variant counts only if it passes; no new hypotheses are added after results are seen.

## Primary hypotheses (one fixed parameterisation each)
H1 BTC hedge: each short is paired with a long BTC perp of equal notional (beta = 1), opened at the same entry hour and closed at the
   short's exit hour; 5bp fee + 2bp slippage per side on BTC, 3bp/day funding paid by the long. Position caps use the short leg only.
   Rationale: strip market beta (e.g. the Q4-2024 BTC rally) from an idiosyncratic decay trade.
H2 Volatility-scaled size: size multiplier = clip(sigma_ref / sigma_i, 0.5, 1.0), where sigma_i = std of log(close/open) of the
   first 4 hourly bars, sigma_ref = median sigma_i of the 30 most recent earlier listings. Only shrinks positions (never > 5%).
   Rationale: equalise risk; the wildest coins are the ones likely to gap through the stop.
   Disclosure: an earlier in-sample glance showed the widest-range tercile had a higher stop rate.
H3 New-token filter: trade only if no USDT spot/perp market for the token existed on Binance, Bybit, OKX or Gate more than
   30 days before the BingX listing (old coins newly added to BingX are skipped). Rationale: the thesis (airdrop/early-holder
   distribution, attention decay) only applies to genuinely new tokens. Requires external metadata.

## Measurement change (applied to baseline and variants alike, not a hypothesis)
M1 Real funding: replace the hypothetical 10bp/day debit with BingX settled funding (short receives positive rates), if data arrives.

## Exploratory only (never used to claim a win)
E1 Same-day Binance perp listing (+-1 day). E2 Threshold sensitivity of H3 (7 / 90 days).

## Amendment A (added 2026-10-28 after seeing H1-proxy and H2 results, BEFORE running H4)
H1/H2 outcomes so far: H2 fails all criteria; H1 with a 4h BTC proxy is flat (final H1 verdict will use 1h BTC).
H4 Walk-forward model over many indicators (counts as one additional primary hypothesis -> 4 in total):
  - Rows: every listing with a volume reference (not only signals). Label: the baseline exit rule's net unit P&L under the
    benchmark engine (stop 20 / target 60 / 21d, 1h delay, costs), clipped to [-0.3, +0.7].
  - Features at the 4h decision: vol_rel, log USD volume, ret, runup, drawdown, off_high, vs_vwap, green_share, rvol,
    vol_last_vs_avg, hour_utc, n_listings_7d, btc_ret_24h, btc_ret_7d, alt index 30d, hot-listings measure, and — if the
    external download succeeds — new-token flag, days listed elsewhere before BingX, number of major exchanges at launch.
  - Model: ridge regression (alpha = 10, fixed, no tuning) on features rank-transformed with the training distribution.
  - Retrain on the 1st of every month using only listings whose 21-day label window ended before that date
    (purged); first fit requires >= 120 matured listings, before that the baseline rule is used.
  - Trade (short, baseline exits) when the prediction exceeds the 80th percentile of the training predictions
    (keeps roughly the baseline's signal frequency). Same "beat" criteria; evaluated once, after the external data is in.
  - Debugging is done on shuffled labels only.
