/* Team pace: play clock used before the snap, with filters, a season table and a year-by-year view.
   Data: one cube per season (data/pace_YYYY.json) of plays aggregated by team, week, home/away, quarter, down,
   no-huddle and neutral situation. Every number is recomputed in the browser for the chosen filters. */
const P = {meta: null, seasons: [], cubes: {}, view: "season", season: null, stat: "clock", from: null,
           f: {wk0: 1, wk1: 22, q: "", d: "", h: "", nh: ""}, sortKey: "clock", sortDir: 1, q: ""};
const PCOLS = [
  {key: "clock", label: "Clock used", fmt: "num1", dir: "low", note: "Average seconds of the 40-second play clock used before the snap"},
  {key: "clock_neu", label: "Clock used (neutral)", fmt: "num1", dir: "low", note: "Same, in neutral situations: quarters 1–3 with win probability between 20% and 80%"},
  {key: "pass_neu", label: "Neutral pass rate", fmt: "pct", dir: null, note: "Dropbacks as a share of plays in neutral situations"},
  {key: "nohuddle", label: "No-huddle", fmt: "pct", dir: "high", note: "Share of plays run without a huddle"},
  {key: "plays_pg", label: "Plays/G", fmt: "num1", dir: "high", note: "Offensive plays per game within the filters"},
  {key: "snaps", label: "Timed snaps", fmt: "int", dir: null, note: "Snaps with a measurable play clock (after a run or pass with no stoppage)"},
];
async function cube(y) {
  if (!P.cubes[y]) P.cubes[y] = await getJSON("pace_" + y + ".json");
  return P.cubes[y];
}
function compute(c) {
  const k = c.cols, n = k.t.length, f = P.f;
  const acc = c.teams.map(() => ({n: 0, nh: 0, g: 0, s: 0, gn: 0, sn: 0, nn: 0, pn: 0, games: new Set()}));
  for (let i = 0; i < n; i++) {
    const w = k.w[i];
    if (w < f.wk0 || w > f.wk1) continue;
    if (f.h !== "" && k.h[i] !== +f.h) continue;
    const a = acc[k.t[i]];
    a.games.add(w);
    if (f.q !== "" && k.q[i] !== +f.q) continue;
    if (f.d !== "" && k.d[i] !== +f.d) continue;
    if (f.nh !== "" && k.nh[i] !== +f.nh) continue;
    a.n += k.n[i]; a.g += k.g[i]; a.s += k.s[i];
    if (k.nh[i]) a.nh += k.n[i];
    if (k.neu[i]) { a.gn += k.g[i]; a.sn += k.s[i]; a.nn += k.n[i]; a.pn += k.p[i]; }
  }
  return c.teams.map((t, i) => {
    const a = acc[i];
    return {team: t, name: nm(t), clock: a.g ? a.s / 10 / a.g : null, clock_neu: a.gn ? a.sn / 10 / a.gn : null,
            pass_neu: a.nn ? a.pn / a.nn : null, nohuddle: a.n ? a.nh / a.n : null,
            plays_pg: a.games.size ? a.n / a.games.size : null, snaps: a.g};
  });
}
function th(key, label, note, cls) {
  const s = P.sortKey === key ? ' aria-sort="' + (P.sortDir > 0 ? "ascending" : "descending") + '"' : "";
  return '<th scope="col" tabindex="0" data-k="' + key + '"' + (cls ? ' class="' + cls + '"' : "") + (note ? ' title="' + esc(note) + '"' : "") + s + '>' + esc(label) + '</th>';
}
const teamCell = r => '<td><b>' + esc(r.team) + '</b> <small>' + esc(r.name) + '</small></td>';
const seasonLabel = y => (P.meta && y === P.meta.season && P.meta.through_week < 18) ? y + " so far" : String(y);
const match = r => !P.q || (r.team + " " + r.name).toLowerCase().includes(P.q);

async function renderSeason() {
  const rowsAll = compute(await cube(P.season));
  const R = {}; PCOLS.forEach(c => { if (c.dir) R[c.key] = rankMap(rowsAll, c.key, c.dir); });
  let rows = sortRows(rowsAll.filter(match), P.sortKey, P.sortDir, (r, k) => k === "team" ? r.team : r[k]);
  $("thead").innerHTML = '<tr>' + th("team", "Team") + PCOLS.map(c => th(c.key, c.label, c.note)).join("") + '</tr>';
  $("tbody").innerHTML = rows.map(r => '<tr>' + teamCell(r) + PCOLS.map(c => {
    const rk = R[c.key] ? R[c.key].m.get(r.team) : null;
    return '<td class="' + (rk ? qClass(rk, R[c.key].n) : "") + '">' + fmtVal(r[c.key], c.fmt) + (rk ? '<small>' + rk + '</small>' : '') + '</td>';
  }).join("") + '</tr>').join("") || '<tr><td colspan="7" class="empty">No teams match.</td></tr>';
  const total = rowsAll.reduce((s, r) => s + r.snaps, 0);
  $("tnote").textContent = "Rank 1 = fastest (least clock used, most plays). Select a column heading to sort; select it again to reverse. " + total.toLocaleString() + " timed snaps in this selection" +
    (total < 2000 ? " — a small sample, so expect noise." : ".");
}
async function renderTrend() {
  const c = PCOLS.find(x => x.key === P.stat);
  const ys = P.seasons;
  const data = {};
  for (const y of ys) data[y] = compute(await cube(y));
  const to = ys[ys.length - 1], from = ys.includes(P.from) && P.from !== to ? P.from : ys[ys.length - 2];
  const val = (t, y) => { const r = data[y].find(x => x.team === t); return r ? r[c.key] : null; };
  const R = {}; if (c.dir) ys.forEach(y => { R[y] = rankMap(data[y], c.key, c.dir); });
  const delta = t => { const a = val(t, to), b = val(t, from); return a != null && b != null ? a - b : null; };
  let rows = data[to].filter(match);
  rows = sortRows(rows, P.sortKey, P.sortDir, (r, k) => k === "team" ? r.team : k === "delta" ? delta(r.team) : val(r.team, +k));
  $("thead").innerHTML = '<tr>' + th("team", "Team") + ys.map(y => th(String(y), seasonLabel(y))).join("") +
    th("delta", "Change " + String(from).slice(2) + "→" + String(to).slice(2), "Change from " + from + " to " + seasonLabel(to), "delta") + '</tr>';
  $("tbody").innerHTML = rows.map(r => '<tr>' + teamCell(r) + ys.map(y => {
    const rk = c.dir && R[y] ? R[y].m.get(r.team) : null;
    return '<td class="' + (rk ? qClass(rk, R[y].n) : "") + '">' + fmtVal(val(r.team, y), c.fmt) + (rk ? '<small>' + rk + '</small>' : '') + '</td>';
  }).join("") + '<td class="delta">' + fmtDelta(delta(r.team), c.fmt) + '</td></tr>').join("") ||
    '<tr><td colspan="' + (ys.length + 2) + '" class="empty">No teams match.</td></tr>';
  $("tnote").textContent = "Filters apply to every season. Small numbers are that season's ranks (1 = fastest). Clock used is measured from 2022, when the end time of each play became available." +
    (P.meta && to === P.meta.season && P.meta.through_week < 18 ? " " + seasonLabel(to) + " covers games through Week " + P.meta.through_week + "." : "");
}
async function render() {
  const trend = P.view === "trend";
  $("seasonField").hidden = trend; $("statField").hidden = !trend; $("fromField").hidden = !trend;
  document.querySelectorAll("[data-view]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.view === P.view)));
  $("tbody").setAttribute("aria-busy", "true");
  try { trend ? await renderTrend() : await renderSeason(); } finally { $("tbody").removeAttribute("aria-busy"); }
}
function sortDefault() {
  if (P.view === "trend") { P.sortKey = String(P.seasons[P.seasons.length - 1]); const c = PCOLS.find(x => x.key === P.stat); P.sortDir = c.dir === "low" ? 1 : -1; }
  else { P.sortKey = "clock"; P.sortDir = 1; }
}
boot(async meta => {
  P.meta = meta;
  const page = await getJSON("page_pace.json");
  P.seasons = page.seasons; P.season = page.season;
  const sel = (id, label, opts) => '<div class="field" id="' + id + 'Field"><label for="' + id + '">' + label + '</label><select id="' + id + '">' + opts.map(([v, t]) => '<option value="' + v + '">' + t + '</option>').join("") + '</select></div>';
  const weeks = Array.from({length: 18}, (_, i) => [i + 1, "Week " + (i + 1)]);
  $("app").innerHTML =
    '<div class="filters">' +
    '<div class="field"><span class="flabel">View</span><div class="seg" role="group" aria-label="View"><button type="button" data-view="season">Season table</button><button type="button" data-view="trend">Year by year</button></div></div>' +
    sel("season", "Season", [...P.seasons].reverse().map(y => [y, seasonLabel(y)])) +
    sel("stat", "Stat", PCOLS.filter(c => c.key !== "snaps").map(c => [c.key, c.label])) +
    sel("from", "Change from", P.seasons.slice(0, -1).reverse().map(y => [y, y])) +
    sel("wk0", "From week", weeks) + sel("wk1", "To week", weeks) +
    sel("qtr", "Quarter", [["", "All"], [1, "1st"], [2, "2nd"], [3, "3rd"], [4, "4th"], [5, "Overtime"]]) +
    sel("down", "Down", [["", "All"], [1, "1st"], [2, "2nd"], [3, "3rd"], [4, "4th"]]) +
    sel("venue", "Venue", [["", "Home + road"], [1, "Home"], [0, "Road"]]) +
    sel("huddle", "Huddle", [["", "Both"], [0, "Huddle"], [1, "No-huddle"]]) +
    '<div class="field"><label for="q">Find a team</label><input type="search" id="q" placeholder="e.g. NO or Saints" autocomplete="off"></div></div>' +
    '<p class="note" id="tnote"></p>' +
    '<div class="scroll"><table class="stbl"><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>';
  $("wk1").value = "18";
  const read = () => {
    let a = +$("wk0").value, b = +$("wk1").value; if (a > b) [a, b] = [b, a];
    P.f = {wk0: a, wk1: b === 18 ? 22 : b, q: $("qtr").value, d: $("down").value, h: $("venue").value, nh: $("huddle").value};
  };
  ["wk0", "wk1", "qtr", "down", "venue", "huddle"].forEach(id => $(id).addEventListener("change", () => { read(); render(); }));
  $("season").addEventListener("change", e => { P.season = +e.target.value; render(); });
  $("stat").addEventListener("change", e => { P.stat = e.target.value; sortDefault(); render(); });
  $("from").addEventListener("change", e => { P.from = +e.target.value; render(); });
  $("q").addEventListener("input", e => { P.q = e.target.value.trim().toLowerCase(); render(); });
  document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => { P.view = b.dataset.view; sortDefault(); render(); }));
  const onSort = e => {
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    const h = e.target.closest("th[data-k]"); if (!h) return;
    e.preventDefault();
    const k = h.dataset.k;
    if (P.sortKey === k) P.sortDir = -P.sortDir;
    else {
      P.sortKey = k;
      const c = PCOLS.find(x => x.key === (P.view === "trend" ? P.stat : k));
      P.sortDir = k === "team" ? 1 : (c && c.dir === "low" && k !== "delta" ? 1 : -1);
    }
    render().then(() => { const again = document.querySelector('th[data-k="' + k + '"]'); if (again) again.focus(); });
  };
  $("thead").addEventListener("click", onSort);
  $("thead").addEventListener("keydown", onSort);
  render();
});
