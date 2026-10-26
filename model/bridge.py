"""임시 거처(브릿지) 시세 — data/bridge_raw.csv(월세 실거래) → web/data/bridge.json

지금 집 만기와 다음 집 입주 사이를 지낼 곳을 고르기 위해
- 구 전체: 유형(아파트·오피스텔) × 크기(원룸~국평)별 보증금·월세 중위값, 1년 미만 단기 계약 수
- 단지별: 같은 기준의 중위값과 위치(지도·거리 계산용)
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
BANDS = [("one", "원룸·1.5룸", 0, 40), ("two", "투룸", 40, 60), ("three", "쓰리룸", 60, 85), ("four", "국평 이상", 85, 999)]
OPP = 0.03  # 보증금 기회비용(연) — 환산 월 비용 계산용


def band_of(a: float) -> str | None:
    for k, _, lo, hi in BANDS:
        if lo <= a < hi:
            return k
    return None


def term_months(t: str) -> int | None:
    """'26.10~27.04' → 6"""
    try:
        a, b = t.split("~")
        y1, m1 = (int(x) for x in a.strip().split("."))
        y2, m2 = (int(x) for x in b.strip().split("."))
        n = (y2 - y1) * 12 + (m2 - m1)
        return n if 0 < n < 120 else None
    except (ValueError, AttributeError):
        return None


def stats(rows: list[dict]) -> dict:
    dep = sorted(int(r["deposit_man"]) for r in rows)
    mon = sorted(int(r["monthly_man"]) for r in rows)
    eff = sorted(int(r["monthly_man"]) + int(r["deposit_man"]) * OPP / 12 for r in rows)
    terms = [t for t in (term_months(r.get("contract_term", "")) for r in rows) if t]
    q = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))]
    return {"n": len(rows), "dep": int(median(dep)), "mon": int(median(mon)), "eff": int(median(eff)),
            "mon_p25": q(mon, .25), "mon_p75": q(mon, .75),
            "short": sum(1 for t in terms if t < 12), "terms": len(terms)}


def main() -> None:
    p = ROOT / "data" / "bridge_raw.csv"
    out = ROOT / "web" / "data" / "bridge.json"
    rows = list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []
    since = (date.today() - timedelta(days=365)).isoformat()
    rows = [r for r in rows if r["deal_date"] >= since and int(r["monthly_man"] or 0) > 0]
    geo = json.loads((ROOT / "data" / "geo.json").read_text(encoding="utf-8")) if (ROOT / "data" / "geo.json").exists() else {}

    summ: dict = defaultdict(lambda: defaultdict(list))
    by_c: dict = defaultdict(list)
    for r in rows:
        b = band_of(float(r["area_m2"]))
        if not b:
            continue
        summ[r["kind"]][b].append(r)
        by_c[(r["kind"], r["sgg"], r["umd"], r["apt"], b)].append(r)

    places = []
    for (kind, sgg, umd, apt, b), rs in by_c.items():
        g = geo.get(f"{sgg}|{umd}|{apt}") or {}
        if not g.get("ok"):
            continue
        s = stats(rs)
        places.append({"name": apt, "kind": kind, "sgg": sgg, "umd": umd, "band": b,
                       "lat": g["lat"], "lng": g["lng"], "station": g.get("station"), "walk_min": g.get("walk_min"),
                       "built": int(rs[0].get("build_year") or 0) or None,
                       "area": round(median(float(r["area_m2"]) for r in rs)),
                       "last": max(r["deal_date"] for r in rs), **s})
    places.sort(key=lambda x: (-x["n"], x["eff"]))
    data = {
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "source": "국토교통부 아파트·오피스텔 전월세 실거래가 (월세만)",
        "period": {"from": min((r["deal_date"] for r in rows), default=None), "to": max((r["deal_date"] for r in rows), default=None)},
        "rows": len(rows),
        "by_kind": {k: sum(len(v) for v in d.values()) for k, d in summ.items()},
        "regions": sorted({r["sgg"] for r in rows}),
        "bands": [{"key": k, "label": l, "min": lo, "max": hi} for k, l, lo, hi in BANDS],
        "opp_rate": OPP,
        "summary": {k: {b: stats(v) for b, v in d.items()} for k, d in summ.items()},
        "places": places,
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"임시 거처 월세 {len(rows)}건 → web/data/bridge.json (위치 확인 {len(places)}곳)")


if __name__ == "__main__":
    main()
