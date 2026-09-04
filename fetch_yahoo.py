#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KOREA MAP data fetcher - Yahoo Finance backend (no login required).

Reads the universe (codes, names, sectors, base market cap, base price) from the
existing data.json, downloads daily closes from Yahoo Finance for every listed
code, and rebuilds data.json / index.html with real returns for all nine periods.

Market cap is scaled from the stored snapshot by the price ratio, which is exact
as long as the share count is unchanged:
    market_cap_now = market_cap_snapshot * (close_now / close_snapshot)

Usage:
    python fetch_yahoo.py --out site
    python fetch_yahoo.py --self-test          # offline logic check, no network
"""
import argparse, datetime as dt, json, os, sys, time

PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"]
OFFSET_DAYS = {"1D": 1, "1W": 7, "1M": 30, "3M": 91, "6M": 182,
               "1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650}
HERE = os.path.dirname(os.path.abspath(__file__))
KST = dt.timezone(dt.timedelta(hours=9))
SUFFIX = {"KOSPI": ".KS", "KOSDAQ": ".KQ", "ETF": ".KS"}
# Guard against a bad quote distorting cell sizes: outside this band the stored
# market cap is kept instead of being rescaled.
MCAP_RATIO_MIN, MCAP_RATIO_MAX = 0.25, 4.0


def log(msg):
    print(f"[{dt.datetime.now(KST).strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------- return maths
def returns_from_series(dates, closes):
    """dates: ascending list of date objects. closes: matching list of floats.
    Returns {period: pct} using the last close on or before each target date."""
    if not closes:
        return None, None, None
    last_i = len(closes) - 1
    last = float(closes[last_i])
    last_date = dates[last_i]
    if last <= 0:
        return None, None, None
    out = {}
    for p in PERIODS:
        target = last_date - dt.timedelta(days=OFFSET_DAYS[p])
        j = None
        for i in range(last_i, -1, -1):
            if dates[i] <= target:
                j = i
                break
        if j is None:
            j = 0                       # not enough history: use the oldest bar
        base = float(closes[j])
        if base <= 0 or j == last_i:
            out[p] = 0.0
        else:
            out[p] = round((last / base - 1.0) * 100.0, 2)
    return out, last, last_date


# --------------------------------------------------------------- yahoo download
def download_closes(symbols, chunk=40, tries=3):
    """{symbol: (dates, closes)} from Yahoo Finance."""
    import pandas as pd
    import yfinance as yf

    result = {}
    for start in range(0, len(symbols), chunk):
        batch = symbols[start:start + chunk]
        df = None
        for attempt in range(1, tries + 1):
            try:
                df = yf.download(batch, period="11y", interval="1d",
                                 auto_adjust=False, group_by="ticker",
                                 progress=False, threads=True, timeout=60)
                if df is not None and not df.empty:
                    break
                log(f"  batch {start//chunk+1}: empty response (try {attempt})")
            except Exception as e:
                log(f"  batch {start//chunk+1}: {type(e).__name__} {e} (try {attempt})")
            time.sleep(3 * attempt)
        if df is None or df.empty:
            continue

        for sym in batch:
            ser = None
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    if (sym, "Close") in df.columns:
                        ser = df[(sym, "Close")]
                    elif ("Close", sym) in df.columns:
                        ser = df[("Close", sym)]
                elif "Close" in df.columns and len(batch) == 1:
                    ser = df["Close"]
            except Exception:
                ser = None
            if ser is None:
                continue
            ser = ser.dropna()
            if ser.empty:
                continue
            dates = [d.date() if hasattr(d, "date") else d for d in ser.index]
            result[sym] = (dates, [float(v) for v in ser.values])
        log(f"  downloaded {len(result)}/{len(symbols)} symbols so far")
    return result


# --------------------------------------------------------------- build
def build(args):
    base_path = args.base_data or os.path.join(HERE, "data.json")
    if not os.path.exists(base_path):
        log(f"FATAL: base data file not found: {base_path}")
        return 1
    base = json.load(open(base_path, encoding="utf-8"))
    markets = base["markets"]

    symbols, index = [], {}
    for mkt, rows in markets.items():
        for r in rows:
            sym = r["c"] + SUFFIX.get(mkt, ".KS")
            symbols.append(sym)
            index[sym] = (mkt, r)
    log(f"universe: {len(symbols)} symbols "
        + " / ".join(f"{m} {len(v)}" for m, v in markets.items()))

    data = download_closes(symbols, chunk=args.chunk)
    log(f"symbols with price data: {len(data)}/{len(symbols)}")

    coverage_ok, updated, kept, as_of = 0, 0, 0, None
    odd = []
    for sym, (mkt, row) in index.items():
        if sym not in data:
            kept += 1
            continue
        dates, closes = data[sym]
        rets, last, last_date = returns_from_series(dates, closes)
        if rets is None:
            kept += 1
            continue
        base_price = float(row.get("p") or 0)
        base_mcap = float(row.get("m") or 0)
        row["r"] = rets
        row["p"] = round(last, 1)
        if mkt != "ETF" and base_price > 0 and base_mcap > 0:
            ratio = last / base_price
            if MCAP_RATIO_MIN <= ratio <= MCAP_RATIO_MAX:
                row["m"] = round(base_mcap * ratio, 3)
            else:
                odd.append(f"{row['c']} x{ratio:.2f}")   # keep stored market cap
        if as_of is None or last_date > as_of:
            as_of = last_date
        updated += 1
        coverage_ok += 1

    if odd:
        log(f"market cap kept from snapshot for {len(odd)} rows with an "
            f"implausible price ratio: {', '.join(odd[:10])}"
            + (" ..." if len(odd) > 10 else ""))
    ratio = coverage_ok / max(len(symbols), 1)
    log(f"updated {updated} rows, kept previous values for {kept} rows "
        f"(coverage {ratio*100:.1f}%)")
    if ratio < args.min_coverage:
        log(f"FATAL: coverage below {args.min_coverage*100:.0f}% - refusing to publish")
        return 1

    as_of = as_of or dt.datetime.now(KST).date()
    base["meta"] = {
        "asOf": as_of.strftime("%Y-%m-%d"),
        "updatedAt": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "periods": PERIODS,
        "realPeriods": PERIODS,
        "source": "Yahoo Finance",
        "note": "KRX listed prices via Yahoo Finance. Market cap scaled from the "
                "stored snapshot by the price ratio.",
    }
    if kept:
        base["meta"]["partial"] = kept

    os.makedirs(args.out, exist_ok=True)
    payload = json.dumps(base, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(args.out, "data.json"), "w", encoding="utf-8").write(payload)

    tpl_path = args.template or os.path.join(HERE, "korea_map_template.html")
    if os.path.exists(tpl_path):
        html = open(tpl_path, encoding="utf-8").read().replace("__DATA__", payload)
        for name in ("index.html", "korea_map.html"):
            open(os.path.join(args.out, name), "w", encoding="utf-8").write(html)
        log(f"wrote {args.out}/index.html ({len(html)/1024:.0f} KB)")
    else:
        log(f"WARNING: template not found at {tpl_path} - only data.json written")

    for m, rows in markets.items():
        if not rows:
            continue
        tw = sum(r["m"] for r in rows) or 1
        w = sum(r["r"]["1D"] * r["m"] for r in rows) / tw
        up = sum(1 for r in rows if r["r"]["1D"] > 0)
        log(f"   {m:6s} {len(rows):4d} rows  cap {tw:8.1f}T  1D cap-weighted {w:+.2f}%  up {up}")
    log(f"as of {base['meta']['asOf']}")
    return 0


# --------------------------------------------------------------- self test
def self_test():
    log("self-test: return maths")
    today = dt.date(2026, 9, 4)
    dates, closes = [], []
    d = today - dt.timedelta(days=4000)
    price = 100.0
    while d <= today:
        if d.weekday() < 5:
            dates.append(d)
            closes.append(price)
            price *= 1.0004
        d += dt.timedelta(days=1)
    rets, last, last_date = returns_from_series(dates, closes)
    assert last_date == today or last_date.weekday() >= 4, last_date
    for p in PERIODS:
        assert p in rets, p
    assert rets["10Y"] > rets["5Y"] > rets["1Y"] > rets["1M"] > rets["1D"] > 0, rets
    log(f"  monotonic across periods OK: {rets}")

    short = returns_from_series(dates[-5:], closes[-5:])[0]
    assert short["10Y"] == short["1Y"], short
    log(f"  short history falls back to oldest bar OK: 1Y={short['1Y']} 10Y={short['10Y']}")

    flat = returns_from_series(dates, [50.0] * len(closes))[0]
    assert all(abs(v) < 1e-9 for v in flat.values()), flat
    log("  flat series gives zero returns OK")

    assert returns_from_series([], [])[0] is None
    assert returns_from_series([today], [0.0])[0] is None
    log("  empty and zero-price inputs rejected OK")
    log("self-test passed")
    return 0


def main():
    ap = argparse.ArgumentParser(description="KOREA MAP - Yahoo Finance fetcher")
    ap.add_argument("--out", default="site")
    ap.add_argument("--base-data", help="existing data.json holding the universe")
    ap.add_argument("--template", help="korea_map_template.html path")
    ap.add_argument("--chunk", type=int, default=40)
    ap.add_argument("--min-coverage", type=float, default=0.60)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    sys.exit(self_test() if args.self_test else build(args))


if __name__ == "__main__":
    main()
