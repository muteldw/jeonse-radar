"""알림 주기·켜기/끄기·받는 사람 판정 테스트. 실행: python tests/test_notify.py"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "notify"))
import dispatch  # noqa: E402

KST = timezone(timedelta(hours=9))
mon7 = datetime(2026, 10, 19, 7, 5, tzinfo=KST)   # 월요일 07:05
sat7 = datetime(2026, 10, 24, 7, 5, tzinfo=KST)   # 토요일


def due(t, now, log=None, ids=("a",), force=False):
    return dispatch.is_due({"id": "x", **t}, now, log or {}, list(ids), force)[0]


def test():
    assert due({"schedule": "daily", "hour": 7}, mon7)
    assert not due({"schedule": "daily", "hour": 8}, mon7)
    assert not due({"schedule": "daily", "hour": 7, "enabled": False}, mon7)
    assert not due({"schedule": "daily", "hour": 7}, mon7, {"x": {"date": "2026-10-19"}})
    assert due({"schedule": "weekdays", "hour": 7}, mon7) and not due({"schedule": "weekdays", "hour": 7}, sat7)
    assert due({"schedule": "weekly", "days": [5], "hour": 7}, sat7) and not due({"schedule": "weekly", "days": [5], "hour": 7}, mon7)
    assert not due({"schedule": "new_only", "hour": 7}, mon7, {"x": {"ids": ["a"]}}, ["a"])
    assert due({"schedule": "new_only", "hour": 7}, mon7, {"x": {"ids": ["a"]}}, ["a", "b"])
    assert due({"schedule": "daily", "hour": 3}, mon7, force=True)
    assert not due({"schedule": "daily", "hour": 3, "enabled": False}, mon7, force=True)
    os.environ["MAIL_RECIPIENTS"] = "본인=me@gmail.com, 배우자 = wife@naver.com, 잘못됨=noat"
    r = dispatch.recipients()
    assert r == {"본인": "me@gmail.com", "배우자": "wife@naver.com"}, r
    print("OK: 주기(매일·평일·매주·새 단지)·켜기/끄기·수동 발송·받는 사람 판정 통과")


if __name__ == "__main__":
    test()
