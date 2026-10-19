"""이사 시기·예상 매물 모델 테스트. 실행: python tests/test_supply.py"""
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import supply  # noqa: E402


def row(term, ctype="신규", rr="", deal="2025-04-10", dep="80000"):
    return {"sgg": "강서구", "umd": "마곡동", "apt": "A단지", "jibun": "1", "build_year": "2014", "area_m2": "84.9",
            "floor": "5", "deal_date": deal, "deposit_man": dep, "monthly_man": "0", "contract_type": ctype,
            "contract_term": term, "use_rr": rr}


def test():
    assert supply.contract_end(row("25.04~27.04")) == "2027-04"
    assert supply.contract_end(row("")) == "2027-04"          # 계약기간 없으면 계약일+24개월
    rows = [row("25.04~27.04"), row("25.05~27.05", "갱신", "사용", "2025-05-02"),
            row("26.01~28.01", deal="2026-01-05"), row("26.02~28.02", "갱신", deal="2026-02-05")]
    out = supply.build(rows, date(2026, 10, 19), {"listing_lead_months": 2, "renewed_leave_prob": 0.7, "horizon_months": 18})
    gid = "강서구-마곡동-A단지-84"
    it = out["items"][gid]
    m = out["months"]
    assert it["exp"][m.index("2027-04")] == 1 and it["exp"][m.index("2027-05")] == 1
    # 신규 만기(4월) → 2월에 매물, 갱신권 사용 만기(5월) → 3월에 0.7건
    assert it["list"][m.index("2027-03")] == 0.7, it["list"]
    assert 0 < it["list"][m.index("2027-02")] < 1
    print("OK: 계약 만기 월·예상 매물(신규/갱신 구분)·매물 선행 2개월 통과")


if __name__ == "__main__":
    test()
