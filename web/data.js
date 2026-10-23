/* 전세 레이더 공통 데이터 로더 — 생활권별 파일을 필요할 때만 내려받는다. */
const JR = {
  _m: {}, _c: {},
  meta(name = "recommend.json") {
    if (!this._m[name]) this._m[name] = fetch("data/" + name, { cache: "no-store" }).then(r => { if (!r.ok) throw new Error(name); return r.json(); });
    return this._m[name];
  },
  file(folder, area) {
    const k = folder + "/" + area;
    if (!this._c[k]) this._c[k] = fetch(`data/${folder}/${area}.json`, { cache: "no-store" }).then(r => r.ok ? r.json() : { items: [] }).catch(() => ({ items: [] }));
    return this._c[k];
  },
  /* 여러 생활권의 items 배열을 합친다 (rec/sale) */
  async items(folder, areas) {
    const ds = await Promise.all(areas.map(a => this.file(folder, a)));
    return [].concat(...ds.map(d => d.items || []));
  },
  /* 예상 매물: items 객체와 지역 합계를 합친다 */
  async supply(areas) {
    const [base, ...ds] = await Promise.all([this.meta("supply.json"), ...areas.map(a => this.file("supply", a))]);
    const items = Object.assign({}, ...ds.map(d => d.items || {}));
    return { ...base, items };
  },
  /* 생활권 선택 상자 채우기 + 기억 */
  fillAreas(sel, meta, { all = true, key = "jr9_area" } = {}) {
    const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    sel.innerHTML = Object.entries(meta.areas || {}).map(([k, a]) => `<option value="${k}">${esc(a.name)}${a.count != null ? ` (${a.count})` : ""}</option>`).join("")
      + (all ? `<option value="all">전체 (데이터가 많아 느릴 수 있음)</option>` : "");
    let v = null; try { v = localStorage.getItem(key); } catch (e) {}
    if (v && [...sel.options].some(o => o.value === v)) sel.value = v;
    sel.addEventListener("change", () => { try { localStorage.setItem(key, sel.value); } catch (e) {} });
    return sel.value;
  },
  areasOf(meta, v) { return v === "all" ? Object.keys(meta.areas || {}) : [v]; },
  kindLabel(it) { return it.kind === "빌라" ? '<span class="kind">빌라</span>' : ""; },
  bath(it) { return it.bath == null ? "욕실 수 확인 필요" : `욕실 ${it.bath}`; }
};
