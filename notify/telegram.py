"""텔레그램으로 오늘의 TOP 목록을 보낸다.

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 가 둘 다 있어야 보낸다.
토큰만 있고 CHAT_ID가 없으면, 봇에게 온 메시지에서 chat id를 찾아 로그에 출력한다.
직접 실행하면 바로 보내고, 정기 발송은 dispatch.py 가 설정에 따라 호출한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PAGES_URL, load_rec, pick_top, place, prev_ids  # noqa: E402


def compose(rec: dict, prev: set[str], top: list[dict] | None = None) -> str:
    top = top if top is not None else pick_top(rec["items"])
    lines = [f"🏠 전세 레이더 · {rec['generated_at'][:10]} 추천", f"예산 {rec['budget_eok']}억 · 34평형↑", ""]
    area, n = None, 0
    for it in top:
        if it.get("area_name") and it.get("area") != area:
            area, n = it.get("area"), 0
            lines.append(f"[{it['area_name']}]")
        n += 1
        new = " 🆕" if it["id"] not in prev else ""
        st = f" · {it['station']}역 도보 {it['walk_min']}분" if it.get("station") and it.get("walk_min") else ""
        lines.append(f"{n}. {it['name']} ({place(it)}){new}")
        lines.append(f"   {it['price_eok']:.1f}억 · {it['built']}년 · {it['pyeong']}평형{st} · 점수 {it['score']}")
    if not top:
        lines.append("오늘은 조건에 맞는 단지가 없습니다.")
    lines += ["", PAGES_URL]
    return "\n".join(lines)


def send(text: str) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN 없음 — 텔레그램을 건너뜁니다.")
        return False
    api = f"https://api.telegram.org/bot{token}"
    if not chat:
        ups = requests.get(f"{api}/getUpdates", timeout=15).json().get("result", [])
        ids = {u["message"]["chat"]["id"] for u in ups if "message" in u}
        print("TELEGRAM_CHAT_ID 가 없습니다. 봇에게 아무 메시지나 보낸 뒤 다시 실행하세요.")
        print("찾은 chat id:", ", ".join(map(str, ids)) or "(없음)")
        return False
    try:
        r = requests.post(f"{api}/sendMessage", json={"chat_id": chat, "text": text,
                                                       "disable_web_page_preview": True}, timeout=15)
    except requests.RequestException as e:
        print("텔레그램 전송 실패:", e)
        return False
    print("텔레그램 전송:", r.status_code, r.text[:120] if r.status_code != 200 else "OK")
    return r.status_code == 200


def main() -> int:
    send(compose(load_rec(), prev_ids()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
