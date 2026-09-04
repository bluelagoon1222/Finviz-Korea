#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KOREA MAP 데이터 갱신 스크립트  (자동 배포용)
=================================================================
FINVIZ 형식 한국 주식시장 히트맵의 데이터를 실제 시세로 교체하고
index.html 을 다시 생성합니다.

백엔드 2가지
  A. pykrx 자동      python update_korea_map.py --backend pykrx --out site
  B. KRX 엑셀 수동   python update_korea_map.py --backend excel --dir ./krx --out site

핵심 동작 원칙
  · KRX 조회는 기간·시장 단위로만 호출해 요청 수를 최소화합니다(총 20여 회).
  · 각 호출은 3회까지 재시도합니다.
  · 일부 기간이 실패하면 기존 data.json 의 해당 기간 값을 그대로 유지합니다.
  · 핵심 데이터(시가총액·종가) 확보에 실패하면 아무 파일도 건드리지 않고
    종료코드 1 로 끝냅니다 → 자동 배포 시 기존 사이트가 그대로 살아 있습니다.
=================================================================
"""
import argparse, csv, datetime as dt, glob, json, os, sys, time

PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"]
OFFSET_DAYS = {"1D": 1, "1W": 7, "1M": 30, "3M": 91, "6M": 182,
               "1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650}
HERE = os.path.dirname(os.path.abspath(__file__))
KST = dt.timezone(dt.timedelta(hours=9))


def log(msg):
    print(f"[{dt.datetime.now(KST).strftime('%H:%M:%S')}] {msg}", flush=True)


def retry(fn, *a, tries=3, wait=4, what="", **kw):
    """KRX 조회 재시도 래퍼. 끝까지 실패하면 None."""
    for i in range(1, tries + 1):
        try:
            return fn(*a, **kw)
        except Exception as e:
            log(f"  ! {what} 실패 {i}/{tries}: {type(e).__name__} {e}")
            if i < tries:
                time.sleep(wait * i)
    return None


# ----------------------------------------------------------------- 매핑 로드
def load_csv_map(path, key, want):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = str(row[key]).strip().zfill(6)
            out[k] = {w: str(row.get(w, "")).strip() for w in want}
    return out


def load_sectors(path=None):
    path = path or os.path.join(HERE, "sectors.csv")
    m = load_csv_map(path, "종목코드", ["종목명", "섹터"])
    log(f"섹터 매핑 {len(m)}종목 로드" if m else f"경고: {path} 없음 → 섹터는 '기타'")
    return m


def load_etf_universe(path=None):
    path = path or os.path.join(HERE, "etf_universe.csv")
    m = load_csv_map(path, "종목코드", ["종목명", "분류", "순자산_조원"])
    log(f"ETF 유니버스 {len(m)}종목 로드" if m else "경고: etf_universe.csv 없음")
    return m


def prev_data(out_dir):
    """이전 data.json (실패한 기간을 메꾸는 데 사용)"""
    for p in (os.path.join(out_dir, "data.json"), os.path.join(HERE, "data.json")):
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                idx = {}
                for mkt, rows in d.get("markets", {}).items():
                    idx[mkt] = {r["c"]: r for r in rows}
                log(f"이전 데이터 참조: {p} ({d.get('meta',{}).get('asOf')})")
                return idx
            except Exception:
                pass
    return {}


# ----------------------------------------------------------------- A. pykrx
def fetch_pykrx(args, sectors, etfs, prev):
    try:
        from pykrx import stock
    except ImportError:
        sys.exit("pykrx 미설치.  pip install -r requirements.txt")

    base = args.date or dt.datetime.now(KST).strftime("%Y%m%d")
    todate = retry(stock.get_nearest_business_day_in_a_week, date=base, what="기준일 조회")
    if not todate:
        log("치명적: 기준일 조회 실패")
        return None, None, None
    log(f"기준일 {todate}")

    froms = {}
    for p, d in OFFSET_DAYS.items():
        day = (dt.datetime.strptime(todate, "%Y%m%d") - dt.timedelta(days=d)).strftime("%Y%m%d")
        froms[p] = retry(stock.get_nearest_business_day_in_a_week, date=day, prev=True,
                         what=f"{p} 시작일") or day

    markets, failed = {}, []

    for mkt, topn in (("KOSPI", args.top_kospi), ("KOSDAQ", args.top_kosdaq)):
        cap = retry(stock.get_market_cap, todate, market=mkt, what=f"{mkt} 시가총액")
        if cap is None or cap.empty:
            log(f"치명적: {mkt} 시가총액 조회 실패")
            return None, None, None
        cap = cap.sort_values("시가총액", ascending=False).head(topn)
        codes = [str(c).zfill(6) for c in cap.index]
        log(f"{mkt} 상위 {len(codes)}종목")

        chg, names = {}, {}
        for p in PERIODS:
            df = retry(stock.get_market_price_change, froms[p], todate, market=mkt,
                       what=f"{mkt} {p} 등락률")
            if df is None or df.empty:
                failed.append(f"{mkt}/{p}")
                chg[p] = None
                continue
            df.index = [str(i).zfill(6) for i in df.index]
            chg[p] = df["등락률"].to_dict()
            if "종목명" in df.columns:
                names.update(df["종목명"].to_dict())
            log(f"   {p:>4s}  {froms[p]} → {todate}   {len(df)}종목")

        rows = []
        for i, code in enumerate(codes):
            nm = (sectors.get(code, {}).get("종목명")
                  or names.get(code)
                  or retry(stock.get_market_ticker_name, code, tries=1, what="종목명") or code)
            sec = sectors.get(code, {}).get("섹터") or "기타"
            old = prev.get(mkt, {}).get(code, {}).get("r", {})
            r = {}
            for p in PERIODS:
                if chg[p] is not None and code in chg[p]:
                    r[p] = round(float(chg[p][code]), 2)
                else:
                    r[p] = round(float(old.get(p, 0.0)), 2)   # 실패 기간은 이전 값 유지
            rows.append({
                "c": code, "n": nm, "e": nm, "s": sec,
                "m": round(float(cap.iloc[i]["시가총액"]) / 1e12, 3),
                "p": float(cap.iloc[i]["종가"]),
                "r": r,
            })
        markets[mkt] = rows

    # ---------------- ETF
    etf_rows = []
    echg = {}
    for p in PERIODS:
        df = retry(stock.get_etf_price_change_by_ticker, froms[p], todate, what=f"ETF {p} 등락률")
        if df is None or df.empty:
            failed.append(f"ETF/{p}")
            echg[p] = None
            continue
        df.index = [str(i).zfill(6) for i in df.index]
        echg[p] = df["등락률"].to_dict()
    ename = {}
    for p in PERIODS:
        if echg[p] is not None:
            break

    if etfs:
        for code, info in etfs.items():
            old = prev.get("ETF", {}).get(code, {}).get("r", {})
            r = {}
            for p in PERIODS:
                if echg[p] is not None and code in echg[p]:
                    r[p] = round(float(echg[p][code]), 2)
                else:
                    r[p] = round(float(old.get(p, 0.0)), 2)
            try:
                aum = float(info.get("순자산_조원") or 0.05)
            except ValueError:
                aum = 0.05
            etf_rows.append({"c": code, "n": info.get("종목명") or code, "e": info.get("종목명") or code,
                             "s": info.get("분류") or "테마·섹터", "m": max(aum, 0.02), "p": 0, "r": r})
        log(f"ETF {len(etf_rows)}종목 (유니버스 CSV 기준)")
    markets["ETF"] = etf_rows

    if failed:
        log(f"경고: 일부 조회 실패 → 이전 값 유지 ({', '.join(failed)})")
    return todate, markets, failed


# ----------------------------------------------------------------- B. KRX 엑셀
def fetch_excel(args, sectors, etfs, prev):
    try:
        import pandas as pd
    except ImportError:
        sys.exit("pandas 미설치.  pip install -r requirements.txt")

    d = args.dir

    def read(pattern):
        files = sorted(glob.glob(os.path.join(d, pattern)))
        if not files:
            return None
        f = files[0]
        try:
            return pd.read_excel(f) if f.lower().endswith((".xlsx", ".xls")) else pd.read_csv(f, encoding="cp949")
        except UnicodeDecodeError:
            return pd.read_csv(f, encoding="utf-8-sig")

    price = read("price*")
    if price is None:
        log(f"치명적: {d} 안에 전종목 시세 파일(price.csv/.xlsx)이 없습니다.")
        return None, None, None
    price.columns = [str(c).strip() for c in price.columns]
    ccol = next(c for c in price.columns if "종목코드" in c)
    ncol = next(c for c in price.columns if "종목명" in c)
    mcol = next(c for c in price.columns if "시가총액" in c)
    pcol = next((c for c in price.columns if c in ("종가", "현재가")), None)
    scol = next((c for c in price.columns if "시장구분" in c), None)
    icol = next((c for c in price.columns if "업종" in c), None)
    price[ccol] = price[ccol].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)

    chg, failed = {}, []
    for p in PERIODS:
        df = read(f"chg_{p}.*")
        if df is None:
            df = read(f"chg_{p}*")
        if df is None:
            failed.append(p)
            chg[p] = None
            continue
        df.columns = [str(c).strip() for c in df.columns]
        c2 = next(c for c in df.columns if "종목코드" in c)
        r2 = next(c for c in df.columns if "등락률" in c)
        df[c2] = df[c2].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)
        chg[p] = dict(zip(df[c2], pd.to_numeric(df[r2], errors="coerce").fillna(0)))
        log(f"   {p:>4s}  {len(chg[p])}종목")

    markets = {"KOSPI": [], "KOSDAQ": [], "ETF": []}
    price[mcol] = pd.to_numeric(price[mcol], errors="coerce").fillna(0)
    price = price.sort_values(mcol, ascending=False)
    limits = {"KOSPI": args.top_kospi, "KOSDAQ": args.top_kosdaq}

    for _, row in price.iterrows():
        code = row[ccol]
        if etfs and code in etfs:
            continue
        raw = str(row[scol]).upper() if scol else "KOSPI"
        mkt = "KOSDAQ" if ("KOSDAQ" in raw or "코스닥" in raw) else "KOSPI"
        if len(markets[mkt]) >= limits[mkt]:
            continue
        nm = sectors.get(code, {}).get("종목명") or str(row[ncol]).strip()
        sec = sectors.get(code, {}).get("섹터") or (str(row[icol]).strip() if icol else "") or "기타"
        old = prev.get(mkt, {}).get(code, {}).get("r", {})
        r = {p: round(float(chg[p][code]), 2) if (chg[p] and code in chg[p])
             else round(float(old.get(p, 0.0)), 2) for p in PERIODS}
        markets[mkt].append({
            "c": code, "n": nm, "e": nm, "s": sec,
            "m": round(float(row[mcol]) / 1e12, 3),
            "p": float(pd.to_numeric(row[pcol], errors="coerce") or 0) if pcol else 0,
            "r": r,
        })

    for code, info in (etfs or {}).items():
        old = prev.get("ETF", {}).get(code, {}).get("r", {})
        r = {p: round(float(chg[p][code]), 2) if (chg[p] and code in chg[p])
             else round(float(old.get(p, 0.0)), 2) for p in PERIODS}
        try:
            aum = float(info.get("순자산_조원") or 0.05)
        except ValueError:
            aum = 0.05
        markets["ETF"].append({"c": code, "n": info.get("종목명") or code, "e": info.get("종목명") or code,
                               "s": info.get("분류") or "테마·섹터", "m": max(aum, 0.02), "p": 0, "r": r})

    todate = args.date or dt.datetime.now(KST).strftime("%Y%m%d")
    if failed:
        log(f"경고: 기간 파일 없음 → 이전 값 유지 ({', '.join(failed)})")
    return todate, markets, failed


# ----------------------------------------------------------------- 출력
def write_outputs(todate, markets, failed, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    as_of = f"{todate[:4]}-{todate[4:6]}-{todate[6:]}" if len(todate) == 8 else todate
    real = [p for p in PERIODS if not any(f.endswith("/" + p) or f == p for f in (failed or []))]
    data = {
        "meta": {
            "asOf": as_of,
            "updatedAt": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "periods": PERIODS,
            "realPeriods": real,
            "source": "KRX",
            "note": "KRX 실제 시장 데이터",
        },
        "markets": markets,
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8").write(payload)

    tpl_path = os.path.join(HERE, "korea_map_template.html")
    if not os.path.exists(tpl_path):
        log("경고: korea_map_template.html 없음 → data.json만 생성")
        return
    html = open(tpl_path, encoding="utf-8").read().replace("__DATA__", payload)
    for name in ("index.html", "korea_map.html"):
        open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html)
    log(f"생성 완료: {out_dir}/index.html  ({len(html)/1024:.0f} KB)")

    for m, rows in markets.items():
        if not rows:
            continue
        tw = sum(r["m"] for r in rows) or 1
        w = sum(r["r"]["1D"] * r["m"] for r in rows) / tw
        up = sum(1 for r in rows if r["r"]["1D"] > 0)
        log(f"   {m:6s} {len(rows):4d}종목  시총합 {tw:8.1f}조  1D 시총가중 {w:+.2f}%  상승 {up}")


def main():
    ap = argparse.ArgumentParser(description="KOREA MAP 데이터 갱신")
    ap.add_argument("--backend", choices=["pykrx", "excel"], default="pykrx")
    ap.add_argument("--dir", default="./krx", help="excel 백엔드용 KRX 다운로드 폴더")
    ap.add_argument("--out", default=".", help="산출물 폴더 (기본: 현재 폴더)")
    ap.add_argument("--date", help="기준일 YYYYMMDD (기본: 오늘/최근 영업일)")
    ap.add_argument("--sectors", help="섹터 매핑 CSV 경로")
    ap.add_argument("--etf-universe", help="ETF 유니버스 CSV 경로")
    ap.add_argument("--top-kospi", type=int, default=200)
    ap.add_argument("--top-kosdaq", type=int, default=150)
    args = ap.parse_args()

    sectors = load_sectors(args.sectors)
    etfs = load_etf_universe(args.etf_universe)
    prev = prev_data(args.out)

    fetch = fetch_pykrx if args.backend == "pykrx" else fetch_excel
    todate, markets, failed = fetch(args, sectors, etfs, prev)
    if not markets:
        log("갱신 중단 — 기존 파일을 변경하지 않았습니다.")
        sys.exit(1)
    write_outputs(todate, markets, failed, args.out)


if __name__ == "__main__":
    main()
