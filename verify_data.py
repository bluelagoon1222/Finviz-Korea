#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생성된 data.json 이 배포 가능한 상태인지 검사한다. 이상하면 종료코드 1."""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "site/data.json"
d = json.load(open(path, encoding="utf-8"))
meta, mk = d["meta"], d["markets"]
counts = {k: len(v) for k, v in mk.items()}
total = sum(counts.values())

print(f"기준일 {meta['asOf']} · 갱신 {meta.get('updatedAt','-')}")
print(f"종목수 {counts} (합계 {total})")
print(f"실데이터 기간 {meta.get('realPeriods')}")

errs = []
if total < 200:
    errs.append(f"종목수 부족: {total}")
for m in ("KOSPI", "KOSDAQ"):
    rows = mk.get(m, [])
    if len(rows) < 50:
        errs.append(f"{m} 종목수 부족: {len(rows)}")
        continue
    if sum(r["m"] for r in rows) <= 0:
        errs.append(f"{m} 시가총액 합계가 0")
    zero = sum(1 for r in rows if all(abs(r["r"][p]) < 1e-9 for p in meta["periods"]))
    if zero > len(rows) * 0.5:
        errs.append(f"{m} 수익률이 전부 0인 종목이 {zero}개 — 조회 실패 의심")
    bad = [r["c"] for r in rows if not (-100 <= r["r"]["1D"] <= 100)]
    if bad:
        errs.append(f"{m} 1D 등락률 이상치: {bad[:5]}")

if errs:
    print("\n검사 실패 — 배포를 중단합니다")
    for e in errs:
        print(" -", e)
    sys.exit(1)
print("\n검사 통과")
