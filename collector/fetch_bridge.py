"""임시 거처(브릿지) 시세 수집 — 다음 집 근처의 월세 실거래(아파트 전 평형 + 오피스텔).

지금 집 만기와 다음 집 입주 사이 몇 달을 지낼 곳을 고르기 위한 자료.
전세 추천용 rent_raw.csv(전용 80㎡↑ 전세만)와 따로 data/bridge_raw.csv 에 쌓는다.
- 국토교통부_아파트 전월세 실거래가 자료 (이미 승인)
- 국토교통부_오피스텔 전월세 실거래가 자료 (신청 전이면 건너뜀)
config.json "bridge": {"regions": {"11500": "강서구"}, "months_back": 12}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_rent as fr  # noqa: E402

ROOT = fr.ROOT


def keep(row: dict, cfg: dict) -> bool:
    # 월세(보증부 월세 포함)만, 원룸~국평까지
    return row["monthly_man"] > 0 and 15 <= row["area_m2"] <= 115


def main() -> int:
    key = (os.environ.get("MOLIT_API_KEY") or "").strip()
    if "%" in key:
        from urllib.parse import unquote
        key = unquote(key)
    if not key:
        print("MOLIT_API_KEY 없음 — 건너뜀")
        return 0
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    b = cfg.get("bridge") or {}
    if not b.get("regions"):
        print("config.json bridge.regions 없음 — 건너뜀")
        return 0
    sub = {"kinds": ["아파트", "오피스텔"], "regions": b["regions"], "min_area_m2": 0}
    out = ROOT / "data" / "bridge_raw.csv"
    out.parent.mkdir(exist_ok=True)
    fr.collect(key, sub, fr.RENT_API, out, fr.FIELDS, "bridge", int(b.get("months_back", 12)), keep, "임시 거처 월세")
    return 0


if __name__ == "__main__":
    sys.exit(main())
