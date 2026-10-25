"""매매 추천: 아파트·빌라 매매 실거래로 단지(건물)별 매매가·추세·전세가율을 계산하고 점수를 매긴다.

입력: data/sale_raw.csv, data/rent_raw.csv(전세가율), data/geo.json, config.json, config/loan_rules.json
출력: web/data/sale.json(메타) + web/data/sale/<생활권>.json

점수 = 역 접근성·신축도·매수 예산 여유·가격 흐름(최근 1년)·거래 활발도·생활 인프라.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median

import rank

ROOT = Path(__file__).resolve().parents[1]
SALE_W = {"station": 1.3, "age": 0.8, "budget": 1.0, "momentum": 0.7, "activity": 0.5, "infra": 0.8}


def build(sales: list[dict], cfg: dict, today: date, geo: dict, jeonse: dict, weights: dict = SALE_W) -> list[dict]:
    budget = float(cfg.get("buy_budget_eok", 12.0))
    regulated = set(cfg.get("regulated_sgg", []))
    toheo_kinds = set(cfg.get("toheo_kinds", ["아파트"]))
    since = today.replace(year=today.year - 1).isoformat()
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in sales:
        groups[(r["sgg"], r["umd"], r["apt"], rank.band_of_area(float(r["area_m2"])))].append(r)
    out = []
    for (sgg, umd, apt, band), deals in groups.items():
        deals.sort(key=lambda r: r["deal_date"])
        recent = [d for d in deals if d["deal_date"] >= since]
        if not recent:
            continue
        eok = lambda d: int(d["deposit_man"]) / 10000  # noqa: E731
        price = round(median(eok(d) for d in recent[-3:]), 2)
        by_q: dict[str, list[float]] = defaultdict(list)
        for d in deals:
            by_q[rank.quarter(d["deal_date"])].append(eok(d))
        qs = sorted(by_q)[-8:]
        trend = [round(median(by_q[q]), 2) for q in qs]
        # 최근 1년 가격 변화: 최근 2분기 중위 vs 1년 전 2분기 중위
        old = [eok(d) for d in deals if d["deal_date"] < since]
        growth = round(median(eok(d) for d in recent) / median(old) - 1, 3) if old else None
        kind = deals[-1].get("kind") or "아파트"
        built = int(float(deals[-1]["build_year"] or 0))
        g = geo.get(f"{sgg}|{umd}|{apt}", {})
        g = g if g.get("ok") else {}
        area_key, area = rank.area_of(sgg, cfg)
        base = area.get("base") or {}
        base_km = round(rank.km(g["lat"], g["lng"], base["lat"], base["lng"]), 2) if g.get("lat") and base.get("lat") else None
        walk = g.get("walk_min")
        station_f = max(0.0, 1 - (min(walk or 20, 20) + (base_km if base_km is not None else 5) * 3) / 35)
        f = {
            "station": station_f,
            "age": max(0.0, min(1.0, (built - 2000) / 20)) if built else 0.3,
            "budget": max(0.0, min(1.0, (budget - price) / 3 + 0.5)),
            "momentum": max(0.0, min(1.0, 0.5 + (growth or 0) * 3)),
            "activity": min(1.0, len(recent) / 8),
            "infra": rank.infra_score(g.get("infra")),
        }
        tot = sum(abs(v) for v in weights.values()) or 1
        gid = f"{sgg}-{umd}-{apt}-{band}"
        j = jeonse.get(gid)
        out.append({
            "id": gid, "kind": kind, "name": apt, "sgg": sgg, "umd": umd, "built": built,
            "area_m2": band, "pyeong": rank.pyeong(band),
            "bath": (2 if band >= 80 else 1) if kind == "아파트" else None,
            "price_eok": price, "deals_12m": len(recent), "last_deal": recent[-1]["deal_date"],
            "trend_q": qs, "trend": trend, "growth_1y": growth,
            "jeonse_eok": j, "jeonse_ratio": round(j / price, 3) if j else None,
            "gap_eok": round(price - j, 2) if j else None,
            "station": g.get("station"), "walk_min": walk, "lines": g.get("lines", []),
            "lat": g.get("lat"), "lng": g.get("lng"), "st_lat": g.get("st_lat"), "st_lng": g.get("st_lng"),
            "infra": g.get("infra"), "base_km": base_km,
            "area": area_key, "area_name": area.get("name", ""), "base_name": base.get("name", ""),
            "regulated": sgg in regulated,
            "toheo": sgg in regulated and kind in toheo_kinds,
            "within_budget": price <= budget + 0.5,
            "features": {k: round(v, 3) for k, v in f.items()},
            "score": round(100 * sum(weights[k] * f[k] for k in weights) / tot),
        })
    out.sort(key=lambda x: (not x["within_budget"], -x["score"]))
    return out


def main() -> None:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    lr = ROOT / "config" / "loan_rules.json"
    if lr.exists():
        L = json.loads(lr.read_text(encoding="utf-8"))
        cfg["regulated_sgg"], cfg["toheo_kinds"] = L.get("regulated_sgg", []), L.get("toheo_kinds", ["아파트"])
    sp = ROOT / "data" / "sale_raw.csv"
    sales = list(csv.DictReader(sp.open(encoding="utf-8"))) if sp.exists() else []
    gp = ROOT / "data" / "geo.json"
    geo = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else {}
    today = datetime.now(rank.KST).date()
    rent_items = rank.build(rank.load_rows(), cfg, rank.DEFAULT_W, today, geo)
    jeonse = {i["id"]: i["price_eok"] for i in rent_items}
    items = build(sales, cfg, today, geo, jeonse)
    rank.write_split(items, cfg, SALE_W, "sale", "sale.json",
                     "국토교통부 아파트·연립다세대 매매 실거래가", budget_key="buy_budget_eok",
                     data_period=rank.period(sales), status_prefix="sale")
    rank.write_top(items, "top_sale.json")
    if not sales:
        print("매매 실거래가 아직 없습니다 — data.go.kr에서 매매 실거래가 자료 활용신청이 필요합니다.")


if __name__ == "__main__":
    main()
