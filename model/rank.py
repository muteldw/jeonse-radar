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
DEFAULT_W = {"station": 1.3, "age": 0.8, "budget": 1.0, "trend": 0.7, "activity": 0.5}
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


def build(rows: list[dict], cfg: dict, weights: dict, today: date) -> list[dict]:
    rows = drop_public_lease(rows, cfg.get("public_lease_ratio", 0.55))
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        a = float(r["area_m2"])
        band = 84 if a < 95 else (99 if a < 110 else 115)
        groups[(r["sgg"], r["umd"], r["apt"], band)].append(r)

    budget = cfg["budget_eok"]
    meta = {norm_name(k): v for k, v in cfg.get("complex_meta", {}).items()}
    st_min = cfg.get("station_minutes_from_base", {})
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
        walk = m.get("walk_min")
        stn = m.get("station")

        f = {
            "station": max(0.0, 1 - ((walk or 15) + st_min.get(stn, 15)) / 30),
            "age": max(0.0, min(1.0, (built - 2000) / 20)) if built else 0.3,
            "budget": max(0.0, min(1.0, (budget - price) / 2 + 0.5)),
            "trend": 0.5,
            "activity": min(1.0, len(recent) / 12),
        }
        if len(trend) >= 3:
            g = (trend[-1] - trend[0]) / trend[0]
            f["trend"] = max(0.0, 1 - abs(g - 0.05) * 6)
        tot = sum(abs(v) for v in weights.values()) or 1
        score = round(100 * sum(weights[k] * f[k] for k in weights) / tot)

        out.append({
            "id": f"{sgg}-{umd}-{apt}-{band}",
            "name": apt, "sgg": sgg, "umd": umd, "built": built,
            "area_m2": band, "pyeong": pyeong(band), "bath": 2 if band >= 80 else 1,
            "price_eok": price, "deals_12m": len(recent),
            "last_deal": recent[-1]["deal_date"],
            "trend_q": qs, "trend": trend,
            "station": stn, "walk_min": walk, "lines": m.get("lines", []),
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
    fb_path = ROOT / "data" / "feedback.json"
    feedback = json.loads(fb_path.read_text(encoding="utf-8")) if fb_path.exists() else {}
    rows = load_rows()
    today = datetime.now(KST).date()
    items = build(rows, cfg, DEFAULT_W, today)
    w = update_weights(DEFAULT_W, items, feedback)
    if w != DEFAULT_W:
        items = build(rows, cfg, w, today)
    out = {
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "budget_eok": cfg["budget_eok"],
        "weights": {k: round(v, 3) for k, v in w.items()},
        "source": "국토교통부 아파트 전월세 실거래가",
        "items": items,
    }
    dst = ROOT / "web" / "data" / "recommend.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"단지 {len(items)}곳 추천 생성 → {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
