"""고가 이상치(펜트하우스·대형 평형 혼입) 제외 검증. 실행: python tests/test_spikes.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "model")]
import rank  # noqa: E402


def d(date, man):
    return {"deal_date": date, "deposit_man": str(man)}


def test():
    # 29억 근처 거래 사이에 섞인 55억 한 건은 빠진다
    deals = [d(f"2026-0{m}-01", p) for m, p in enumerate([290000, 285000, 300000, 550000, 295000, 290000, 280000], 1)]
    kept = rank.drop_price_spikes(deals)
    assert [int(x["deposit_man"]) for x in kept] == [290000, 285000, 300000, 295000, 290000, 280000]

    # 꾸준히 오르는 단지(8억대 → 13.5억)는 그대로 남는다
    rising = [d(f"2026-0{m}-01", p) for m, p in enumerate([82000, 88000, 82000, 89000, 107000, 135000, 97000, 135000], 1)]
    assert len(rank.drop_price_spikes(rising)) == len(rising)

    # 거래가 적으면 판단하지 않는다
    few = [d("2026-01-01", 50000), d("2026-02-01", 50000), d("2026-03-01", 200000)]
    assert rank.drop_price_spikes(few) == few
    print("ok")


if __name__ == "__main__":
    test()
