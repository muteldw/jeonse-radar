"""국토교통부 아파트 전월세 실거래가 수집기.

GitHub Actions에서 매일 실행된다. API 키는 환경변수 MOLIT_API_KEY
(공공데이터포털 '국토교통부_아파트 전월세 실거래가 자료' 일반 인증키, Decoding 값)로 받는다.

출력: data/rent_raw.csv  (조건에 맞는 전세 거래 누적, 중복 제거)
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
FIELDS = ["sgg", "umd", "apt", "jibun", "build_year", "area_m2", "floor",
          "deal_date", "deposit_man", "monthly_man", "contract_type"]


def months_back(n: int, today: date | None = None) -> list[str]:
    t = today or date.today()
    y, m, out = t.year, t.month, []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _num(s: str | None) -> float:
    if not s:
        return 0.0
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _t(item: ET.Element, *names: str) -> str:
    """구버전(한글 태그)과 신버전(영문 태그) 모두 지원."""
    for n in names:
        el = item.find(n)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def parse(xml_text: str, sgg_name: str) -> tuple[list[dict], int]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        raise RuntimeError(f"XML이 아닌 응답: {xml_text[:150]!r}")
    code = root.findtext(".//resultCode", "")
    if code not in ("00", "000", ""):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg', '')}")
    total = int(root.findtext(".//totalCount", "0") or 0)
    rows = []
    for it in root.iter("item"):
        y, m, d = _t(it, "dealYear", "년"), _t(it, "dealMonth", "월"), _t(it, "dealDay", "일")
        rows.append({
            "sgg": sgg_name,
            "umd": _t(it, "umdNm", "법정동"),
            "apt": _t(it, "aptNm", "아파트"),
            "jibun": _t(it, "jibun", "지번"),
            "build_year": int(_num(_t(it, "buildYear", "건축년도"))),
            "area_m2": _num(_t(it, "excluUseAr", "전용면적")),
            "floor": int(_num(_t(it, "floor", "층"))),
            "deal_date": f"{int(_num(y)):04d}-{int(_num(m)):02d}-{int(_num(d)):02d}",
            "deposit_man": int(_num(_t(it, "deposit", "보증금액"))),
            "monthly_man": int(_num(_t(it, "monthlyRent", "월세금액"))),
            "contract_type": _t(it, "contractType", "계약구분"),
        })
    return rows, total


def fetch_month(key: str, lawd: str, ymd: str, sgg_name: str) -> list[dict]:
    out, page = [], 1
    while True:
        params = {"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ymd,
                  "pageNo": page, "numOfRows": 1000}
        for attempt in range(3):
            try:
                r = requests.get(API, params=params, timeout=30)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3)
        rows, total = parse(r.text, sgg_name)
        out += rows
        if page * 1000 >= total or not rows:
            return out
        page += 1


def keep(row: dict, cfg: dict) -> bool:
    if row["area_m2"] < cfg["min_area_m2"]:
        return False
    if cfg.get("jeonse_only", True) and row["monthly_man"] > 0:
        return False
    return True


def load_existing(path: Path) -> dict[tuple, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {_key(r): r for r in csv.DictReader(f)}


def _key(r: dict) -> tuple:
    return (r["apt"], r["jibun"], str(r["area_m2"]), str(r["floor"]), r["deal_date"], str(r["deposit_man"]))


def main() -> int:
    key = (os.environ.get("MOLIT_API_KEY") or "").strip()
    # 포털의 Encoding 키(%2B 등 포함)를 넣어도 동작하도록 디코딩 (requests가 다시 인코딩함)
    if "%" in key:
        from urllib.parse import unquote
        key = unquote(key)
    if not key:
        print("MOLIT_API_KEY 환경변수가 없습니다. GitHub 저장소 Settings > Secrets에 등록하세요.")
        return 1
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    out_path = ROOT / "data" / "rent_raw.csv"
    out_path.parent.mkdir(exist_ok=True)
    rows = load_existing(out_path)
    # 처음에는 months_back 전체, 이후에는 최근 3개월만 다시 받아 지연 신고분을 반영
    n = cfg["months_back"] if not rows else 3
    added, failed, calls = 0, 0, 0
    for lawd, name in cfg["regions"].items():
        for ymd in months_back(n):
            calls += 1
            try:
                month_rows = fetch_month(key, lawd, ymd, name)
            except (RuntimeError, ET.ParseError, requests.RequestException) as e:
                # 공공데이터 API 일시 장애·트래픽 초과 시 기존 데이터로 계속 진행
                failed += 1
                print(f"[경고] {name} {ymd} 수집 실패: {e}")
                continue
            for r in month_rows:
                if keep(r, cfg):
                    k = _key({kk: str(v) for kk, v in r.items()})
                    if k not in rows:
                        added += 1
                    rows[k] = r
            time.sleep(0.2)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: r["deal_date"]):
            w.writerow({k: r[k] for k in FIELDS})
    print(f"전세 거래 {len(rows)}건 저장 (신규 {added}건)")
    if failed:
        print(f"[경고] {calls}건 중 {failed}건 수집 실패 — 기존 데이터로 추천을 계속 만듭니다.")
    if failed == calls and not rows:
        return 1  # 처음 실행인데 하나도 못 받은 경우만 실패 처리
    return 0


if __name__ == "__main__":
    sys.exit(main())
