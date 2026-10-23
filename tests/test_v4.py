"""v4 테스트: 빌라 파싱, 미승인 API 건너뛰기·이어받기, 매매 추천. 실행: python tests/test_v4.py"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "collector"), str(ROOT / "model")]
import fetch_rent as fr  # noqa: E402
import rank_sale  # noqa: E402

VILLA = """<response><header><resultCode>000</resultCode></header><body><items>
<item><mhouseNm>해피하우스</mhouseNm><houseType>다세대</houseType><buildYear>2019</buildYear><dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>3</dealDay>
<deposit>45,000</deposit><monthlyRent>0</monthlyRent><excluUseAr>82.5</excluUseAr><floor>3</floor><umdNm>화곡동</umdNm><jibun>1024-5</jibun>
<contractTerm>26.10~28.10</contractTerm><contractType>신규</contractType></item></items><totalCount>1</totalCount></body></response>"""
NOT_APPROVED = "<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"


class Resp:
    def __init__(self, t): self.text, self.status_code = t, 200
    def raise_for_status(self): pass


def test():
    rows, _ = fr.parse(VILLA, "강서구", "빌라")
    r = rows[0]
    assert r["kind"] == "빌라" and r["apt"] == "해피하우스 (1024-5)" and r["deposit_man"] == 45000 and r["contract_term"] == "26.10~28.10"

    # 아파트는 응답, 빌라는 미승인 → 아파트만 저장, 빌라는 상태에 '미완료'로 남아 다음에 이어받음
    calls = []
    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return Resp(NOT_APPROVED if "RHRent" in url else VILLA.replace("mhouseNm", "aptNm"))
    fr.requests.get = fake_get
    with tempfile.TemporaryDirectory() as td:
        fr.STATE = Path(td) / "state.json"
        out = Path(td) / "rent.csv"
        cfg = {"regions": {"11500": "강서구"}, "kinds": ["아파트", "빌라"], "min_area_m2": 80, "months_back": 2}
        n, _ = fr.collect("k", cfg, fr.RENT_API, out, fr.FIELDS, "rent", 2, fr.keep, "전세")
        st = json.loads(fr.STATE.read_text(encoding="utf-8"))["rent"]
        assert n == 1 and st.get("아파트|강서구") is True and not st.get("빌라|강서구"), st
        assert sum("RHRent" in u for u in calls) == 1, "미승인 API는 한 번 확인 후 바로 중단"

    sales = [{"kind": "아파트", "sgg": "강서구", "umd": "마곡동", "apt": "A", "jibun": "1", "build_year": "2014",
              "area_m2": "84.9", "floor": "5", "deal_date": d, "deposit_man": p}
             for d, p in [("2025-03-10", "120000"), ("2025-06-10", "122000"), ("2026-05-10", "130000"), ("2026-08-10", "132000")]]
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg["regulated_sgg"], cfg["toheo_kinds"] = ["강서구"], ["아파트"]
    it = rank_sale.build(sales, cfg, date(2026, 10, 23), {}, {"강서구-마곡동-A-84": 8.3})[0]
    assert it["price_eok"] == 13.1 and it["jeonse_ratio"] == round(8.3 / 13.1, 3) and it["gap_eok"] == 4.8
    assert it["growth_1y"] > 0.05 and it["toheo"] is True and it["area"] == "seoul_west"
    print("OK: 빌라 파싱·미승인 API 건너뛰기/이어받기·매매가·전세가율·갭·1년 상승률 통과")


if __name__ == "__main__":
    test()
