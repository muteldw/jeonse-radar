"""매일 아침 TOP 5를 지메일로 보낸다.

필요한 Secret
  GMAIL_USER          보내는 지메일 주소 (예: yourname@gmail.com)
  GMAIL_APP_PASSWORD  구글 '앱 비밀번호' 16자리 (일반 비밀번호 아님)
  MAIL_TO             받는 주소, 쉼표로 여러 개 가능 (없으면 GMAIL_USER로 보냄)
"""
from __future__ import annotations

import html
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PAGES_URL, load_rec, pick_top, prev_ids  # noqa: E402


def build(rec: dict, prev: set[str]) -> tuple[str, str, str]:
    top = pick_top(rec["items"])
    day = rec["generated_at"][:10]
    subject = f"[전세 레이더] {day} 아침 추천 TOP {len(top)}"
    if top:
        subject += f" · 1위 {top[0]['name']} {top[0]['price_eok']:.1f}억"
    text_lines, rows = [], []
    for n, it in enumerate(top, 1):
        new = it["id"] not in prev
        st = f"{it['station']}역 도보 {it['walk_min']}분" if it.get("station") and it.get("walk_min") else "-"
        text_lines.append(f"{n}. {it['name']} ({it['umd']}){' [신규]' if new else ''} "
                          f"{it['price_eok']:.1f}억 · {it['built']}년 · {it['pyeong']}평형 · {st} · 점수 {it['score']}")
        badge = ('<span style="background:#2f7d4f;color:#fff;border-radius:9px;padding:1px 7px;'
                 'font-size:11px;margin-left:6px">NEW</span>') if new else ""
        map_url = (f"https://map.kakao.com/link/map/{html.escape(it['name'])},{it['lat']},{it['lng']}"
                   if it.get("lat") else f"https://map.kakao.com/?q={html.escape(it['name'])}")
        rows.append(
            f'<tr><td style="padding:10px 8px;border-bottom:1px solid #e3e0d6;color:#a8954f;font-weight:700">{n}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #e3e0d6"><a href="{map_url}" '
            f'style="color:#1f2328;font-weight:700;text-decoration:none">{html.escape(it["name"])}</a>{badge}'
            f'<div style="color:#6b6f63;font-size:12px">{html.escape(it["sgg"])} {html.escape(it["umd"])} · '
            f'{it["built"]}년 · {it["pyeong"]}평형 · {html.escape(st)}</div></td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #e3e0d6;text-align:right;white-space:nowrap">'
            f'<b>{it["price_eok"]:.1f}억</b><div style="color:#6b6f63;font-size:12px">점수 {it["score"]}</div></td></tr>')
    text = (f"전세 레이더 {day} 아침 추천 (예산 {rec['budget_eok']}억, 34평형 이상)\n\n"
            + ("\n".join(text_lines) or "오늘은 조건에 맞는 단지가 없습니다.") + f"\n\n전체 보기: {PAGES_URL}")
    body = (
        '<div style="font-family:-apple-system,\'Apple SD Gothic Neo\',Arial,sans-serif;max-width:560px;color:#1f2328">'
        f'<h2 style="margin:0 0 4px">전세 레이더 <span style="background:#a8954f;color:#fff;border-radius:9px;'
        f'padding:1px 8px;font-size:13px">9</span></h2>'
        f'<div style="color:#6b6f63;font-size:13px;margin-bottom:12px">{day} 아침 추천 · 예산 {rec["budget_eok"]}억 · '
        '34평형 이상 · 최근 신규 전세 실거래 기준</div>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px">{"".join(rows)}</table>'
        f'<p style="margin-top:16px"><a href="{PAGES_URL}" style="background:#a8954f;color:#fff;padding:9px 16px;'
        'border-radius:8px;text-decoration:none;font-size:14px">전체 추천 보기</a></p>'
        '<p style="color:#9a9c92;font-size:11px">국토교통부 실거래가·카카오 로컬 데이터 기반 자동 추천입니다. '
        '계약 전 등기부등본과 현장 확인이 필요합니다.</p></div>')
    return subject, text, body


def main() -> int:
    user = (os.environ.get("GMAIL_USER") or "").strip()
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
    if not user or not pw:
        print("GMAIL_USER / GMAIL_APP_PASSWORD 없음 — 메일 알림을 건너뜁니다.")
        return 0
    to = [a.strip() for a in (os.environ.get("MAIL_TO") or user).split(",") if a.strip()]
    subject, text, body = build(load_rec(), prev_ids())
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, f"전세 레이더 <{user}>", ", ".join(to)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pw)
            s.sendmail(user, to, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        print("지메일 로그인 실패 — 일반 비밀번호가 아니라 16자리 '앱 비밀번호'를 넣었는지 확인하세요.")
        return 0
    print(f"메일 전송 완료 → {len(to)}명")
    return 0


if __name__ == "__main__":
    sys.exit(main())
