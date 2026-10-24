"""월별 실거래 통계 (전세·매매 각각) → web/data/stats.json ('통계' 탭용).

지역 단위: 전체 / 생활권 / 구, 유형: 전체·아파트·빌라.
월별 지표
  n        거래 건수 (전세는 신규+갱신 전체)
  ppy      3.3㎡(평)당 중위 가격, 만원  (전세는 신규 계약만 — 갱신은 5% 상한에 묶여 시세가 아님)
  med      중위 가격, 억
  idx      단지 보정 가격지수 (같은 단지·평형의 24개월 중위가 대비 비율의 중위 ×100)
           → 비싼 단지가 많이 거래된 달에 값이 튀는 '구성 효과'를 걸러낸 지수
  (전세만) renew  갱신 계약 비중, rr  갱신 중 갱신요구권 사용 비중, gap  신규÷갱신 가격 비율(같은 단지 기준)
표본이 5건 미만인 달은 가격 지표를 비운다(null).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

import rank

ROOT = Path(__file__).resolve().parents[1]
PY = 3.3058
MIN_N = 5


def months_between(a: str, b: str) -> list[str]:
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def scopes_of(sgg: str, cfg: dict, code_of: dict) -> list[str]:
    out = ["all"]
    a = rank.area_of(sgg, cfg)[0]
    if a:
        out.append(f"area:{a}")
    if sgg in code_of:
        out.append(code_of[sgg])
    return out


def gid(r: dict) -> str:
    return f"{r['sgg']}|{r['umd']}|{r['apt']}|{rank.band_of_area(float(r['area_m2']))}"


def build(rows: list[dict], cfg: dict, kind_field: str = "kind", rent: bool = True) -> tuple[dict, list[str]]:
    if not rows:
        return {}, []
    code_of = {n: c for c, n in cfg["regions"].items()}
    if rent:
        rows = rank.drop_public_lease(rows, cfg.get("public_lease_ratio", 0.55))
    ppy = lambda r: int(r["deposit_man"]) / float(r["area_m2"]) * PY  # noqa: E731
    # 단지 기준가: 전세는 신규 계약, 매매는 전체 거래의 24개월 중위 평당가
    base_pool = defaultdict(list)
    for r in rows:
        if not rent or r.get("contract_type") == "신규":
            base_pool[gid(r)].append(ppy(r))
    base = {g: median(v) for g, v in base_pool.items() if len(v) >= 3}
    renew_base_pool = defaultdict(list)
    if rent:
        for r in rows:
            if r.get("contract_type") == "갱신":
                renew_base_pool[gid(r)].append(ppy(r))
    acc = defaultdict(lambda: {"n": 0, "p": [], "e": [], "i": [], "new": 0, "ren": 0, "rr": 0, "ri": []})
    for r in rows:
        mth = r["deal_date"][:7]
        kinds = ["all", r.get(kind_field) or "아파트"]
        is_new = (not rent) or r.get("contract_type") == "신규"
        is_ren = rent and r.get("contract_type") == "갱신"
        g = gid(r)
        ratio = ppy(r) / base[g] if g in base else None
        for s in scopes_of(r["sgg"], cfg, code_of):
            for k in kinds:
                a = acc[(s, k, mth)]
                a["n"] += 1
                if is_new:
                    a["new"] += 1
                    a["p"].append(ppy(r))
                    a["e"].append(int(r["deposit_man"]) / 10000)
                    if ratio:
                        a["i"].append(ratio)
                if is_ren:
                    a["ren"] += 1
                    a["rr"] += (r.get("use_rr") or "").strip() == "사용"
                    if ratio:
                        a["ri"].append(ratio)
    months = months_between(min(r["deal_date"][:7] for r in rows), max(r["deal_date"][:7] for r in rows))
    out: dict = defaultdict(dict)
    keys = {(s, k) for (s, k, _) in acc}
    for s, k in keys:
        ser = defaultdict(list)
        for m in months:
            a = acc.get((s, k, m))
            ok = a and len(a["p"]) >= MIN_N
            ser["n"].append(a["n"] if a else 0)
            ser["ppy"].append(round(median(a["p"])) if ok else None)
            ser["med"].append(round(median(a["e"]), 2) if ok else None)
            ser["idx"].append(round(median(a["i"]) * 100, 1) if a and len(a["i"]) >= MIN_N else None)
            if rent:
                tot = (a["new"] + a["ren"]) if a else 0
                ser["renew"].append(round(a["ren"] / tot, 3) if a and tot >= MIN_N else None)
                ser["rr"].append(round(a["rr"] / a["ren"], 3) if a and a["ren"] >= MIN_N else None)
                ser["gap"].append(round(median(a["i"]) / median(a["ri"]), 3)
                                  if a and len(a["i"]) >= MIN_N and len(a["ri"]) >= MIN_N else None)
        out[s][k] = dict(ser)
    return dict(out), months


def main() -> None:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    def load(n):
        p = ROOT / "data" / n
        return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []
    rent_rows, sale_rows = load("rent_raw.csv"), load("sale_raw.csv")
    rent, rm = build(rent_rows, cfg, rent=True)
    sale, sm = build(sale_rows, cfg, rent=False)
    last = max([r["deal_date"] for r in rent_rows + sale_rows], default=date.today().isoformat())
    # 실거래 신고 기한은 계약 후 30일 → 최근 1~2개월은 아직 신고가 덜 들어온 '잠정' 수치
    prov = (date.fromisoformat(last) - timedelta(days=31)).isoformat()[:7]
    scopes = {"all": "서울·안양 전체"}
    for k, a in cfg.get("areas", {}).items():
        scopes[f"area:{k}"] = a["name"]
        for n in a.get("sgg", []):
            code = next((c for c, nm in cfg["regions"].items() if nm == n), None)
            if code:
                scopes[code] = n
    out = {"generated_at": datetime.now(rank.KST).isoformat(timespec="minutes"),
           "provisional_from": prov, "last_deal": last, "min_n": MIN_N,
           "unit": {"ppy": "만원/3.3㎡", "med": "억", "idx": "단지 보정 지수(24개월 단지 중위=100)"},
           "scopes": scopes, "groups": {k: {"name": a["name"], "codes": [c for c, nm in cfg["regions"].items() if nm in a.get("sgg", [])]}
                                        for k, a in cfg.get("areas", {}).items()},
           "rent": {"months": rm, "data": rent, "rows": len(rent_rows)},
           "sale": {"months": sm, "data": sale, "rows": len(sale_rows)}}
    dst = ROOT / "web" / "data" / "stats.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"통계: 전세 {len(rent_rows)}건 {len(rm)}개월, 매매 {len(sale_rows)}건 {len(sm)}개월, 지역 {len(scopes)}개 → {dst.relative_to(ROOT)} ({dst.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
