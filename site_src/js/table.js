/* Generic ranked team table: sortable columns, league rank beside each value, shading by fifths (best to worst). */
const T = {page: null, sortKey: null, sortDir: -1, q: ""};
function ranksFor(col, rows) {
  // 1 = best. Ties share the best rank.
  const vals = rows.map(r => r[col.key]).filter(v => typeof v === "number" && isFinite(v));
  const sorted = [...vals].sort((a, b) => col.dir === "low" ? a - b : b - a);
  const out = new Map();
  rows.forEach(r => {
    const v = r[col.key];
    if (typeof v === "number" && isFinite(v)) out.set(r.team, sorted.indexOf(v) + 1);
  });
  return {ranks: out, n: vals.length};
}
function qClass(rank, n) {
  if (!rank || n < 5) return "";
  const q = Math.min(5, Math.floor((rank - 1) / n * 5) + 1);
  return q === 3 ? "" : "q" + q;
}
function headRows(cols) {
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
  const main = '<tr><th scope="col" data-k="team"' + ariaSort("team") + '>Team</th>' + cols.map(c =>
    '<th scope="col" data-k="' + esc(c.key) + '"' + (c.note ? ' title="' + esc(c.note) + '"' : '') + ariaSort(c.key) + '>' + esc(c.label) + '</th>').join("") + '</tr>';
  return groups + main;
}
function ariaSort(k) { return ' tabindex="0"' + (T.sortKey === k ? ' aria-sort="' + (T.sortDir > 0 ? "ascending" : "descending") + '"' : ""); }
function render() {
  const P = T.page, cols = P.columns.filter(c => c.key !== "team" && c.key !== "name");
  const R = {}; cols.forEach(c => { if (c.dir) R[c.key] = ranksFor(c, P.rows); });
  let rows = P.rows.filter(r => !T.q || (r.team + " " + (r.name || nm(r.team))).toLowerCase().includes(T.q));
  if (T.sortKey) {
    const k = T.sortKey, d = T.sortDir;
    rows = [...rows].sort((a, b) => {
      const x = k === "team" ? a.team : a[k], y = k === "team" ? b.team : b[k];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * d;
    });
  }
  let body = rows.map(r => '<tr><td><b>' + esc(r.team) + '</b> <small>' + esc(r.name || nm(r.team)) + '</small></td>' + cols.map(c => {
    const v = r[c.key];
    if (c.fmt === "text") return '<td class="txt">' + esc(v) + '</td>';
    const rk = R[c.key] ? R[c.key].ranks.get(r.team) : null;
    return '<td class="' + (rk ? qClass(rk, R[c.key].n) : "") + '">' + fmtVal(v, c.fmt) + (rk ? '<small>' + rk + '</small>' : '') + '</td>';
  }).join("") + '</tr>').join("");
  if (!rows.length) body = '<tr><td colspan="' + (cols.length + 1) + '" class="empty">No teams match.</td></tr>';
  $("thead").innerHTML = headRows(cols);
  $("tbody").innerHTML = body;
}
boot(async () => {
  const key = document.body.dataset.page;
  T.page = await getJSON("page_" + key + ".json");
  $("pageTitle").textContent = T.page.title;
  document.title = T.page.title + " · NFLFutures";
  $("pageIntro").textContent = T.page.intro || "";
  const first = T.page.columns.find(c => c.dir && c.key !== "team");
  if (first) { T.sortKey = first.key; T.sortDir = first.dir === "low" ? 1 : -1; }
  $("app").innerHTML =
    '<div class="table-head"><div class="filters"><div class="field"><label for="q">Find a team</label><input type="search" id="q" placeholder="e.g. KC or Chiefs" autocomplete="off"></div></div>' +
    '<div class="legend-q" aria-label="Shading key"><span><i class="q1"></i>Top fifth</span><span><i class="q2"></i>Above average</span><span><i style="background:var(--surface)"></i>Middle</span><span><i class="q4"></i>Below average</span><span><i class="q5"></i>Bottom fifth</span></div></div>' +
    '<p class="note">Small numbers are league ranks (1 = best). Select a column heading to sort.' + (T.page.rows.length ? '' : ' No games have been played yet this season.') + '</p>' +
    '<div class="scroll"><table class="stbl"><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>';
  $("q").addEventListener("input", e => { T.q = e.target.value.trim().toLowerCase(); render(); });
  const onSort = e => {
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    const th = e.target.closest("th[data-k]"); if (!th) return;
    e.preventDefault();
    const k = th.dataset.k;
    if (T.sortKey === k) T.sortDir = -T.sortDir;
    else {
      T.sortKey = k;
      const c = T.page.columns.find(x => x.key === k);
      T.sortDir = k === "team" ? 1 : (c && c.dir === "low" ? 1 : -1);
    }
    render();
    const again = document.querySelector('th[data-k="' + k + '"]'); if (again) again.focus();
  };
  $("thead").addEventListener("click", onSort);
  $("thead").addEventListener("keydown", onSort);
  render();
});
