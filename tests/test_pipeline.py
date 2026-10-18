"""API 응답 파싱과 추천 계산을 모의 데이터로 검증한다. 실행: python tests/test_pipeline.py"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "collector"), str(ROOT / "model")]
import fetch_rent  # noqa: E402
import rank  # noqa: E402

XML = """<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
<body><items>
<item><aptNm>마곡엠밸리7단지</aptNm><buildYear>2014</buildYear><dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>12</dealDay>
<deposit>84,000</deposit><monthlyRent>0</monthlyRent><excluUseAr>84.97</excluUseAr><floor>9</floor><umdNm>마곡동</umdNm><jibun>800</jibun><contractType>신규</contractType></item>
<item><aptNm>마곡엠밸리7단지</aptNm><buildYear>2014</buildYear><dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>20</dealDay>
<deposit>30,000</deposit><monthlyRent>150</monthlyRent><excluUseAr>84.97</excluUseAr><floor>3</floor><umdNm>마곡동</umdNm><jibun>800</jibun><contractType></contractType></item>
<item><aptNm>마곡엠밸리15단지</aptNm><buildYear>2014</buildYear><dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>3</dealDay>
<deposit>56,000</deposit><monthlyRent>0</monthlyRent><excluUseAr>59.9</excluUseAr><floor>5</floor><umdNm>마곡동</umdNm><jibun>790</jibun><contractType></contractType></item>
</items><numOfRows>1000</numOfRows><pageNo>1</pageNo><totalCount>3</totalCount></body></response>"""


def test():
    rows, total = fetch_rent.parse(XML, "강서구")
    assert total == 3 and len(rows) == 3
    assert rows[0]["deposit_man"] == 84000 and rows[0]["deal_date"] == "2026-09-12"
    cfg = {"min_area_m2": 80, "jeonse_only": True, "budget_eok": 8.0,
           "complex_meta": {"마곡엠밸리7단지": {"station": "마곡나루", "walk_min": 6, "lines": ["9"]}},
           "station_minutes_from_base": {"마곡나루": 0}}
    kept = [r for r in rows if fetch_rent.keep(r, cfg)]
    assert len(kept) == 1, "월세와 59㎡는 걸러져야 함"
    str_rows = [{k: str(v) for k, v in r.items()} for r in kept]
    items = rank.build(str_rows, cfg, rank.DEFAULT_W, date(2026, 10, 18))
    assert len(items) == 1 and items[0]["price_eok"] == 8.4 and items[0]["pyeong"] == 34
    w = rank.update_weights(rank.DEFAULT_W, items, {items[0]["id"]: "like"})
    assert set(w) == set(rank.DEFAULT_W)
    assert fetch_rent.months_back(3, date(2026, 1, 5)) == ["202601", "202512", "202511"]
    print("OK: 파싱·필터·점수·학습 모두 통과")


if __name__ == "__main__":
    test()
