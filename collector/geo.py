"""카카오 로컬 API로 단지 위치·가장 가까운 역·주변 인프라를 구한다.

환경변수 KAKAO_REST_KEY 가 없으면 아무것도 하지 않고 넘어간다.
결과는 data/geo.json 에 캐시되어, 새 단지만 조회한다(실패한 단지는 30일 뒤 재시도).
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://dapi.kakao.com/v2/local"
WALK_M_PER_MIN = 67  # 시속 4km
INFRA = {  # 코드: (이름, 반경 m)
    "SC4": ("학교", 700),
    "PS3": ("어린이집·유치원", 500),
    "MT1": ("대형마트", 1500),
    "HP8": ("병원", 1000),
}


def complex_key(sgg: str, umd: str, apt: str) -> str:
    return f"{sgg}|{umd}|{apt}"


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Kakao:
    def __init__(self, key: str, session=None):
        self.s = session or requests.Session()
        self.h = {"Authorization": f"KakaoAK {key}"}

    def get(self, path: str, **params) -> dict:
        for attempt in range(3):
            r = self.s.get(f"{API}/{path}", headers=self.h, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(2 + attempt * 3)
                continue
            if r.status_code in (401, 403):
                raise RuntimeError(f"카카오 키 오류({r.status_code}): {r.text[:200]} "
                                   "— 앱 설정에서 '카카오맵' 사용 설정을 켰는지 확인하세요.")
            r.raise_for_status()
            return r.json()
        return {"documents": [], "meta": {"total_count": 0}}

    def locate(self, sgg: str, umd: str, jibun: str, apt: str) -> tuple[float, float] | None:
        if jibun:
            d = self.get("search/address.json", query=f"{'경기' if '시 ' in sgg else '서울'} {sgg} {umd} {jibun}").get("documents", [])
            if d:
                return float(d[0]["y"]), float(d[0]["x"])
        city = sgg.split()[0] if "시 " in sgg else ""
        d = self.get("search/keyword.json", query=f"{city} {umd} {apt}".strip()).get("documents", [])
        for doc in d:
            if "아파트" in doc.get("category_name", "") or not doc.get("category_name"):
                return float(doc["y"]), float(doc["x"])
        return (float(d[0]["y"]), float(d[0]["x"])) if d else None

    def nearest_station(self, lat: float, lng: float) -> dict | None:
        d = self.get("search/category.json", category_group_code="SW8", x=lng, y=lat,
                     radius=2000, sort="distance").get("documents", [])
        if not d:
            return None
        first = d[0]
        name = re.sub(r"역.*$", "", first["place_name"]).strip()
        lines = []
        for doc in d:
            if re.sub(r"역.*$", "", doc["place_name"]).strip() == name:
                m = re.search(r"역\s*(.+)$", doc["place_name"])
                if m:
                    lines.append(m.group(1).strip())
        dist = int(first.get("distance") or 0)
        return {"station": name, "lines": sorted(set(lines)), "station_m": dist,
                "st_lat": round(float(first["y"]), 6) if first.get("y") else None,
                "st_lng": round(float(first["x"]), 6) if first.get("x") else None,
                "walk_min": max(1, round(dist / WALK_M_PER_MIN))}

    def count(self, code: str, lat: float, lng: float, radius: int) -> int:
        j = self.get("search/category.json", category_group_code=code, x=lng, y=lat,
                     radius=radius, size=1)
        return int(j.get("meta", {}).get("total_count", 0))


def lookup(k: Kakao, sgg, umd, jibun, apt, base: dict) -> dict:
    loc = k.locate(sgg, umd, jibun, apt)
    if not loc:
        return {"ok": False, "tried": date.today().isoformat()}
    lat, lng = loc
    out = {"ok": True, "lat": round(lat, 6), "lng": round(lng, 6)}
    st = k.nearest_station(lat, lng)
    if st:
        out.update(st)
    out["base_km"] = round(haversine_km(lat, lng, base["lat"], base["lng"]), 2)
    out["infra"] = {name: k.count(code, lat, lng, rad) for code, (name, rad) in INFRA.items()}
    return out


def complexes_from_raw() -> dict[str, tuple]:
    """전세·매매 거래에 나온 단지·건물. 최근 거래가 많은 곳부터 조회하도록 거래 수 순으로 정렬."""
    out, cnt = {}, {}
    since = (date.today() - timedelta(days=365)).isoformat()
    for name in ("rent_raw.csv", "sale_raw.csv", "bridge_raw.csv"):
        p = ROOT / "data" / name
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ck = complex_key(r["sgg"], r["umd"], r["apt"])
                out.setdefault(ck, (r["sgg"], r["umd"], r["jibun"], r["apt"]))
                cnt[ck] = cnt.get(ck, 0) + (r["deal_date"] >= since)
    return dict(sorted(out.items(), key=lambda kv: -cnt[kv[0]]))


def main() -> int:
    key = (os.environ.get("KAKAO_REST_KEY") or "").strip()
    if not key:
        print("KAKAO_REST_KEY 없음 — 위치 정보 단계를 건너뜁니다.")
        return 0
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = cfg.get("base_station") or {"lat": 37.5667, "lng": 126.8272}
    path = ROOT / "data" / "geo.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    retry_before = (date.today() - timedelta(days=30)).isoformat()
    k = Kakao(key)
    todo = [(ck, v) for ck, v in complexes_from_raw().items()
            if ck not in cache or (not cache[ck].get("ok") and cache[ck].get("tried", "") < retry_before)]
    # 역 좌표가 없던 예전 캐시는 역 정보만 다시 조회 (지도 표시용)
    patch = [ck for ck, v in cache.items() if v.get("ok") and "st_lat" not in v]
    for ck in patch:
        try:
            st = k.nearest_station(cache[ck]["lat"], cache[ck]["lng"])
        except (RuntimeError, requests.RequestException) as e:
            print(e)
            break
        cache[ck].update(st or {"st_lat": None, "st_lng": None})
    if patch:
        print(f"역 좌표 보강 {len(patch)}곳")
    cap = int(cfg.get("geo_max_per_run", 2500))
    if len(todo) > cap:
        print(f"위치 조회 대상 {len(todo)}곳 중 거래 많은 {cap}곳만 이번에 조회 (나머지는 다음 실행에서)")
        todo = todo[:cap]
    print(f"위치 조회 대상 {len(todo)}곳 (캐시 {len(cache)}곳)")
    for i, (ck, (sgg, umd, jibun, apt)) in enumerate(todo, 1):
        try:
            cache[ck] = lookup(k, sgg, umd, jibun, apt, base)
        except RuntimeError as e:
            print(e)
            break
        except requests.RequestException as e:
            print(f"{apt}: {e}")
            continue
        if i % 50 == 0:
            path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        time.sleep(0.05)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"위치 정보 {sum(1 for v in cache.values() if v.get('ok'))}곳 보유")
    return 0


if __name__ == "__main__":
    sys.exit(main())
