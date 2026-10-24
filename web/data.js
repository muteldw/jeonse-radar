/* 전세 레이더 공통 데이터 로더 — 구(법정동코드)별 파일을 필요할 때만 내려받는다. */
const JR = {
  _m: {}, _c: {},
  esc: s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
  meta(name = "recommend.json") {
    if (!this._m[name]) this._m[name] = fetch("data/" + name, { cache: "no-store" }).then(r => { if (!r.ok) throw new Error(name); return r.json(); });
    return this._m[name];
  },
  file(folder, code) {
    const k = folder + "/" + code;
    if (!this._c[k]) this._c[k] = fetch(`data/${folder}/${code}.json`, { cache: "no-store" }).then(r => r.ok ? r.json() : { items: [] }).catch(() => ({ items: [] }));
    return this._c[k];
  },
  isSgg(meta) { return meta.layout === "sgg" && meta.sgg; },
  /* 선택값 → 내려받을 파일 코드 목록. 'area:키' = 생활권 전체, 'all' = 전체, 그 외 = 구 코드 */
  codesOf(meta, v) {
    if (!this.isSgg(meta)) return v === "all" ? Object.keys(meta.areas || {}) : [v.replace(/^area:/, "")];
    if (v === "all") return Object.keys(meta.sgg);
    if (v.startsWith("area:")) return (meta.areas[v.slice(5)] || {}).codes || [];
    return [v];
  },
  async items(folder, codes) {
    const ds = await Promise.all(codes.map(c => this.file(folder, c)));
    return [].concat(...ds.map(d => d.items || []));
  },
  async supply(codes) {
    const [base, ...ds] = await Promise.all([this.meta("supply.json"), ...codes.map(c => this.file("supply", c))]);
    return { ...base, items: Object.assign({}, ...ds.map(d => d.items || {})) };
  },
  sggLabel(s) {
    if (s.count) return `${s.name} (${s.count})`;
    const done = s.collected && Object.values(s.collected).some(Boolean);
    return `${s.name} (${done ? "위치 조회 중" : "수집 중"})`;
  },
  /* 지역 선택 상자: 생활권별로 묶은 구 목록 */
  fillRegions(sel, meta, { all = false, key = "jr9_region", def } = {}) {
    const e = this.esc;
    let html = "";
    if (this.isSgg(meta)) {
      for (const [k, a] of Object.entries(meta.areas || {})) {
        html += `<optgroup label="${e(a.name)}"><option value="area:${k}">${e(a.name)} 전체 (${a.count})</option>`;
        for (const c of a.codes || []) html += `<option value="${c}">${e(this.sggLabel(meta.sgg[c]))}</option>`;
        html += "</optgroup>";
      }
    } else {
      html = Object.entries(meta.areas || {}).map(([k, a]) => `<option value="area:${k}">${e(a.name)} (${a.count ?? ""})</option>`).join("");
    }
    if (all) html += `<option value="all">전체 (데이터가 많아 느릴 수 있음)</option>`;
    sel.innerHTML = html;
    let v = def || null; try { v = v || localStorage.getItem(key); } catch (x) {}
    if (v && [...sel.options].some(o => o.value === v)) sel.value = v;
    sel.addEventListener("change", () => { try { localStorage.setItem(key, sel.value); } catch (x) {} });
    return sel.value;
  },
  /* 작은 글씨 출처 줄 */
  sourceLine(meta, label = "계약일") {
    const p = meta.period || {}, e = this.esc;
    const kinds = p.by_kind ? Object.entries(p.by_kind).map(([k, n]) => `${k} ${n.toLocaleString()}건`).join(" · ") : "";
    return `출처: ${e(meta.source || "")}${p.from ? ` · ${label} ${p.from} ~ ${p.to}` : ""}${kinds ? ` · ${kinds}` : ""} · ${e((meta.generated_at || "").replace("T", " ").slice(0, 16))} 갱신 · 위치·역·인프라: 카카오 로컬 · <a href="sources.html">자료 전체 보기</a>`;
  },
  // 국토부 단지명 → 네이버 검색용 이름: 동·지번 괄호 삭제, "(14단지)"·"(5차)"는 살림
  naverName(it) {
    let n = String(it.name || "").replace(/ \([^)]*\)$/, "");          // 빌라 "이름 (지번)"
    n = n.replace(/\(([^)]*)\)/g, (m, x) => /^[\d\s,~-]+$|동|상가|^[가-하]$/.test(x) ? " " : " " + x + " ");
    n = n.replace(/\d+동(?=[,\s]|$)/g, " ").replace(/[,~]/g, " ").replace(/[\u4e00-\u9fff]/g, "");
    return n.replace(/\s+/g, " ").trim() || String(it.name || "");
  },
  // 호가 링크: 1) 단지 위치로 네이버 부동산 지도(그 자리 단지가 바로 보임) 2) 동+단지명 검색
  naverLinks(it, trade) {
    const t = trade === "sale" ? "A1" : "B1", villa = it.kind === "빌라", q = `${it.umd || ""} ${JR.naverName(it)}`.trim();
    const map = it.lat && it.lng ? `https://new.land.naver.com/${villa ? "houses" : "complexes"}?ms=${it.lat},${it.lng},18&a=${villa ? "VL:DDDGG:JWJT:SGJT:HOJT" : "APT:ABYG:JGC"}&b=${t}&e=RETAIL` : null;
    const search = `https://m.land.naver.com/search/result/${encodeURIComponent(q)}`;
    const web = `https://search.naver.com/search.naver?query=${encodeURIComponent(q + (villa ? "" : " 아파트") + " 네이버부동산")}`;
    return { map, search, web, q };
  },
  naverHtml(it, trade, cls = "") {
    const L = JR.naverLinks(it, trade), c = cls ? ` class="${cls}"` : "", o = ' target="_blank" rel="noopener"';
    return (L.map ? `<a${c} href="${L.map}"${o} title="네이버 부동산 지도에서 이 위치 열기">호가(지도)</a> ` : "") +
      `<a${c} href="${L.search}"${o} title="${JR.esc(L.q)} 검색">호가(검색)</a>`;
  },
  kindLabel(it) { return it.kind === "빌라" ? '<span class="kind">빌라</span>' : ""; },
  bath(it) { return it.bath == null ? "욕실 수 확인 필요" : `욕실 ${it.bath}`; }
};
