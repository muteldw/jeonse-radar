"""국토교통부 아파트 매매 실거래가 수집기 (전용 80㎡↑, 최근 12개월).

같은 MOLIT_API_KEY를 쓰되, 공공데이터포털에서 '국토교통부_아파트 매매 실거래가 자료'를
따로 활용신청해야 한다. 신청 전이면 경고만 남기고 넘어간다(실패 처리하지 않음).
출력: data/sale_raw.csv  (deposit_man 열 = 매매 거래금액, 만원)
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_rent as fr  # noqa: E402

API = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
FIELDS = ["sgg", "umd", "apt", "jibun", "build_year", "area_m2", "floor", "deal_date", "deposit_man"]


def fetch(key: str, lawd: str, ymd: str, name: str) -> list[dict]:
    out, page = [], 1
    while True:
        r = requests.get(API, params={"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ymd,
                                      "pageNo": page, "numOfRows": 1000}, timeout=30)
        r.raise_for_status()
        rows, total = fr.parse(r.text, name)
        out += rows
        if page * 1000 >= total or not rows:
            return out
        page += 1


def main() -> int:
    key = (os.environ.get("MOLIT_API_KEY") or "").strip()
    key = unquote(key) if "%" in key else key
    if not key:
        print("MOLIT_API_KEY 없음 — 매매 수집을 건너뜁니다.")
        return 0
    cfg = json.loads((fr.ROOT / "config.json").read_text(encoding="utf-8"))
    path = fr.ROOT / "data" / "sale_raw.csv"
    rows: dict[tuple, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[tuple(r[k] for k in FIELDS)] = r
    n = 12 if not rows else 3
    ok = fail = 0
    for lawd, name in cfg["regions"].items():
        for ymd in fr.months_back(n):
            try:
                got = fetch(key, lawd, ymd, name)
            except (RuntimeError, ET.ParseError, requests.RequestException) as e:
                fail += 1
                print(f"[경고] 매매 {name} {ymd}: {e}")
                if fail >= 3 and ok == 0:
                    print("매매 API가 아직 승인되지 않은 것 같습니다 — 이번에는 건너뜁니다.")
                    return 0
                continue
            ok += 1
            for r in got:
                if r["area_m2"] >= cfg["min_area_m2"]:
                    s = {k: str(r[k]) for k in FIELDS}
                    rows[tuple(s[k] for k in FIELDS)] = s
            time.sleep(0.2)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: r["deal_date"]):
            w.writerow(r)
    print(f"매매 거래 {len(rows)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
