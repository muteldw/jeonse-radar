"""알림 공통: 오늘 TOP 목록과 '어제 대비 새로 들어온 단지' 판별."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAST = ROOT / "data" / "last_top.json"
PAGES_URL = os.environ.get("PAGES_URL", "https://muteldw.github.io/jeonse-radar/")


def load_rec() -> dict:
    return json.loads((ROOT / "web" / "data" / "recommend.json").read_text(encoding="utf-8"))


def pick_top(items: list[dict], n: int = 5) -> list[dict]:
    return [i for i in items if i.get("within_budget") and i.get("deals_12m", 0) >= 3][:n]


def prev_ids() -> set[str]:
    return set(json.loads(LAST.read_text(encoding="utf-8"))) if LAST.exists() else set()


def save_top() -> None:
    """모든 알림을 보낸 뒤 실행 — 내일 🆕 판별 기준을 저장."""
    LAST.write_text(json.dumps([i["id"] for i in pick_top(load_rec()["items"])], ensure_ascii=False),
                    encoding="utf-8")
    print("오늘 TOP 저장 완료")


if __name__ == "__main__" and sys.argv[1:] == ["save"]:
    save_top()
