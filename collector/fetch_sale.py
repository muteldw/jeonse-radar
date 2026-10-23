"""국토교통부 매매 실거래가 수집기 — 아파트 + 빌라(연립·다세대), 전용 80㎡↑, 최근 24개월.

같은 MOLIT_API_KEY를 쓰되 자료마다 활용신청이 필요하다.
  - 국토교통부_아파트 매매 실거래가 자료
  - 국토교통부_연립다세대 매매 실거래가 자료
신청 전이면 경고만 남기고 넘어간다(실패 처리하지 않음).
출력: data/sale_raw.csv  (deposit_man 열 = 매매 거래금액, 만원)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_rent as fr  # noqa: E402

SALE_API = {"아파트": f"{fr.BASE}/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
            "빌라": f"{fr.BASE}/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"}
FIELDS = ["kind", "sgg", "umd", "apt", "jibun", "build_year", "area_m2", "floor", "deal_date", "deposit_man"]


def keep(r: dict, cfg: dict) -> bool:
    return float(r["area_m2"]) >= cfg["min_area_m2"]


def main() -> int:
    key = (os.environ.get("MOLIT_API_KEY") or "").strip()
    key = unquote(key) if "%" in key else key
    if not key:
        print("MOLIT_API_KEY 없음 — 매매 수집을 건너뜁니다.")
        return 0
    cfg = json.loads((fr.ROOT / "config.json").read_text(encoding="utf-8"))
    fr.collect(key, cfg, SALE_API, fr.ROOT / "data" / "sale_raw.csv", FIELDS, "sale", 24, keep, "매매")
    return 0


if __name__ == "__main__":
    sys.exit(main())
