"""알림 공통: 오늘 TOP 목록과 '어제 대비 새로 들어온 단지' 판별."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAST = ROOT / "data" / "last_top.json"
PAGES_URL = os.environ.get("PAGES_URL", "https://muteldw.github.io/jeonse-radar/")


def load_rec(areas: list[str] | None = None) -> dict:
    """메타(recommend.json) + 생활권별 파일(rec/<area>.json)을 합친다. areas가 비면 전체."""
    meta = json.loads((ROOT / "web" / "data" / "recommend.json").read_text(encoding="utf-8"))
    if "items" in meta:  # 예전 형식
        return meta
    if areas is None:
        try:
            areas = json.loads((ROOT / "config" / "notify.json").read_text(encoding="utf-8")).get("areas") or None
        except (OSError, ValueError):
            areas = None
    items = []
    for k in (areas or list(meta.get("areas", {}))):
        f = ROOT / "web" / "data" / meta.get("folder", "rec") / f"{k}.json"
        if f.exists():
            items += json.loads(f.read_text(encoding="utf-8")).get("items", [])
    order = list(meta.get("areas", {}))
    items.sort(key=lambda i: (order.index(i["area"]) if i.get("area") in order else 99,
                              not i.get("within_budget"), -i.get("score", 0)))
    return {**meta, "items": items}


def pick_top(items: list[dict], n: int = 5) -> list[dict]:
    """생활권(서울 강서·양천, 안양 …)마다 상위 n곳. 한 지역이 다른 지역을 밀어내지 않게 한다."""
    ok = [i for i in items if i.get("within_budget") and i.get("deals_12m", 0) >= 3]
    out, cnt = [], {}
    for i in ok:
        a = i.get("area") or "_"
        if cnt.get(a, 0) < n:
            out.append(i)
            cnt[a] = cnt.get(a, 0) + 1
    order = list(dict.fromkeys(i.get("area") or "_" for i in ok))
    return sorted(out, key=lambda i: order.index(i.get("area") or "_"))


def place(it: dict) -> str:
    """서울은 동 이름, 경기는 '안양 평촌동'처럼 시 이름을 붙인다."""
    sgg = it.get("sgg", "")
    return f"{sgg.split()[0].removesuffix('시')} {it['umd']}" if "시 " in sgg else it["umd"]


def prev_ids() -> set[str]:
    return set(json.loads(LAST.read_text(encoding="utf-8"))) if LAST.exists() else set()


def save_top() -> None:
    """모든 알림을 보낸 뒤 실행 — 내일 🆕 판별 기준을 저장."""
    LAST.write_text(json.dumps([i["id"] for i in pick_top(load_rec()["items"])], ensure_ascii=False),
                    encoding="utf-8")
    print("오늘 TOP 저장 완료")


if __name__ == "__main__" and sys.argv[1:] == ["save"]:
    save_top()
