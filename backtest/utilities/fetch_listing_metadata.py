"""Fetch open exchange metadata for every BingX listing in database/exchanges/bingx/1h.

Outputs (database/external/):
  listing_metadata.csv  - BingX launchTime + first listing time of the same token on Binance, Bybit, OKX, Gate
  bingx_funding.csv     - BingX funding-rate history for the first 30 days after each listing
                          (BingX only keeps ~5 months of funding history: older listings come back empty)
  BTC-USDT-USDT_1h.csv  - BingX BTC perp 1h candles (for hedging / marking)

Public endpoints only, no API key. Run from the repo root:
    .venv/bin/python backtest/utilities/fetch_listing_metadata.py
"""
import glob, os, re, time, sys
import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "database", "exchanges", "bingx", "1h")
OUT = os.path.join(ROOT, "database", "external")
os.makedirs(OUT, exist_ok=True)

coins = sorted(os.path.basename(f).replace("-USDT-USDT.csv", "") for f in glob.glob(os.path.join(SRC, "*-USDT-USDT.csv")))
first_bar = {}
for c in coins:
    with open(os.path.join(SRC, f"{c}-USDT-USDT.csv")) as fh:
        fh.readline(); line = fh.readline()
        first_bar[c] = int(line.split(",")[0]) if line else None
print(f"{len(coins)} BingX coins")

def bases(coin):
    """Names the same token may use elsewhere (BingX '1000PEPE' -> 'PEPE', '1000000MOG' -> 'MOG')."""
    out = {coin}
    m = re.match(r"^(1000000|100000|10000|1000|100)(.+)$", coin)
    if m: out.add(m.group(2))
    return out

def load(ex_id, **opts):
    ex = getattr(ccxt, ex_id)({"enableRateLimit": True, **opts})
    for attempt in range(3):
        try:
            ex.load_markets(); return ex
        except Exception as e:
            print(f"  {ex_id} load_markets failed ({attempt+1}/3): {str(e)[:120]}"); time.sleep(3)
    return None

def earliest_created(ex, coin, kinds):
    best = None
    for m in ex.markets.values():
        if m.get("quote") != "USDT" or m.get("base") not in bases(coin): continue
        kind = "spot" if m.get("spot") else ("perp" if m.get("swap") and m.get("linear") else None)
        if kind not in kinds: continue
        ts = m.get("created")
        if ts is None:
            info = m.get("info", {}) or {}
            for k in ("onboardDate", "launchTime", "listTime", "buy_start"):
                if info.get(k): ts = int(info[k]) * (1000 if k == "buy_start" else 1); break
        if ts:
            best = int(ts) if best is None else min(best, int(ts))
    return best

rows = {c: {"coin": c, "first_1h_bar_ms": first_bar[c]} for c in coins}

# 1) BingX launch time (verifies the first-candle listing proxy)
bingx = load("bingx")
for c in coins:
    m = bingx.markets.get(f"{c}/USDT:USDT") if bingx else None
    rows[c]["bingx_launch_ms"] = int(m["info"]["launchTime"]) if m and m.get("info", {}).get("launchTime") else None

# 2) Other exchanges: unified 'created' listing timestamp
specs = [("binanceusdm", {}, {"perp"}, "binance_perp_ms"),
         ("bybit", {"options": {"fetchMarkets": {"types": ["spot", "linear"]}}}, {"spot", "perp"}, None),
         ("okx", {"options": {"fetchMarkets": {"types": ["spot", "swap"]}}}, {"spot", "perp"}, None),
         ("gate", {"options": {"fetchMarkets": {"types": ["spot", "swap"]}}}, {"spot", "perp"}, None)]
for ex_id, opts, kinds, single in specs:
    print("loading", ex_id); ex = load(ex_id, **opts)
    if ex is None and opts: ex = load(ex_id)
    for c in coins:
        for k in sorted(kinds):
            col = single or f"{ex_id}_{k}_ms"
            rows[c][col] = earliest_created(ex, c, {k}) if ex else None

# 3) Binance spot has no listing date in its metadata -> first daily candle
print("binance spot first candles")
bs = load("binance")
for i, c in enumerate(coins):
    ts = None
    if bs:
        for b in bases(c):
            sym = f"{b}/USDT"
            if sym in bs.markets:
                try:
                    k = bs.fetch_ohlcv(sym, "1d", since=1, limit=1)
                    if k: ts = k[0][0] if ts is None else min(ts, k[0][0])
                except Exception as e:
                    print("  ", sym, str(e)[:80])
    rows[c]["binance_spot_ms"] = ts
meta = pd.DataFrame(rows.values())
meta.to_csv(os.path.join(OUT, "listing_metadata.csv"), index=False)
print("saved listing_metadata.csv", meta.notna().sum().to_dict())

# 4) BingX funding history, first 30 days after listing
print("bingx funding history")
fund = []
for i, c in enumerate(coins):
    sym = f"{c}/USDT:USDT"
    if not bingx or sym not in bingx.markets or not first_bar[c]: continue
    since, until = first_bar[c] - 3600_000, first_bar[c] + 30 * 86400_000
    try:
        hist = bingx.fetch_funding_rate_history(sym, since=since, limit=1000, params={"until": until})
        fund += [dict(coin=c, ts=h["timestamp"], rate=h["fundingRate"]) for h in hist if h.get("timestamp") and h["timestamp"] <= until]
    except Exception as e:
        print("  ", sym, str(e)[:100])
    if i % 50 == 0: print(f"  {i}/{len(coins)}")
pd.DataFrame(fund).to_csv(os.path.join(OUT, "bingx_funding.csv"), index=False)
print("saved bingx_funding.csv", len(fund), "rows,", len({f['coin'] for f in fund}), "coins")

# 5) BTC 1h
print("BTC 1h")
since, rows_btc = bingx.parse8601("2024-04-01T00:00:00Z"), []
now_ms = bingx.milliseconds()
while since < now_ms:                       # BingX may return fewer than `limit` candles per call: page until now
    k = bingx.fetch_ohlcv("BTC/USDT:USDT", "1h", since=since, limit=1000)
    if not k: break
    rows_btc += k; since = k[-1][0] + 3600_000
btc = pd.DataFrame(rows_btc, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
btc.to_csv(os.path.join(OUT, "BTC-USDT-USDT_1h.csv"), index=False)
print("saved BTC 1h:", len(btc), "candles", pd.to_datetime(btc.date.iloc[0], unit="ms"), "->", pd.to_datetime(btc.date.iloc[-1], unit="ms"))
print("DONE")
