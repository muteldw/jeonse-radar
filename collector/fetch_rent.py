"""국토교통부 전월세 실거래가 수집기 — 아파트 + 빌라(연립·다세대).

GitHub Actions에서 매일 실행된다. API 키는 환경변수 MOLIT_API_KEY 하나로
아래 공공데이터포털 자료를 모두 쓴다(자료마다 활용신청은 따로 해야 함).
  - 국토교통부_아파트 전월세 실거래가 자료
  - 국토교통부_연립다세대 전월세 실거래가 자료   (빌라. 신청 전이면 건너뜀)

출력: data/rent_raw.csv  (조건에 맞는 전세 거래 누적, 중복 제거, kind 열 = 아파트/빌라)
상태: data/collect_state.json  (지역·유형별 24개월 소급이 끝났는지 — 중간에 끊겨도 다음 날 이어서)
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
BASE = "https://apis.data.go.kr/1613000"
RENT_API = {"아파트": f"{BASE}/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
            "빌라": f"{BASE}/RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
            "오피스텔": f"{BASE}/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent"}   # 임시 거처용(fetch_bridge.py)
API = RENT_API["아파트"]  # 예전 코드 호환
FIELDS = ["kind", "sgg", "umd", "apt", "jibun", "build_year", "area_m2", "floor",
          "deal_date", "deposit_man", "monthly_man", "contract_type", "contract_term", "use_rr"]
STATE = ROOT / "data" / "collect_state.json"
QUOTA_CODES = {"22", "20", "30", "31", "32"}  # 트래픽 초과·미등록 키·미승인 서비스 등


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


class ApiStop(RuntimeError):
    """이 자료는 오늘 더 받을 수 없음(미승인·트래픽 초과)."""


def parse(xml_text: str, sgg_name: str, kind: str = "아파트") -> tuple[list[dict], int]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        txt = xml_text[:200]
        if "SERVICE_KEY" in txt or "LIMITED" in txt or "Unauthorized" in txt or "Forbidden" in txt:
            raise ApiStop(f"API 접근 불가: {txt!r}")
        raise RuntimeError(f"XML이 아닌 응답: {txt!r}")
    code = (root.findtext(".//resultCode", "") or root.findtext(".//returnReasonCode", "")).strip()
    if code not in ("00", "000", ""):
        msg = root.findtext(".//resultMsg", "") or root.findtext(".//returnAuthMsg", "")
        if code in QUOTA_CODES or "LIMITED" in msg or "SERVICE_KEY" in msg:
            raise ApiStop(f"API 오류 {code}: {msg}")
        raise RuntimeError(f"API 오류 {code}: {msg}")
    total = int(root.findtext(".//totalCount", "0") or 0)
    rows = []
    for it in root.iter("item"):
        y, m, d = _t(it, "dealYear", "년"), _t(it, "dealMonth", "월"), _t(it, "dealDay", "일")
        jibun = _t(it, "jibun", "지번")
        name = _t(it, "aptNm", "아파트", "mhouseNm", "연립다세대", "offiNm", "단지", "단지명")
        if kind == "빌라":
            # 빌라는 같은 이름이 흔해 지번으로 건물을 구분한다
            name = f"{name or '빌라'} ({jibun})" if jibun else (name or "빌라")
        rows.append({
            "kind": kind,
            "sgg": sgg_name,
            "umd": _t(it, "umdNm", "법정동"),
            "apt": name,
            "jibun": jibun,
            "build_year": int(_num(_t(it, "buildYear", "건축년도"))),
            "area_m2": _num(_t(it, "excluUseAr", "전용면적")),
            "floor": int(_num(_t(it, "floor", "층"))),
            "deal_date": f"{int(_num(y)):04d}-{int(_num(m)):02d}-{int(_num(d)):02d}",
            "deposit_man": int(_num(_t(it, "deposit", "보증금액", "dealAmount", "거래금액"))),
            "monthly_man": int(_num(_t(it, "monthlyRent", "월세금액"))),
            "contract_type": _t(it, "contractType", "계약구분"),
            "contract_term": _t(it, "contractTerm", "계약기간"),   # 예: "25.01~27.01"
            "use_rr": _t(it, "useRRRight", "갱신요구권사용"),       # "사용" 또는 빈칸
        })
    return rows, total


def fetch_month(key: str, lawd: str, ymd: str, sgg_name: str, url: str = API, kind: str = "아파트") -> list[dict]:
    out, page = [], 1
    while True:
        params = {"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ymd, "pageNo": page, "numOfRows": 1000}
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=30)
                if r.status_code in (401, 403):
                    raise ApiStop(f"HTTP {r.status_code} (활용신청·승인 확인 필요)")
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3)
        rows, total = parse(r.text, sgg_name, kind)
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
        out = {}
        for r in csv.DictReader(f):
            r["kind"] = r.get("kind") or "아파트"
            out[_key(r)] = r
        return out


def _key(r: dict) -> tuple:
    return (r.get("kind") or "아파트", r["apt"], r["jibun"], str(r["area_m2"]), str(r["floor"]),
            r["deal_date"], str(r["deposit_man"]))


def load_state(rows: dict, has_term: bool, prefix: str) -> dict:
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if prefix not in st:
        # 처음 상태 파일을 만들 때: 이미 계약기간까지 받아 둔 아파트 지역은 소급 완료로 본다
        st[prefix] = {f"아파트|{r['sgg']}": True for r in rows.values()
                      if (r.get("kind") or "아파트") == "아파트"} if has_term else {}
    return st


def save_csv(path: Path, rows: dict, fields: list[str]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: r["deal_date"]):
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def collect(key: str, cfg: dict, apis: dict, out_path: Path, fields: list[str], prefix: str,
            months_full: int, keep_fn, label: str) -> tuple[int, int]:
    rows = load_existing(out_path)
    has_term = (not out_path.exists()) or "contract_term" in out_path.open(encoding="utf-8").readline() or prefix == "sale"
    state = load_state(rows, has_term, prefix)
    done = state[prefix]
    added = failed = 0
    for kind in cfg.get("kinds", ["아파트"]):
        url = apis.get(kind)
        if not url:
            continue
        ok_calls = 0
        stopped = False
        for lawd, name in cfg["regions"].items():
            if stopped:
                break
            sk = f"{kind}|{name}"
            full = not done.get(sk)
            n = months_full if full else 3
            if full:
                print(f"[{label}·{kind}] {name}: {n}개월치 소급")
            region_fail = 0
            for ymd in months_back(n):
                try:
                    got = fetch_month(key, lawd, ymd, name, url, kind)
                except ApiStop as e:
                    print(f"[{label}·{kind}] 중단: {e} — 활용신청·승인 전이거나 오늘 트래픽을 다 썼습니다. 다음 실행에서 이어서 받습니다.")
                    stopped = True
                    break
                except (RuntimeError, ET.ParseError, requests.RequestException) as e:
                    failed += 1
                    region_fail += 1
                    print(f"[경고] {label}·{kind} {name} {ymd}: {e}")
                    if ok_calls == 0 and failed >= 3:
                        print(f"[{label}·{kind}] 연속 실패 — 이번 실행은 건너뜁니다.")
                        stopped = True
                        break
                    continue
                ok_calls += 1
                for r in got:
                    if keep_fn(r, cfg):
                        k = _key({kk: str(v) for kk, v in r.items()})
                        if k not in rows:
                            added += 1
                        rows[k] = {kk: str(v) for kk, v in r.items()}
                time.sleep(0.15)
            if not stopped and region_fail == 0 and full:
                done[sk] = True
            save_csv(out_path, rows, fields)          # 지역마다 저장(작업이 끊겨도 받은 만큼 보존)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{label}] 저장 {len(rows)}건 (신규 {added}건), 실패 {failed}건")
    return len(rows), failed


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
    n, _ = collect(key, cfg, RENT_API, out_path, FIELDS, "rent", cfg["months_back"], keep, "전세")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
