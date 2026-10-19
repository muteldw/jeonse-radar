"""알림 발송기 — 매시 정각에 실행되어 config/notify.json 에 따라 '지금 보낼 대상'에게만 보낸다.

schedule 종류
  daily     매일 hour 시
  weekdays  월~금 hour 시
  weekly    days(0=월 … 6=일)에 해당하는 요일 hour 시
  new_only  hour 시에 확인해서, 그 대상이 마지막으로 받은 TOP 목록에 없던 단지가 있을 때만

메일 받는 사람: Secret MAIL_RECIPIENTS = "본인=a@gmail.com, 배우자=b@naver.com"
                 (없으면 '본인' = MAIL_TO 또는 GMAIL_USER)
보낸 기록: data/sent_log.json  {target_id: {"date": "YYYY-MM-DD", "ids": [...], "at": "..."}}
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import email_alert  # noqa: E402
import telegram  # noqa: E402
from common import ROOT, load_rec, pick_top  # noqa: E402

KST = timezone(timedelta(hours=9))
CFG = ROOT / "config" / "notify.json"
LOG = ROOT / "data" / "sent_log.json"


def recipients() -> dict[str, str]:
    raw = os.environ.get("MAIL_RECIPIENTS") or ""
    out = {}
    for part in raw.replace("\n", ",").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and "@" in v:
                out[k.strip()] = v.strip()
    if "본인" not in out:
        me = (os.environ.get("MAIL_TO") or os.environ.get("GMAIL_USER") or "").split(",")[0].strip()
        if me:
            out["본인"] = me
    return out


def is_due(t: dict, now: datetime, log: dict, top_ids: list[str], force: bool) -> tuple[bool, str]:
    if not t.get("enabled", True):
        return False, "꺼짐"
    last = log.get(t["id"], {})
    if force:
        return True, "수동 실행"
    if int(t.get("hour", 7)) != now.hour:
        return False, f"{t.get('hour', 7)}시 아님"
    if last.get("date") == now.date().isoformat():
        return False, "오늘 이미 보냄"
    s, wd = t.get("schedule", "daily"), now.weekday()
    if s == "weekdays" and wd >= 5:
        return False, "주말"
    if s == "weekly" and wd not in [int(d) for d in t.get("days", [])]:
        return False, "요일 아님"
    if s == "new_only" and not (set(top_ids) - set(last.get("ids", []))):
        return False, "새 단지 없음"
    return True, s


def main() -> int:
    force = os.environ.get("FORCE_SEND", "").lower() in ("1", "true", "yes")
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if not cfg.get("enabled", True) and not force:
        print("전체 알림이 꺼져 있습니다.")
        return 0
    now = datetime.now(KST)
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    rec = load_rec()
    top = pick_top(rec["items"], int(cfg.get("top_n", 5)))
    top_ids = [i["id"] for i in top]
    rcpt = recipients()
    sent = 0
    for t in cfg.get("targets", []):
        due, why = is_due(t, now, log, top_ids, force)
        if not due:
            print(f"- {t['id']}: 건너뜀 ({why})")
            continue
        prev = set(log.get(t["id"], {}).get("ids", []))
        ok = False
        if t["channel"] == "telegram":
            ok = telegram.send(telegram.compose(rec, prev, top))
        elif t["channel"] == "email":
            addr = rcpt.get(t.get("recipient", "본인"))
            if not addr:
                print(f"- {t['id']}: '{t.get('recipient')}' 주소가 MAIL_RECIPIENTS에 없습니다.")
                continue
            ok = email_alert.send([addr], rec, prev, top)
        print(f"- {t['id']}: {'보냄' if ok else '실패'} ({why})")
        if ok:
            sent += 1
            log[t["id"]] = {"date": now.date().isoformat(), "ids": top_ids, "at": now.isoformat(timespec="minutes")}
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    # 화면에서 '마지막 발송'을 보여주기 위해 공개 데이터에도 시각만 남긴다(주소·별칭 제외)
    pub = {k: v["at"] for k, v in log.items()}
    (ROOT / "web" / "data" / "sent_status.json").write_text(json.dumps(pub, ensure_ascii=False), encoding="utf-8")
    print(f"발송 {sent}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
