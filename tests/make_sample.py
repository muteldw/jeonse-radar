"""첫 실행 전 화면 확인용 예시 recommend.json 생성 (sample: true 표시)."""
import json, random, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import rank  # noqa: E402

random.seed(7)
SPEC = [("강서구", "마곡동", "마곡엠밸리7단지", 2014, 84.9, 8.3), ("강서구", "마곡동", "마곡엠밸리6단지", 2014, 84.9, 7.8),
        ("강서구", "마곡동", "마곡엠밸리2단지", 2014, 84.9, 7.1), ("강서구", "가양동", "강서한강자이", 2010, 84.9, 6.7),
        ("강서구", "내발산동", "우장산아이파크이편한세상", 2008, 84.9, 6.2), ("양천구", "목동", "목동신시가지7단지", 1986, 101.2, 7.4),
        ("강서구", "마곡동", "마곡힐스테이트마스터", 2017, 99.0, 9.6)]
rows = []
for sgg, umd, apt, by, ar, base in SPEC:
    for k in range(20):
        y, m = 2024 + (k + 10) // 12, (k + 10) % 12 + 1
        if (y, m) > (2026, 9):
            break
        price = base * (0.92 + 0.08 * k / 20) + random.uniform(-.15, .15)
        rows.append({"sgg": sgg, "umd": umd, "apt": apt, "jibun": "0", "build_year": str(by), "area_m2": str(ar),
                     "floor": "5", "deal_date": f"{y}-{m:02d}-15", "deposit_man": str(int(price * 10000)), "monthly_man": "0", "contract_type": ""})
cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
items = rank.build(rows, cfg, rank.DEFAULT_W, date(2026, 10, 18))
out = {"generated_at": "2026-10-18T22:50", "budget_eok": cfg["budget_eok"], "weights": rank.DEFAULT_W,
       "source": "예시 데이터 (실제 시세 아님)", "sample": True, "items": items}
p = ROOT / "web" / "data" / "recommend.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(items), "items")
