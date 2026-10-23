"""전세 거래를 단지 단위로 묶어 추천 점수를 매긴다.

입력: data/rent_raw.csv, config.json, data/feedback.json(선택, 관심/제외 기록)
출력: web/data/recommend.json

1단계 점수 = 역 접근성, 신축도, 예산 여유, 가격 추세 안정, 거래 활발도.
가중치는 feedback.json이 쌓이면 갱신된다(3단계에서 LightGBM 랭커로 교체 예정).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_W = {"station": 1.3, "age": 0.8, "budget": 1.0, "trend": 0.7, "activity": 0.5, "infra": 0.8}
KST = timezone(timedelta(hours=9))


def norm_name(s: str) -> str:
    return s.replace(" ", "")


def quarter(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def pyeong(area_m2: float) -> int:
    # 전용면적 → 공급평형 근사(전용 84㎡ ≈ 34평형)
    return round(area_m2 * 1.33 / 3.3058)


def load_rows() -> list[dict]:
    p = ROOT / "data" / "rent_raw.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def drop_public_lease(rows: list[dict], ratio: float = 0.55) -> list[dict]:
    """SH 장기전세·공공임대처럼 시장에서 구할 수 없는 저가 거래를 걸러낸다.
    같은 구·면적대·연도 중위가의 ratio 미만인 전세 거래를 제외."""
    def band_of(r):
        a = float(r["area_m2"])
        return 84 if a < 95 else (99 if a < 110 else 115)
    pool: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        pool[(r["sgg"], band_of(r), r["deal_date"][:4])].append(int(r["deposit_man"]))
    med = {k: median(v) for k, v in pool.items()}
    return [r for r in rows
            if int(r["deposit_man"]) >= ratio * med[(r["sgg"], band_of(r), r["deal_date"][:4])]]


def infra_score(inf: dict | None) -> float:
    if not inf:
        return 0.4
    return min(1.0, 0.3 * min(1, inf.get("학교", 0) / 3) + 0.2 * min(1, inf.get("어린이집·유치원", 0) / 5)
               + 0.3 * min(1, inf.get("대형마트", 0) / 2) + 0.2 * min(1, inf.get("병원", 0) / 10))


def km(lat1, lng1, lat2, lng2) -> float:
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def area_of(sgg: str, cfg: dict) -> tuple[str, dict]:
    """생활권(areas) 찾기. 설정에 없으면 첫 생활권."""
    areas = cfg.get("areas") or {"default": {"name": "", "sgg": [], "base": cfg.get("base_station", {})}}
    for k, a in areas.items():
        if sgg in a.get("sgg", []):
            return k, a
    k = next(iter(areas))
    return k, areas[k]


def band_of_area(a: float) -> int:
    return 84 if a < 95 else (99 if a < 110 else 115)


def sale_prices(sales: list[dict], today: date) -> dict[tuple, float]:
    """단지·면적대별 최근 12개월 매매 거래 마지막 3건 중위가(억)."""
    since = today.replace(year=today.year - 1).isoformat()
    g: dict[tuple, list[dict]] = defaultdict(list)
    for r in sales:
        if r["deal_date"] >= since:
            g[(r["sgg"], r["umd"], r["apt"], band_of_area(float(r["area_m2"])))].append(r)
    return {k: round(median(int(d["deposit_man"]) / 10000 for d in sorted(v, key=lambda d: d["deal_date"])[-3:]), 2)
            for k, v in g.items()}


def build(rows: list[dict], cfg: dict, weights: dict, today: date, geo: dict | None = None,
          sales: dict | None = None) -> list[dict]:
    geo = geo or {}
    sales = sales or {}
    rows = drop_public_lease(rows, cfg.get("public_lease_ratio", 0.55))
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        a = float(r["area_m2"])
        band = 84 if a < 95 else (99 if a < 110 else 115)
        groups[(r["sgg"], r["umd"], r["apt"], band)].append(r)

    budget = cfg["budget_eok"]
    meta = {norm_name(k): v for k, v in cfg.get("complex_meta", {}).items()}
    st_min = cfg.get("station_minutes_from_base", {})
    regulated = set(cfg.get("regulated_sgg", []))
    out = []
    for (sgg, umd, apt, band), deals in groups.items():
        deals.sort(key=lambda r: r["deal_date"])
        # 신규 계약이 있으면 신규만 시세로 사용 (갱신 계약은 5% 상한으로 시세보다 낮게 묶임)
        new_only = [d for d in deals if d.get("contract_type") == "신규"]
        if len(new_only) >= 3:
            deals = new_only
        # 단지 안에 섞인 장기전세(SH) 등 저가 거래 제외: 최근 거래 상위 25% 가격의 78% 미만
        if len(deals) >= 4:
            ps = sorted(int(d["deposit_man"]) for d in deals[-24:])
            p75 = ps[int(len(ps) * 0.75)]
            deals = [d for d in deals if int(d["deposit_man"]) >= 0.78 * p75]
        recent = [d for d in deals if d["deal_date"] >= (today.replace(year=today.year - 1)).isoformat()]
        if not recent:
            continue
        by_q: dict[str, list[float]] = defaultdict(list)
        for d in deals:
            by_q[quarter(d["deal_date"])].append(int(d["deposit_man"]) / 10000)
        qs = sorted(by_q)[-8:]
        trend = [round(median(by_q[q]), 2) for q in qs]
        last3 = [int(d["deposit_man"]) / 10000 for d in recent[-3:]]
        price = round(median(last3), 2)
        built = int(deals[-1]["build_year"] or 0)
        m = meta.get(norm_name(apt), {})
        g = geo.get(f"{sgg}|{umd}|{apt}", {})
        g = g if g.get("ok") else {}
        walk = g.get("walk_min", m.get("walk_min"))
        stn = g.get("station", m.get("station"))
        lines = g.get("lines") or m.get("lines", [])
        area_key, area = area_of(sgg, cfg)
        base = area.get("base") or {}
        base_km = round(km(g["lat"], g["lng"], base["lat"], base["lng"]), 2) if g.get("lat") and base.get("lat") else None
        if base_km is not None:
            # 도보시간 + 생활권 기준역(서울 강서·양천=마곡나루, 안양=범계)까지 거리 1km당 3분으로 환산
            station_f = max(0.0, 1 - (min(walk or 20, 20) + base_km * 3) / 35)
        else:
            station_f = max(0.0, 1 - ((walk or 15) + st_min.get(stn, 15)) / 30)

        f = {
            "station": station_f,
            "age": max(0.0, min(1.0, (built - 2000) / 20)) if built else 0.3,
            "budget": max(0.0, min(1.0, (budget - price) / 2 + 0.5)),
            "trend": 0.5,
            "activity": min(1.0, len(recent) / 12),
            "infra": infra_score(g.get("infra")),
        }
        if len(trend) >= 3:
            growth = (trend[-1] - trend[0]) / trend[0]
            f["trend"] = max(0.0, 1 - abs(growth - 0.05) * 6)
        tot = sum(abs(v) for v in weights.values()) or 1
        score = round(100 * sum(weights[k] * f[k] for k in weights) / tot)

        out.append({
            "id": f"{sgg}-{umd}-{apt}-{band}",
            "name": apt, "sgg": sgg, "umd": umd, "built": built,
            "kind": deals[-1].get("kind") or "아파트",
            "area_m2": band, "pyeong": pyeong(band),
            # 아파트 84㎡↑는 욕실 2개가 표준. 빌라는 구조가 제각각이라 확인 필요(None)
            "bath": (2 if band >= 80 else 1) if (deals[-1].get("kind") or "아파트") == "아파트" else None,
            "price_eok": price, "deals_12m": len(recent),
            "last_deal": recent[-1]["deal_date"],
            "trend_q": qs, "trend": trend,
            "station": stn, "walk_min": walk, "lines": lines,
            "lat": g.get("lat"), "lng": g.get("lng"), "base_km": base_km,
            "area": area_key, "area_name": area.get("name", ""), "base_name": base.get("name", ""),
            "regulated": sgg in regulated if regulated else None,
            "infra": g.get("infra"),
            "st_lat": g.get("st_lat"), "st_lng": g.get("st_lng"),
            "sale_eok": sales.get((sgg, umd, apt, band)),
            "jeonse_ratio": round(price / sales[(sgg, umd, apt, band)], 3) if sales.get((sgg, umd, apt, band)) else None,
            "within_budget": price <= budget + 0.5,
            "features": {k: round(v, 3) for k, v in f.items()},
            "score": score,
        })
    out.sort(key=lambda x: (not x["within_budget"], -x["score"]))
    return out


def update_weights(weights: dict, items: list[dict], feedback: dict) -> dict:
    """관심(+)/제외(-) 반응으로 가중치를 조정하는 간단한 온라인 학습."""
    if not items or not feedback:
        return weights
    by_id = {i["id"]: i for i in items}
    mean = {k: sum(i["features"][k] for i in items) / len(items) for k in weights}
    w = dict(weights)
    for iid, kind in feedback.items():
        it = by_id.get(iid)
        if not it:
            continue
        s = 1 if kind == "like" else -1
        for k in w:
            w[k] = max(0.05, w[k] + s * 0.2 * (it["features"][k] - mean[k]))
    return w


def main() -> None:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    lr = ROOT / "config" / "loan_rules.json"
    if lr.exists():
        cfg["regulated_sgg"] = json.loads(lr.read_text(encoding="utf-8")).get("regulated_sgg", [])
    fb_path = ROOT / "data" / "feedback.json"
    feedback = json.loads(fb_path.read_text(encoding="utf-8")) if fb_path.exists() else {}
    rows = load_rows()
    sp = ROOT / "data" / "sale_raw.csv"
    sales = {}
    if sp.exists():
        with sp.open(encoding="utf-8") as f:
            sales = sale_prices(list(csv.DictReader(f)), datetime.now(KST).date())
    gp = ROOT / "data" / "geo.json"
    geo = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else {}
    today = datetime.now(KST).date()
    items = build(rows, cfg, DEFAULT_W, today, geo, sales)
    w = update_weights(DEFAULT_W, items, feedback)
    if w != DEFAULT_W:
        items = build(rows, cfg, w, today, geo, sales)
    write_split(items, cfg, w, "rec", "recommend.json", "국토교통부 아파트·연립다세대 전월세 실거래가",
                data_period=period(rows), status_prefix="rent")


def public(it: dict) -> dict:
    """화면용으로 가볍게: 학습용 features 제거, 분기 이름은 처음·끝만."""
    o = {k: v for k, v in it.items() if k != "features"}
    if o.get("trend_q"):
        o["trend_q"] = [o["trend_q"][0], o["trend_q"][-1]]
    return o


def collect_status(prefix: str = "rent") -> dict[str, dict]:
    """data/collect_state.json → {구 이름: {"아파트": True/False, "빌라": ...}} (24개월 소급이 끝났는지)."""
    p = ROOT / "data" / "collect_state.json"
    st = json.loads(p.read_text(encoding="utf-8")).get(prefix, {}) if p.exists() else {}
    out: dict[str, dict] = defaultdict(dict)
    for k, v in st.items():
        kind, sgg = k.split("|", 1)
        out[sgg][kind] = bool(v)
    return out


def period(rows: list[dict]) -> dict:
    ds = [r["deal_date"] for r in rows if r.get("deal_date")]
    by = defaultdict(int)
    for r in rows:
        by[r.get("kind") or "아파트"] += 1
    return {"from": min(ds) if ds else None, "to": max(ds) if ds else None, "rows": len(rows), "by_kind": dict(by)}


def write_split(items: list[dict], cfg: dict, w: dict, folder: str, meta_name: str, source: str,
                budget_key: str = "budget_eok", data_period: dict | None = None, status_prefix: str = "rent") -> None:
    """구별 파일(web/data/<folder>/<법정동코드>.json) + 목록·범위·출처를 담은 메타 파일."""
    d = ROOT / "web" / "data" / folder
    d.mkdir(parents=True, exist_ok=True)
    code_of = {name: code for code, name in cfg["regions"].items()}
    by: dict[str, list] = defaultdict(list)
    for it in items:
        by[code_of.get(it["sgg"], "_")].append(public(it))
    for old in d.glob("*.json"):          # 예전 생활권 단위 파일 정리
        if old.stem not in cfg["regions"]:
            old.unlink()
    status = collect_status(status_prefix)
    sgg_meta = {}
    for code, name in cfg["regions"].items():
        its = by.get(code, [])
        (d / f"{code}.json").write_text(json.dumps({"sgg": name, "code": code, "items": its}, ensure_ascii=False,
                                                   separators=(",", ":")), encoding="utf-8")
        pts = [(i["lat"], i["lng"]) for i in its if i.get("lat")]
        sgg_meta[code] = {
            "name": name, "area": area_of(name, cfg)[0], "count": len(its),
            "center": cfg.get("sgg_centers", {}).get(code),
            "with_location": len(pts),
            "bbox": [round(min(p[0] for p in pts), 4), round(min(p[1] for p in pts), 4),
                     round(max(p[0] for p in pts), 4), round(max(p[1] for p in pts), 4)] if pts else None,
            "collected": status.get(name, {}),
        }
    meta = {
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "budget_eok": cfg.get(budget_key, cfg["budget_eok"]),
        "weights": {k: round(v, 3) for k, v in w.items()},
        "source": source, "folder": folder, "layout": "sgg",
        "period": data_period or {},
        "areas": {k: {"name": a["name"], "base": a.get("base", {}), "sgg": a.get("sgg", []),
                      "codes": [code_of[n] for n in a.get("sgg", []) if n in code_of],
                      "count": sum(len(by.get(code_of.get(n, ""), [])) for n in a.get("sgg", []))}
                  for k, a in cfg.get("areas", {}).items()},
        "sgg": sgg_meta,
    }
    (ROOT / "web" / "data" / meta_name).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)}곳 → web/data/{meta_name} + {folder}/<구코드>.json ({sum(1 for c in sgg_meta.values() if c['count'])}개 구에 데이터)")


if __name__ == "__main__":
    main()
