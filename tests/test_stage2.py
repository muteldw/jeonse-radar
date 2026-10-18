"""2단계(카카오 위치·텔레그램) 모의 테스트. 실행: python tests/test_stage2.py"""
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "collector"), str(ROOT / "model"), str(ROOT / "notify")]
import geo, rank, telegram  # noqa: E402


class Resp:
    def __init__(self, j, code=200): self._j, self.status_code, self.text = j, code, ""
    def json(self): return self._j
    def raise_for_status(self): pass


class FakeSession:
    def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("address.json"):
            return Resp({"documents": [{"x": "126.8301", "y": "37.5650"}]})
        code = params.get("category_group_code")
        if code == "SW8":
            return Resp({"documents": [
                {"place_name": "마곡나루역 9호선", "distance": "420"},
                {"place_name": "마곡나루역 공항철도", "distance": "450"},
                {"place_name": "양천향교역 9호선", "distance": "1300"}]})
        return Resp({"documents": [], "meta": {"total_count": {"SC4": 2, "PS3": 6, "MT1": 1, "HP8": 14}[code]}})


def test():
    k = geo.Kakao("x", session=FakeSession())
    g = geo.lookup(k, "강서구", "마곡동", "800", "마곡엠밸리7단지", {"lat": 37.5667, "lng": 126.8272})
    assert g["station"] == "마곡나루" and g["lines"] == ["9호선", "공항철도"] and g["walk_min"] == 6
    assert g["infra"]["대형마트"] == 1 and 0.2 < g["base_km"] < 0.5
    rows = [{"sgg": "강서구", "umd": "마곡동", "apt": "마곡엠밸리7단지", "jibun": "800", "build_year": "2014",
             "area_m2": "84.9", "floor": "5", "deal_date": f"2026-0{m}-10", "deposit_man": "82000",
             "monthly_man": "0", "contract_type": "신규"} for m in range(3, 10)]
    cfg = {"budget_eok": 8.0, "min_area_m2": 80}
    no_geo = rank.build(rows, cfg, rank.DEFAULT_W, date(2026, 10, 18))[0]
    with_geo = rank.build(rows, cfg, rank.DEFAULT_W, date(2026, 10, 18), {"강서구|마곡동|마곡엠밸리7단지": g})[0]
    assert with_geo["station"] == "마곡나루" and with_geo["score"] > no_geo["score"]
    msg = telegram.compose({"generated_at": "2026-10-19T06:05", "budget_eok": 8.0, "items": [with_geo]}, set())
    assert "마곡엠밸리7단지" in msg and "🆕" in msg and "도보 6분" in msg
    print("OK: 위치·역·인프라·점수·알림 메시지 통과")
    print(msg)


if __name__ == "__main__":
    test()
