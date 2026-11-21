/* Ranked team tables with a season picker and a year-by-year view.
   Season table: one season, every stat, league rank beside each value, shaded by fifths (best to worst).
   Year by year: one stat, every season side by side, plus the change between two seasons. */
const T = {page: null, meta: null, view: "season", season: null, stat: null, from: null, sortKey: null, sortDir: -1, q: ""};

function th(key, label, note, cls) {
  const s = T.sortKey === key ? ' aria-sort="' + (T.sortDir > 0 ? "ascending" : "descending") + '"' : "";
  return '<th scope="col" tabindex="0" data-k="' + esc(key) + '"' + (cls ? ' class="' + cls + '"' : "") + (note ? ' title="' + esc(note) + '"' : "") + s + '>' + esc(label) + '</th>';
}
function teamCell(r) { return '<td><b>' + esc(r.team) + '</b> <small>' + esc(r.name || nm(r.team)) + '</small></td>'; }
function seasonLabel(y) {
  const cur = T.meta && y === T.meta.season && T.meta.through_week < 18;
  return cur ? y + " so far" : String(y);
}
/* ---------- season table ---------- */
function renderSeason() {
  const rowsAll = T.page.data[String(T.season)] || [];
  const empty = new Set(T.page.columns.filter(c => rowsAll.every(r => r[c.key] == null)).map(c => c.key));
  const cols = T.page.columns.filter(c => !empty.has(c.key));
  const R = {}; cols.forEach(c => { if (c.dir) R[c.key] = rankMap(rowsAll, c.key, c.dir); });
  let rows = rowsAll.filter(r => !T.q || (r.team + " " + (r.name || nm(r.team))).toLowerCase().includes(T.q));
  if (T.sortKey) rows = sortRows(rows, T.sortKey, T.sortDir, (r, k) => k === "team" ? r.team : r[k]);
  let groups = "";
  if (cols.some(c => c.group)) {
    groups = '<tr><th class="grp" scope="col"></th>';
    for (let i = 0; i < cols.length;) {
      let j = i; while (j < cols.length && cols[j].group === cols[i].group) j++;
      groups += '<th class="grp" scope="colgroup" colspan="' + (j - i) + '">' + esc(cols[i].group || "") + '</th>';
      i = j;
    }
    groups += '</tr>';
  }
  $("thead").innerHTML = groups + '<tr>' + th("team", "Team") + cols.map(c => th(c.key, c.label, c.note)).join("") + '</tr>';
  $("tbody").innerHTML = rows.map(r => '<tr>' + teamCell(r) + cols.map(c => {
    const v = r[c.key];
    if (c.fmt === "text") return '<td class="txt">' + esc(v) + '</td>';
    const rk = R[c.key] ? R[c.key].m.get(r.team) : null;
    return '<td class="' + (rk ? qClass(rk, R[c.key].n) : "") + '">' + fmtVal(v, c.fmt) + (rk ? '<small>' + rk + '</small>' : '') + '</td>';
  }).join("") + '</tr>').join("") || '<tr><td colspan="' + (cols.length + 1) + '" class="empty">No teams match.</td></tr>';
  const missing = T.page.columns.filter(c => empty.has(c.key)).map(c => c.label);
  $("tnote").textContent = "Small numbers are league ranks (1 = best). Select a column heading to sort; select it again to reverse the order." +
    (missing.length ? " Not yet available for " + T.season + ", so hidden: " + missing.join(", ") + " (switch season or use Year by year for earlier seasons)." : "");
}

/* ---------- year by year ---------- */
function renderTrend() {
  const c = T.page.columns.find(x => x.key === T.stat);
  const ys = T.page.seasons.filter(y => (T.page.data[String(y)] || []).some(r => r[c.key] != null));
  const to = ys[ys.length - 1], from = ys.includes(T.from) && T.from !== to ? T.from : ys[ys.length - 2];
  const by = {}; ys.forEach(y => { by[y] = new Map((T.page.data[String(y)] || []).map(r => [r.team, r])); });
  const R = {}; if (c.dir) ys.forEach(y => { R[y] = rankMap(T.page.data[String(y)], c.key, c.dir); });
  const val = (t, y) => { const r = by[y] && by[y].get(t); return r ? r[c.key] : null; };
  const delta = t => { const a = val(t, to), b = from != null ? val(t, from) : null; return a != null && b != null ? a - b : null; };
  let rows = TEAMS_LIST.map(t => ({team: t, name: nm(t)})).filter(r => !T.q || (r.team + " " + r.name).toLowerCase().includes(T.q));
  if (T.sortKey) rows = sortRows(rows, T.sortKey, T.sortDir, (r, k) => k === "team" ? r.team : k === "delta" ? delta(r.team) : val(r.team, +k));
  $("thead").innerHTML = '<tr>' + th("team", "Team") + ys.map(y => th(String(y), seasonLabel(y))).join("") +
    (from != null ? th("delta", "Change " + String(from).slice(2) + "→" + String(to).slice(2), "Change from " + from + " to " + seasonLabel(to) + (c.fmt === "pct" ? ", in percentage points" : ""), "delta") : "") + '</tr>';
  $("tbody").innerHTML = rows.map(r => {
    let h = '<tr>' + teamCell(r);
    ys.forEach(y => {
      const v = val(r.team, y), rk = c.dir && R[y] ? R[y].m.get(r.team) : null;
      h += '<td class="' + (rk ? qClass(rk, R[y].n) : "") + '">' + fmtVal(v, c.fmt) + (rk ? '<small>' + rk + '</small>' : '') + '</td>';
    });
    if (from != null) {
      const d = delta(r.team);
      const good = d == null || !c.dir || Math.abs(d) < 1e-9 ? "" : ((d > 0) === (c.dir === "high") ? "adj-pos" : "adj-neg");
      h += '<td class="delta ' + good + '">' + fmtDelta(d, c.fmt) + '</td>';
    }
    return h + '</tr>';
  }).join("") || '<tr><td colspan="' + (ys.length + 2) + '" class="empty">No teams match.</td></tr>';
  $("tnote").textContent = "Select a column heading to sort; select it again to reverse. " + (c.dir ? "Small numbers are that season's league ranks (1 = best); green change = improved" + (c.fmt === "pct" ? ", in percentage points" : "") + ". " : (c.fmt === "pct" ? "Change is in percentage points. " : "")) +
    (c.note ? c.note + ". " : "") + (ys.length < T.page.seasons.length ? "Seasons without this stat are left out. " : "") +
    (T.meta && to === T.meta.season && T.meta.through_week < 18 ? seasonLabel(to) + " covers games through Week " + T.meta.through_week + "." : "");
}

function render() {
  const trend = T.view === "trend";
  $("seasonField").hidden = trend;
  $("statField").hidden = !trend;
  $("fromField").hidden = !trend;
  document.querySelectorAll("[data-view]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.view === T.view)));
  if (trend) {
    const c = T.page.columns.find(x => x.key === T.stat);
    const ys = T.page.seasons.filter(y => (T.page.data[String(y)] || []).some(r => r[c.key] != null));
    const cur = $("from").value;
    $("from").innerHTML = ys.slice(0, -1).reverse().map(y => '<option value="' + y + '">' + y + '</option>').join("");
    if (ys.slice(0, -1).map(String).includes(cur)) $("from").value = cur;
    T.from = +$("from").value || null;
    renderTrend();
  } else renderSeason();
  try { history.replaceState(null, "", "#" + (trend ? "trend=" + T.stat : "season=" + T.season)); } catch (e) {}
}
function defaultSort() {
  if (T.view === "trend") { T.sortKey = String(T.page.seasons[T.page.seasons.length - 1]); const c = T.page.columns.find(x => x.key === T.stat); T.sortDir = c && c.dir === "low" ? 1 : -1; return; }
  const first = T.page.columns.find(c => c.dir);
  T.sortKey = first ? first.key : null; T.sortDir = first && first.dir === "low" ? 1 : -1;
}
const TEAMS_LIST = Object.keys(NAMES).sort();

boot(async meta => {
  T.meta = meta;
  const key = document.body.dataset.page;
  T.page = await getJSON("page_" + key + ".json");
  if (!T.page.seasons) { T.page.seasons = [meta.season]; T.page.data = {[meta.season]: T.page.rows || []}; }
  $("pageTitle").textContent = T.page.title;
  document.title = T.page.title + " · NFLFutures";
  $("pageIntro").textContent = T.page.intro || "";
  const multi = T.page.seasons.length > 1;
  const statCols = T.page.columns.filter(c => c.fmt !== "text" && c.key !== "games");
  T.season = T.page.season;
  T.stat = (statCols.find(c => c.dir) || statCols[0] || {}).key;
  try {
    const h = location.hash.slice(1).split("=");
    if (multi && h[0] === "trend" && statCols.some(c => c.key === h[1])) { T.view = "trend"; T.stat = h[1]; }
    if (h[0] === "season" && T.page.seasons.includes(+h[1])) T.season = +h[1];
  } catch (e) {}
  $("app").innerHTML =
    '<div class="table-head"><div class="filters">' +
    (multi ? '<div class="field"><span class="flabel">View</span><div class="seg" role="group" aria-label="View"><button type="button" data-view="season">Season table</button><button type="button" data-view="trend">Year by year</button></div></div>' : '') +
    '<div class="field" id="seasonField"><label for="season">Season</label><select id="season">' + [...T.page.seasons].reverse().map(y => '<option value="' + y + '">' + seasonLabel(y) + '</option>').join("") + '</select></div>' +
    '<div class="field" id="statField" hidden><label for="stat">Stat</label><select id="stat">' + statCols.map(c => '<option value="' + c.key + '">' + esc((c.group ? c.group + " · " : "") + c.label) + '</option>').join("") + '</select></div>' +
    '<div class="field" id="fromField" hidden><label for="from">Change from</label><select id="from"></select></div>' +
    '<div class="field"><label for="q">Find a team</label><input type="search" id="q" placeholder="e.g. KC or Chiefs" autocomplete="off"></div></div>' +
    '<div class="legend-q" aria-label="Shading key"><span><i class="q1"></i>Top fifth</span><span><i class="q2"></i>Above average</span><span><i style="background:var(--surface)"></i>Middle</span><span><i class="q4"></i>Below average</span><span><i class="q5"></i>Bottom fifth</span></div></div>' +
    '<p class="note" id="tnote"></p>' +
    '<div class="scroll"><table class="stbl"><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>';
  if (!multi) $("seasonField").hidden = true;
  $("season").value = String(T.season);
  $("stat").value = T.stat;
  defaultSort();
  document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => { T.view = b.dataset.view; defaultSort(); render(); }));
  $("season").addEventListener("change", e => { T.season = +e.target.value; render(); });
  $("stat").addEventListener("change", e => { T.stat = e.target.value; defaultSort(); render(); });
  $("from").addEventListener("change", () => render());
  $("q").addEventListener("input", e => { T.q = e.target.value.trim().toLowerCase(); render(); });
  const onSort = e => {
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    const h = e.target.closest("th[data-k]"); if (!h) return;
    e.preventDefault();
    const k = h.dataset.k;
    if (T.sortKey === k) T.sortDir = -T.sortDir;
    else {
      T.sortKey = k;
      const c = T.page.columns.find(x => x.key === (T.view === "trend" ? T.stat : k));
      T.sortDir = k === "team" ? 1 : (c && c.dir === "low" && k !== "delta" ? 1 : -1);
    }
    render();
    const again = document.querySelector('th[data-k="' + k + '"]'); if (again) again.focus();
  };
  $("thead").addEventListener("click", onSort);
  $("thead").addEventListener("keydown", onSort);
  render();
});
