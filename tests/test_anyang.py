"""안양 확장 테스트: 생활권별 기준역, 규제/비규제 구분, 경기 주소 조회. 실행: python tests/test_anyang.py"""
import json
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "model"), str(ROOT / "collector")]
import geo, rank  # noqa: E402


def rows(sgg, umd, apt, dep):
    return [{"sgg": sgg, "umd": umd, "apt": apt, "jibun": "1", "build_year": "2012", "area_m2": "84.9", "floor": "7",
             "deal_date": f"2026-0{m}-10", "deposit_man": str(dep), "monthly_man": "0", "contract_type": "신규"} for m in range(3, 10)]


def test():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["regulated_sgg"] = json.loads((ROOT / "config/loan_rules.json").read_text(encoding="utf-8"))["regulated_sgg"]
    data = rows("안양시 동안구", "평촌동", "평촌A", 62000) + rows("안양시 만안구", "안양동", "만안B", 48000)
    g = {"안양시 동안구|평촌동|평촌A": {"ok": True, "lat": 37.3920, "lng": 126.9520, "station": "범계", "walk_min": 5},
         "안양시 만안구|안양동|만안B": {"ok": True, "lat": 37.4010, "lng": 126.9220, "station": "안양", "walk_min": 8}}
    items = {i["name"]: i for i in rank.build(data, cfg, rank.DEFAULT_W, date(2026, 10, 23), g)}
    a, b = items["평촌A"], items["만안B"]
    assert a["area"] == "anyang" and a["base_name"] == "범계" and a["base_km"] < 0.5, a
    assert a["regulated"] is True and b["regulated"] is False
    assert a["features"]["station"] > 0.6, "안양 단지가 마곡나루 기준으로 감점되면 안 됨"

    class S:
        def __init__(self): self.q = []
        def get(self, url, headers=None, params=None, timeout=None):
            self.q.append(params.get("query"))
            class R:
                status_code = 200
                def json(_): return {"documents": [{"x": "126.95", "y": "37.39"}]}
                def raise_for_status(_): pass
            return R()
    s = S()
    geo.Kakao("x", session=s).locate("안양시 동안구", "평촌동", "934", "평촌A")
    assert s.q[0] == "경기 안양시 동안구 평촌동 934", s.q
    print("OK: 안양 생활권 기준역(범계)·규제(동안)/비규제(만안)·경기 주소 조회 통과")


if __name__ == "__main__":
    test()
