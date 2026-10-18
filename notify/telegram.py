"""매일 아침 텔레그램으로 오늘의 TOP 5를 보낸다.

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 가 둘 다 있어야 보낸다.
토큰만 있고 CHAT_ID가 없으면, 봇에게 온 메시지에서 chat id를 찾아 로그에 출력한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PAGES_URL, load_rec, pick_top, prev_ids  # noqa: E402


def compose(rec: dict, prev_ids: set[str]) -> str:
    top = pick_top(rec["items"])
    lines = [f"🏠 전세 레이더 · {rec['generated_at'][:10]} 아침 추천", f"예산 {rec['budget_eok']}억 · 34평형↑", ""]
    for n, it in enumerate(top, 1):
        new = " 🆕" if it["id"] not in prev_ids else ""
        st = f" · {it['station']}역 도보 {it['walk_min']}분" if it.get("station") and it.get("walk_min") else ""
        lines.append(f"{n}. {it['name']} ({it['umd']}){new}")
        lines.append(f"   {it['price_eok']:.1f}억 · {it['built']}년 · {it['pyeong']}평형{st} · 점수 {it['score']}")
    lines += ["", PAGES_URL]
    return "\n".join(lines)


def main() -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN 없음 — 알림을 건너뜁니다.")
        return 0
    api = f"https://api.telegram.org/bot{token}"
    if not chat:
        ups = requests.get(f"{api}/getUpdates", timeout=15).json().get("result", [])
        ids = {u["message"]["chat"]["id"] for u in ups if "message" in u}
        print("TELEGRAM_CHAT_ID 가 없습니다. 봇에게 아무 메시지나 보낸 뒤 다시 실행하세요.")
        print("찾은 chat id:", ", ".join(map(str, ids)) or "(없음)")
        return 0
    msg = compose(load_rec(), prev_ids())
    r = requests.post(f"{api}/sendMessage", json={"chat_id": chat, "text": msg,
                                                   "disable_web_page_preview": True}, timeout=15)
    print("텔레그램 전송:", r.status_code, r.text[:120] if r.status_code != 200 else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
