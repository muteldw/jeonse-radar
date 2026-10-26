"""임시 거처 시세 계산 테스트 (모의 월세 데이터)."""
import csv, json, shutil, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import bridge  # noqa: E402

assert bridge.term_months("26.10~27.04") == 6
assert bridge.term_months("26.10~28.10") == 24
assert bridge.term_months("") is None
assert bridge.band_of(33) == "one" and bridge.band_of(59.9) == "two" and bridge.band_of(84) == "three" and bridge.band_of(101) == "four"

tmp = Path(tempfile.mkdtemp())
(tmp / "data").mkdir(); (tmp / "web" / "data").mkdir(parents=True)
from datetime import date
d = date.today().isoformat()
F = ["kind","sgg","umd","apt","jibun","build_year","area_m2","floor","deal_date","deposit_man","monthly_man","contract_type","contract_term","use_rr"]
rows = [
 ["오피스텔","강서구","마곡동","마곡A오피스텔","1",2018,26,5,d,1000,90,"신규","26.10~27.04",""],
 ["오피스텔","강서구","마곡동","마곡A오피스텔","1",2018,27,7,d,1000,100,"신규","26.10~27.10",""],
 ["아파트","강서구","마곡동","B아파트","2",2015,59,3,d,10000,150,"신규","26.10~28.10",""],
 ["아파트","강서구","마곡동","B아파트","2",2015,84,3,d,30000,0,"신규","26.10~28.10",""],   # 전세 → 제외
]
with (tmp/"data"/"bridge_raw.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(F); w.writerows(rows)
(tmp/"data"/"geo.json").write_text(json.dumps({"강서구|마곡동|마곡A오피스텔":{"ok":True,"lat":37.56,"lng":126.82},
                                               "강서구|마곡동|B아파트":{"ok":True,"lat":37.57,"lng":126.83}}), encoding="utf-8")
bridge.ROOT = tmp
bridge.main()
out = json.loads((tmp/"web"/"data"/"bridge.json").read_text(encoding="utf-8"))
assert out["rows"] == 3, out["rows"]
o = out["summary"]["오피스텔"]["one"]
assert o["n"] == 2 and o["short"] == 1 and o["mon"] == 95, o
assert len(out["places"]) == 2
shutil.rmtree(tmp)
print("bridge OK")
