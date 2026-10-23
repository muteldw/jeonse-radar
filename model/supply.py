"""단지별 월별 전세 만기·예상 매물 예측과 계절 시세 지수.

원리
- 전월세 실거래 신고에는 계약기간(예: 25.04~27.04)이 있어 단지별로 '언제 계약이 끝나는지' 알 수 있다.
- 만기가 오면 세입자는 갱신하거나 나간다. 나가면 그 집이 전세 매물로 나온다.
  · 첫 계약(신규) 만기: 나갈 확률 = 1 − 그 단지의 최근 갱신 비율 (지역 평균으로 보정)
  · 이미 갱신요구권을 쓴 계약 만기: 다시 쓸 수 없어 나갈 확률이 높다 (config: renewed_leave_prob)
- 매물은 보통 만기 2개월 전쯤 나온다 (config: listing_lead_months).
- 신고된 거래만 셀 수 있어 실제 매물보다 적게 잡히는 '하한'에 가깝다.

출력: web/data/supply.json
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import rank

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def ym_add(y: int, m: int, k: int) -> tuple[int, int]:
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def ym(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def contract_end(r: dict) -> str | None:
    """계약 만기 월 'YYYY-MM'. 계약기간이 없으면 계약일 + 24개월."""
    t = (r.get("contract_term") or "").strip()
    m = re.search(r"(\d{2,4})\.(\d{1,2})\s*~\s*(\d{2,4})\.(\d{1,2})", t)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        return ym(y, int(m.group(4)))
    try:
        y, mo = int(r["deal_date"][:4]), int(r["deal_date"][5:7])
    except (KeyError, ValueError):
        return None
    return ym(*ym_add(y, mo, 24))


def is_renewed(r: dict) -> bool:
    return r.get("contract_type") == "갱신" or (r.get("use_rr") or "").strip() == "사용"


def group_id(r: dict) -> str:
    return f"{r['sgg']}-{r['umd']}-{r['apt']}-{rank.band_of_area(float(r['area_m2']))}"


def build(rows: list[dict], today: date, cfg: dict) -> dict:
    lead = int(cfg.get("listing_lead_months", 2))
    p_rr = float(cfg.get("renewed_leave_prob", 0.7))
    horizon = int(cfg.get("horizon_months", 18))
    k_shrink = 10.0

    rows = rank.drop_public_lease(rows, cfg.get("public_lease_ratio", 0.55))
    since = today.replace(year=today.year - 1).isoformat()

    # 갱신 비율: 최근 12개월 계약 중 갱신 비중 (단지별, 지역 평균으로 수축 보정)
    cnt = defaultdict(lambda: [0, 0])  # id -> [갱신, 전체]
    reg = [0, 0]
    for r in rows:
        if r["deal_date"] >= since and r.get("contract_type") in ("신규", "갱신"):
            c = cnt[group_id(r)]
            c[0] += r["contract_type"] == "갱신"
            c[1] += 1
            reg[0] += r["contract_type"] == "갱신"
            reg[1] += 1
    reg_rate = reg[0] / reg[1] if reg[1] else 0.5
    rate = {g: (a + k_shrink * reg_rate) / (n + k_shrink) for g, (a, n) in cnt.items()}

    y0, m0 = today.year, today.month
    months = [ym(*ym_add(y0, m0, i)) for i in range(horizon)]
    idx = {mm: i for i, mm in enumerate(months)}

    items: dict[str, dict] = defaultdict(lambda: {"exp": [0.0] * horizon, "list": [0.0] * horizon})
    region_exp, region_list = [0.0] * horizon, [0.0] * horizon
    for r in rows:
        end = contract_end(r)
        if not end:
            continue
        g = group_id(r)
        leave = p_rr if is_renewed(r) else 1 - rate.get(g, reg_rate)
        ey, em = int(end[:4]), int(end[5:7])
        lm = ym(*ym_add(ey, em, -lead))
        it = items[g]
        if end in idx:
            it["exp"][idx[end]] += 1
            region_exp[idx[end]] += 1
        if lm in idx:
            it["list"][idx[lm]] += leave
            region_list[idx[lm]] += leave

    # 계절 지수: 신규 계약의 '같은 단지·같은 해 중위가 대비' 가격 비율과 거래량을 달(1~12월)별로
    by_gy: dict[tuple, list[int]] = defaultdict(list)
    for r in rows:
        if r.get("contract_type") == "신규":
            by_gy[(group_id(r), r["deal_date"][:4])].append(int(r["deposit_man"]))
    med_gy = {k: median(v) for k, v in by_gy.items() if len(v) >= 3}
    ratio_m, vol_m = defaultdict(list), defaultdict(int)
    for r in rows:
        if r.get("contract_type") != "신규":
            continue
        mo = int(r["deal_date"][5:7])
        vol_m[mo] += 1
        base = med_gy.get((group_id(r), r["deal_date"][:4]))
        if base:
            ratio_m[mo].append(int(r["deposit_man"]) / base)
    total_vol = sum(vol_m.values()) or 1
    season = {str(mo): {"price": round(median(ratio_m[mo]), 4) if ratio_m.get(mo) else None,
                        "volume": round(vol_m.get(mo, 0) / total_vol * 12, 3)} for mo in range(1, 13)}

    out_items = {g: {"exp": [round(x, 1) for x in v["exp"]], "list": [round(x, 2) for x in v["list"]],
                     "renew_rate": round(rate.get(g, reg_rate), 3)}
                 for g, v in items.items() if sum(v["exp"]) or sum(v["list"])}
    return {
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "months": months, "lead_months": lead, "renewed_leave_prob": p_rr,
        "region_renew_rate": round(reg_rate, 3),
        "region": {"exp": [round(x, 1) for x in region_exp], "list": [round(x, 1) for x in region_list]},
        "season": season, "items": out_items,
        "terms_known": sum(1 for r in rows if r.get("contract_term")), "rows": len(rows),
    }


def main() -> None:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    p = ROOT / "data" / "rent_raw.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []
    out = build(rows, datetime.now(KST).date(), cfg.get("supply", {}) | {"public_lease_ratio": cfg.get("public_lease_ratio", 0.55)})
    items = out.pop("items")
    # 생활권별로 나눠 저장 (휴대폰에서 필요한 지역만 내려받도록)
    d = ROOT / "web" / "data" / "supply"
    d.mkdir(parents=True, exist_ok=True)
    code_of = {name: code for code, name in cfg["regions"].items()}
    by: dict[str, dict] = defaultdict(dict)
    for gid, v in items.items():
        by[code_of.get(gid.split("-", 1)[0], "_")][gid] = v
    for old in d.glob("*.json"):
        if old.stem not in cfg["regions"]:
            old.unlink()
    for k in cfg["regions"]:
        sub = by.get(k, {})
        h = len(out["months"])
        reg = {"exp": [round(sum(v["exp"][i] for v in sub.values()), 1) for i in range(h)],
               "list": [round(sum(v["list"][i] for v in sub.values()), 1) for i in range(h)]}
        (d / f"{k}.json").write_text(json.dumps({"code": k, "region": reg, "items": sub}, ensure_ascii=False,
                                                separators=(",", ":")), encoding="utf-8")
    dst = ROOT / "web" / "data" / "supply.json"
    out["period"] = rank.period(rows)
    dst.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"예상 매물 계산: 단지 {len(items)}곳, 계약기간 확인 {out['terms_known']}/{out['rows']}건 → supply.json + supply/")


if __name__ == "__main__":
    main()
