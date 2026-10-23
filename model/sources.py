"""사용한 자료 목록·기간·건수·수집 현황 → web/data/sources.json ('자료' 탭용)."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import rank

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/muteldw/jeonse-radar"
DGK = "https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword="


def scan(name: str) -> tuple[dict, dict]:
    """CSV → (전체 요약, {구: {유형: 건수}})"""
    p = ROOT / "data" / name
    by: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    rows = []
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = r.get("kind") or "아파트"
                by[r["sgg"]][k] += 1
                rows.append({"deal_date": r["deal_date"], "kind": k})
    return rank.period(rows), {s: dict(v) for s, v in by.items()}


def main() -> None:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    loan = json.loads((ROOT / "config" / "loan_rules.json").read_text(encoding="utf-8"))
    wealth = json.loads((ROOT / "config" / "wealth_dist.json").read_text(encoding="utf-8"))
    rent_p, rent_by = scan("rent_raw.csv")
    sale_p, sale_by = scan("sale_raw.csv")
    geo = json.loads((ROOT / "data" / "geo.json").read_text(encoding="utf-8")) if (ROOT / "data" / "geo.json").exists() else {}
    geo_by = defaultdict(int)
    for k, v in geo.items():
        if v.get("ok"):
            geo_by[k.split("|", 1)[0]] += 1
    rs, ss = rank.collect_status("rent"), rank.collect_status("sale")
    def kinds(p, kind):
        return p.get("by_kind", {}).get(kind, 0)
    datasets = [
        {"name": "국토교통부_아파트 전월세 실거래가 자료", "provider": "국토교통부 · 공공데이터포털", "url": DGK + "아파트 전월세 실거래가",
         "use": "전세 추천·시세·계약기간(이사 시기)", "rows": kinds(rent_p, "아파트"), "period": rent_p, "file": "data/rent_raw.csv"},
        {"name": "국토교통부_연립다세대 전월세 실거래가 자료", "provider": "국토교통부 · 공공데이터포털", "url": DGK + "연립다세대 전월세 실거래가",
         "use": "빌라 전세 추천", "rows": kinds(rent_p, "빌라"), "period": rent_p, "file": "data/rent_raw.csv"},
        {"name": "국토교통부_아파트 매매 실거래가 자료", "provider": "국토교통부 · 공공데이터포털", "url": DGK + "아파트 매매 실거래가",
         "use": "매매 추천·전세가율·매수자 분석", "rows": kinds(sale_p, "아파트"), "period": sale_p, "file": "data/sale_raw.csv"},
        {"name": "국토교통부_연립다세대 매매 실거래가 자료", "provider": "국토교통부 · 공공데이터포털", "url": DGK + "연립다세대 매매 실거래가",
         "use": "빌라 매매 추천·전세가율", "rows": kinds(sale_p, "빌라"), "period": sale_p, "file": "data/sale_raw.csv"},
        {"name": "카카오 로컬 API (주소·키워드·카테고리 검색)", "provider": "카카오", "url": "https://developers.kakao.com/docs/latest/ko/local/dev-guide",
         "use": "단지 위치, 가까운 전철역·도보 시간, 학교·어린이집·마트·병원 수", "rows": sum(geo_by.values()), "period": {}, "file": "data/geo.json"},
        {"name": "OpenStreetMap 지도", "provider": "OpenStreetMap 기여자", "url": "https://www.openstreetmap.org/copyright",
         "use": "지도 배경", "rows": None, "period": {}, "file": None},
        {"name": "주택담보대출 규칙 (LTV·한도·DSR·취득세)", "provider": loan.get("source", ""), "url": None,
         "use": "매수자 자금 분석", "rows": None, "period": {"as_of": loan.get("as_of")}, "file": "config/loan_rules.json"},
        {"name": "규제지역·토지거래허가구역 목록", "provider": "10·15 대책 (서울 25개 구 + 경기 12곳)", "url": None,
         "use": "대출·실거주 의무 판단", "rows": len(loan.get("regulated_sgg", [])), "period": {"as_of": loan.get("as_of")}, "file": "config/loan_rules.json"},
        {"name": "가구 순자산 분포 (상위 % 추정)", "provider": " · ".join(wealth.get("notes", [])[:3]), "url": None,
         "use": "매수자 자산 상위 % 추정", "rows": len(wealth.get("points", [])), "period": {"as_of": wealth.get("as_of")}, "file": "config/wealth_dist.json"},
    ]
    regions = []
    for code, name in cfg["regions"].items():
        regions.append({"code": code, "name": name, "area": rank.area_of(name, cfg)[1].get("name", ""),
                        "rent": rent_by.get(name, {}), "sale": sale_by.get(name, {}),
                        "rent_done": rs.get(name, {}), "sale_done": ss.get(name, {}), "located": geo_by.get(name, 0)})
    out = {"generated_at": datetime.now(rank.KST).isoformat(timespec="minutes"), "repo": REPO,
           "conditions": {"min_area_m2": cfg["min_area_m2"], "months_back": cfg["months_back"], "jeonse_only": cfg.get("jeonse_only", True)},
           "datasets": datasets, "regions": regions}
    (ROOT / "web" / "data" / "sources.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"자료 목록 {len(datasets)}개, 지역 {len(regions)}곳 → web/data/sources.json")


if __name__ == "__main__":
    main()
