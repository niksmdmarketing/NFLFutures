/* NHL pages. One script, five pages (body[data-page]): standings, teams, skaters, goalies, games.
   Data files are columnar: {cols:[{k,l,g,f,lo,t}], rows:[[identity..., value per col...]]}. Click any heading to sort. */
const PAGE = document.body.dataset.page;
const IDS = {teams: ["team", "name"], skaters: ["name", "team", "pos"], goalies: ["name", "team", "pos"], games: ["date", "team", "opp", "ha", "res"]};
const memo = {};
const load = (kind, y) => memo[kind + y] || (memo[kind + y] = getJSON(kind + "_" + y + ".json").then(d => hydrate(d, kind)));
let META = null;

function hydrate(d, kind) {
  const ids = IDS[kind === "team" ? "teams" : kind];
  d.rows = d.rows.map(a => {
    const o = {};
    ids.forEach((k, i) => o[k] = a[i]);
    d.cols.forEach((c, i) => o[c.k] = a[ids.length + i]);
    o.season = d.season;
    return o;
  });
  return d;
}
const seasonLabel = y => y + "-" + String((y + 1) % 100).padStart(2, "0");
const tname = t => (META.teams && META.teams[t]) || t;

function fmt(v, f) {
  if (v == null || (typeof v === "number" && !isFinite(v))) return "–";
  switch (f) {
    case "pct": return (v * 100).toFixed(1) + "%";
    case "pdo": return (v * 100).toFixed(1);
    case "sv": return v.toFixed(3).replace(/^0/, "");
    case "num1": return v.toFixed(1);
    case "num2": return v.toFixed(2);
    case "int": return Math.round(v).toLocaleString();
    case "mins": return Math.round(v / 60).toLocaleString();
    case "mmss": { const s = Math.round(v); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
    default: return esc(v);
  }
}
const opt = (v, l, sel) => '<option value="' + esc(v) + '"' + (sel ? " selected" : "") + ">" + esc(l) + "</option>";
const seasonOpts = (cur, all) => (all ? opt("all", "All seasons", cur === "all") : "") + META.seasons.map(y => opt(y, seasonLabel(y) + (y === META.season ? " (so far)" : ""), String(cur) === String(y))).join("");

/* ---------------- generic sortable data table ---------------- */
function tableHTML(rows, cols, idCols, st, o) {
  o = o || {};
  const th = (k, l, t, cls) => '<th scope="col" tabindex="0" data-k="' + esc(k) + '"' + (cls ? ' class="' + cls + '"' : "") + (t ? ' title="' + esc(t) + '"' : "") +
    (st.sortKey === k ? ' aria-sort="' + (st.sortDir > 0 ? "ascending" : "descending") + '"' : "") + ">" + esc(l) + "</th>";
  let rk = {};
  if (o.shade) cols.forEach(c => { if (c.f !== "text") rk[c.k] = rankMap(rows, c.k, c.lo ? "low" : "high"); });
  const head = "<tr>" + (o.rank ? "<th>#</th>" : "") + idCols.map(c => th(c.k, c.l, "", c.cls)).join("") + cols.map(c => th(c.k, c.l, c.t || c.l)).join("") + "</tr>";
  const body = rows.map((r, i) => "<tr>" + (o.rank ? "<td>" + (i + 1) + "</td>" : "") + idCols.map(c => c.cell ? c.cell(r) : "<td>" + esc(r[c.k]) + "</td>").join("") +
    cols.map(c => {
      const v = r[c.k];
      const q = rk[c.k] ? qClass(rk[c.k].m.get(r.team), rk[c.k].n) : "";
      return '<td class="' + (c.f === "text" ? "txt " : "") + q + '">' + fmt(v, c.f) + "</td>";
    }).join("") + "</tr>").join("");
  return '<div class="scroll"><table class="stbl nhl' + (o.rank ? ' ranked' : '') + '"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
}
function sortBy(rows, st, all) {
  if (!st.sortKey) return rows;
  const c = all.find(x => x.k === st.sortKey);
  const text = !c || c.f === "text";
  return sortRows(rows, st.sortKey, st.sortDir, (r, k) => r[k] == null ? null : text ? String(r[k]) : r[k]);
}
function wireSort(host, st, redraw, all) {
  host.querySelectorAll("th[data-k]").forEach(h => {
    const go = () => {
      const k = h.dataset.k, c = all.find(x => x.k === k);
      const text = !c || c.f === "text";
      if (st.sortKey === k) st.sortDir = -st.sortDir; else { st.sortKey = k; st.sortDir = text ? 1 : (c && c.lo ? 1 : -1); }
      redraw();
    };
    h.addEventListener("click", go);
    h.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
}
function chips(groups, cur) {
  return '<div class="field"><span class="flabel">Stat group</span><div class="seg chips" role="group">' +
    groups.map(g => '<button type="button" data-g="' + esc(g) + '" aria-pressed="' + (g === cur) + '">' + esc(g) + "</button>").join("") + "</div></div>";
}
const groupsOf = cols => ["All", ...new Set(cols.map(c => c.g))];
const PINNED = ["gamesPlayed"];
function visibleCols(cols, group) {
  return cols.filter(c => group === "All" || c.g === group || PINNED.includes(c.k));
}
const teamCell = r => "<td><b>" + esc(r.team) + "</b> <small>" + esc(r.name || tname(r.team)) + "</small></td>";

/* ---------------- standings ---------------- */
async function standings() {
  const st = {y: META.season, view: "division", sortKey: "points", sortDir: -1};
  const draw = async () => {
    const d = await load("team", st.y);
    const useDiv = st.y >= META.div_from;
    if (!useDiv && st.view !== "league") st.view = "league";
    const want = ["gamesPlayed", "wins", "losses", "otLosses", "points", "pointPct", "regulationAndOtWins", "goalsFor", "goalsAgainst", "goalDiff", "ptsPace", "expPoints", "luck", "shootingPlusSavePct5v5", "satPct", "powerPlayPct", "penaltyKillPct"];
    const cols = want.map(k => d.cols.find(c => c.k === k)).filter(Boolean).map(c => ({...c}));
    const alias = {gamesPlayed: "GP", wins: "W", losses: "L", otLosses: "OTL", points: "PTS", pointPct: "P%", regulationAndOtWins: "ROW", goalsFor: "GF", goalsAgainst: "GA",
      goalDiff: "GD", ptsPace: "PTS pace", expPoints: "Exp PTS", luck: "Luck", shootingPlusSavePct5v5: "PDO", satPct: "SAT%", powerPlayPct: "PP%", penaltyKillPct: "PK%"};
    cols.forEach(c => c.l = alias[c.k] || c.l);
    const rows = d.rows.slice();
    const dv = {}; Object.entries(META.divisions).forEach(([n, ts]) => ts.forEach(t => dv[t] = n));
    rows.forEach(r => { r.div = dv[r.team]; r.conf = META.conf[r.div]; });
    const by = (a, b) => (b.points - a.points) || ((a.gamesPlayed || 0) - (b.gamesPlayed || 0)) || ((b.regulationAndOtWins || 0) - (a.regulationAndOtWins || 0)) || ((b.goalDiff || 0) - (a.goalDiff || 0));
    let groups;
    if (st.view === "division" && useDiv) groups = Object.keys(META.divisions).map(n => [n + " Division", rows.filter(r => r.div === n)]);
    else if (st.view === "conference" && useDiv) groups = ["East", "West"].map(c => [c + "ern Conference", rows.filter(r => r.conf === c)]);
    else groups = [["League", rows]];
    const idCols = [{k: "team", l: "Team", cell: teamCell}];
    let html = "";
    groups.forEach(([title, rs]) => {
      rs = st.sortKey === "points" && st.sortDir === -1 ? rs.sort(by) : sortBy(rs, st, cols.concat([{k: "team", f: "text"}]));
      html += "<h2>" + esc(title) + "</h2>" + tableHTML(rs, cols, idCols, st, {rank: true});
    });
    $("tbl").innerHTML = html;
    $("tbl").querySelectorAll(".scroll").forEach(s => wireSort(s, st, draw, cols.concat([{k: "team", f: "text"}])));
    $("note").textContent = "Exp PTS is what the team's goal difference usually earns (fitted on every season on the site: about " + (META.slope * 100).toFixed(1) +
      " points of points-percentage per goal of differential per game). Luck is actual points minus Exp PTS; teams with big positive luck and a PDO well above 100 are the usual regression candidates. PDO is 5v5 shooting % plus save %.";
  };
  $("app").innerHTML = '<div class="filters"><div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y) + "</select></div>" +
    '<div class="field"><span class="flabel">Group by</span><div class="seg" id="vw" role="group">' + ["division", "conference", "league"].map(v => '<button type="button" data-v="' + v + '" aria-pressed="' + (v === st.view) + '">' + v[0].toUpperCase() + v.slice(1) + "</button>").join("") + "</div></div></div>" +
    '<div id="tbl"></div><p class="note" id="note"></p>';
  $("ss").onchange = e => { st.y = +e.target.value; draw(); };
  $("vw").querySelectorAll("button").forEach(b => b.onclick = () => { st.view = b.dataset.v; st.sortKey = "points"; st.sortDir = -1; $("vw").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); draw(); });
  draw();
}

/* ---------------- team stats (season table + year by year) ---------------- */
async function teams() {
  const st = {y: META.season, mode: "season", group: "Results", sortKey: "points", sortDir: -1, q: "", stat: "points", from: null, to: null};
  const seasonDraw = async () => {
    const d = await load("team", st.y);
    const groups = groupsOf(d.cols);
    if (!groups.includes(st.group)) st.group = groups[1] || "All";
    const cols = visibleCols(d.cols, st.group);
    let rows = d.rows.filter(r => !st.q || (r.team + " " + r.name).toLowerCase().includes(st.q));
    const all = d.cols.concat([{k: "team", f: "text"}]);
    rows = sortBy(rows, st, all);
    // shading ranks use the whole league, not the filtered rows
    const full = d.rows;
    const rk = {}; cols.forEach(c => { if (c.f !== "text" && new Set(full.map(r => r[c.k])).size > 1) rk[c.k] = rankMap(full, c.k, c.lo ? "low" : "high"); });
    const th = (k, l, t) => '<th scope="col" tabindex="0" data-k="' + esc(k) + '" title="' + esc(t || l) + '"' + (st.sortKey === k ? ' aria-sort="' + (st.sortDir > 0 ? "ascending" : "descending") + '"' : "") + ">" + esc(l) + "</th>";
    $("out").innerHTML = '<div class="scroll"><table class="stbl nhl"><thead><tr>' + th("team", "Team") + cols.map(c => th(c.k, c.l, c.t)).join("") + "</tr></thead><tbody>" +
      rows.map(r => "<tr>" + teamCell(r) + cols.map(c => {
        const rank = rk[c.k] ? rk[c.k].m.get(r.team) : null;
        return '<td class="' + (rk[c.k] ? qClass(rank, rk[c.k].n) : "") + '">' + fmt(r[c.k], c.f) + (rank ? "<small>" + rank + "</small>" : "") + "</td>";
      }).join("") + "</tr>").join("") + "</tbody></table></div>";
    wireSort($("out"), st, seasonDraw, all);
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; seasonDraw(); });
  };
  const yearDraw = async () => {
    const ds = await Promise.all(META.seasons.map(y => load("team", y)));
    const first = ds[0];                       // newest season fixes the stat list
    const col = first.cols.find(c => c.k === st.stat) || first.cols[0];
    const ys = META.seasons.slice().reverse();                      // oldest to newest
    const byY = {}; ds.forEach(d => byY[d.season] = d);
    st.from = st.from && ys.includes(+st.from) ? +st.from : ys[0];
    st.to = st.to && ys.includes(+st.to) ? +st.to : ys[ys.length - 1];
    const shown = ys.filter(y => y >= Math.min(st.from, st.to) && y <= Math.max(st.from, st.to));
    const teamsAll = [...new Set(ds.flatMap(d => d.rows.map(r => r.team)))];
    let rows = teamsAll.map(t => {
      const o = {team: t, name: tname(t)};
      shown.forEach(y => { const r = byY[y] && byY[y].rows.find(x => x.team === t); const c = byY[y] && byY[y].cols.find(x => x.k === col.k); o["y" + y] = r && c ? r[col.k] : null; });
      const vs = shown.map(y => o["y" + y]).filter(v => v != null);
      o.change = vs.length > 1 ? vs[vs.length - 1] - vs[0] : null;
      o.avg = vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
      return o;
    }).filter(r => !st.q || (r.team + " " + r.name).toLowerCase().includes(st.q));
    if (!st.ysort) st.ysort = {sortKey: "y" + shown[shown.length - 1], sortDir: col.lo ? 1 : -1};
    rows = sortBy(rows, st.ysort, [{k: "team", f: "text"}]);
    const flt = shown.map(y => rankMap(byY[y] ? byY[y].rows : [], col.k, col.lo ? "low" : "high"));
    const th = (k, l) => '<th scope="col" tabindex="0" data-k="' + k + '"' + (st.ysort.sortKey === k ? ' aria-sort="' + (st.ysort.sortDir > 0 ? "ascending" : "descending") + '"' : "") + ">" + esc(l) + "</th>";
    $("out").innerHTML = '<p class="note">' + esc(col.l) + (col.t ? " — " + esc(col.t) : "") + ". Shading ranks each season's league (best to worst). Change is last shown season minus first.</p>" +
      '<div class="scroll"><table class="stbl nhl"><thead><tr>' + th("team", "Team") + shown.map(y => th("y" + y, seasonLabel(y))).join("") + th("avg", "Avg") + th("change", "Change") + "</tr></thead><tbody>" +
      rows.map(r => "<tr>" + teamCell(r) + shown.map((y, i) => '<td class="' + qClass(flt[i].m.get(r.team), flt[i].n) + '">' + fmt(r["y" + y], col.f) + "</td>").join("") +
        "<td>" + fmt(r.avg, col.f) + "</td><td>" + (r.change == null ? "–" : (r.change > 0 ? "+" : r.change < 0 ? "−" : "") + fmt(Math.abs(r.change), col.f)) + "</td></tr>").join("") + "</tbody></table></div>";
    wireSort($("out"), st.ysort, yearDraw, [{k: "team", f: "text"}]);
  };
  const draw = async () => {
    $("modes").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.m === st.mode));
    $("seasonF").hidden = st.mode !== "season"; $("statF").hidden = st.mode !== "year"; $("rangeF").hidden = st.mode !== "year"; $("grp").hidden = st.mode !== "season";
    if (st.mode === "season") await seasonDraw(); else await yearDraw();
  };
  const d0 = await load("team", META.season);
  const statOpts = () => {
    const gs = {}; d0.cols.forEach(c => (gs[c.g] = gs[c.g] || []).push(c));
    return Object.entries(gs).map(([g, cs]) => '<optgroup label="' + esc(g) + '">' + cs.map(c => opt(c.k, c.l, c.k === st.stat)).join("") + "</optgroup>").join("");
  };
  const ysOld = META.seasons.slice().reverse();
  $("app").innerHTML = '<div class="filters"><div class="field"><span class="flabel">View</span><div class="seg" id="modes" role="group"><button type="button" data-m="season">Season table</button><button type="button" data-m="year">Year by year</button></div></div>' +
    '<div class="field" id="seasonF"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y) + "</select></div>" +
    '<div class="field" id="statF"><label for="stat">Stat</label><select id="stat">' + statOpts() + "</select></div>" +
    '<div class="field" id="rangeF"><label for="fy">From → to</label><span class="pair"><select id="fy">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[0])).join("") + '</select><select id="ty">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[ysOld.length - 1])).join("") + "</select></span></div>" +
    '<div class="field"><label for="q">Team</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">Click any heading to sort high to low, again for low to high. Small numbers are league ranks; shading runs from best (teal) to worst (orange). PDO, SAT% (Corsi) and zone starts are 5v5.</p>';
  $("modes").querySelectorAll("button").forEach(b => b.onclick = () => { st.mode = b.dataset.m; draw(); });
  $("ss").onchange = e => { st.y = +e.target.value; draw(); };
  $("stat").onchange = e => { st.stat = e.target.value; st.ysort = null; draw(); };
  $("fy").onchange = e => { st.from = +e.target.value; draw(); };
  $("ty").onchange = e => { st.to = +e.target.value; draw(); };
  $("q").oninput = e => { st.q = e.target.value.trim().toLowerCase(); draw(); };
  draw();
}

/* ---------------- skaters / goalies ---------------- */
async function players(kind) {
  const isG = kind === "goalies";
  const st = {y: META.season, group: isG ? "Basics" : "Scoring", sortKey: isG ? "wins" : "points", sortDir: -1, q: "", team: "", pos: "", min: 0, limit: 100};
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") {
      const ds = await Promise.all(META.seasons.map(y => load(kind, y)));
      const seen = new Map(); ds.forEach(d => d.cols.forEach(c => { if (!seen.has(c.k)) seen.set(c.k, c); }));
      cols = [...seen.values()]; rows = ds.flatMap(d => d.rows);
    } else { const d = await load(kind, st.y); cols = d.cols; rows = d.rows; }
    const groups = groupsOf(cols);
    if (!groups.includes(st.group)) st.group = groups[1] || "All";
    const teams = [...new Set(rows.flatMap(r => String(r.team || "").split(",")).filter(Boolean))].sort();
    $("team").innerHTML = opt("", "All teams", !st.team) + teams.map(t => opt(t, t, t === st.team)).join("");
    const gp = r => r.gamesPlayed || 0;
    const posOk = r => !st.pos || (st.pos === "F" ? "CLRW".includes(r.pos) : st.pos === "W" ? "LR".includes(r.pos) : r.pos === st.pos);
    rows = rows.filter(r => gp(r) >= st.min && posOk(r) && (!st.team || String(r.team).split(",").includes(st.team)) && (!st.q || r.name.toLowerCase().includes(st.q)));
    rows = sortBy(rows, st, cols.concat([{k: "name", f: "text"}, {k: "team", f: "text"}, {k: "pos", f: "text"}, {k: "season", f: "int"}]));
    const total = rows.length;
    rows = rows.slice(0, st.limit);
    const shown = visibleCols(cols, st.group);
    const idCols = [{k: "name", l: "Player", cell: r => "<td><b>" + esc(r.name) + "</b></td>"}];
    if (st.y === "all") idCols.push({k: "season", l: "Season", cell: r => "<td>" + seasonLabel(r.season) + "</td>"});
    idCols.push({k: "team", l: "Team", cell: r => "<td>" + esc(r.team) + "</td>"}, {k: "pos", l: "Pos", cell: r => "<td>" + esc(r.pos) + "</td>"});
    $("out").innerHTML = tableHTML(rows, shown, idCols, st, {rank: true}) +
      '<p class="note">Showing ' + rows.length + " of " + total + " rows" + (total > rows.length ? ' · <a href="#" id="more">show 100 more</a>' : "") + ". Click a heading to sort.</p>";
    wireSort($("out"), st, draw, cols.concat([{k: "name", f: "text"}, {k: "team", f: "text"}, {k: "pos", f: "text"}, {k: "season", f: "int"}]));
    const m = $("more"); if (m) m.onclick = e => { e.preventDefault(); st.limit += 100; draw(); };
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; draw(); });
  };
  const posBtns = isG ? "" : '<div class="field"><label for="pos">Position</label><select id="pos">' + [["", "All"], ["F", "Forwards"], ["C", "Centres"], ["W", "Wingers"], ["D", "Defence"]].map(([v, l]) => opt(v, l)).join("") + "</select></div>";
  $("app").innerHTML = '<div class="filters"><div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' + posBtns +
    '<div class="field"><label for="min">Min games</label><input id="min" type="number" min="0" value="0" style="width:84px"></div>' +
    '<div class="field"><label for="q">Player</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">' + (isG ? "Saves above average is saves minus what a league-average goalie would have saved on the same shots (it does not account for shot quality). " : "") +
    "'All seasons' lists every player-season since " + seasonLabel(META.seasons[META.seasons.length - 1]) + ", so you can rank the best single seasons.</p>";
  $("ss").onchange = e => { st.y = e.target.value === "all" ? "all" : +e.target.value; st.limit = 100; draw(); };
  $("team").onchange = e => { st.team = e.target.value; st.limit = 100; draw(); };
  if ($("pos")) $("pos").onchange = e => { st.pos = e.target.value; st.limit = 100; draw(); };
  $("min").oninput = e => { st.min = +e.target.value || 0; st.limit = 100; draw(); };
  $("q").oninput = e => { st.q = e.target.value.trim().toLowerCase(); st.limit = 100; draw(); };
  draw();
}

/* ---------------- game log ---------------- */
async function games() {
  const st = {y: META.season, team: "", ha: "", res: "", sortKey: "date", sortDir: -1, group: "Result", limit: 100};
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") {
      const ds = await Promise.all(META.seasons.map(y => load("games", y)));
      const seen = new Map(); ds.forEach(d => d.cols.forEach(c => { if (!seen.has(c.k)) seen.set(c.k, c); }));
      cols = [...seen.values()]; rows = ds.flatMap(d => d.rows);
    } else { const d = await load("games", st.y); cols = d.cols; rows = d.rows; }
    const groups = groupsOf(cols);
    if (!groups.includes(st.group)) st.group = "All";
    const teams = [...new Set(rows.map(r => r.team))].sort();
    $("team").innerHTML = opt("", "All teams", !st.team) + teams.map(t => opt(t, t + " · " + tname(t), t === st.team)).join("");
    rows = rows.filter(r => (!st.team || r.team === st.team) && (!st.ha || r.ha === st.ha) && (!st.res || r.res === st.res));
    const ids = ["date", "team", "opp", "ha", "res"].map(k => ({k, f: "text"}));
    rows = sortBy(rows, st, cols.concat(ids));
    const total = rows.length; rows = rows.slice(0, st.limit);
    const shown = cols.filter(c => st.group === "All" || c.g === st.group || ["goalsFor", "goalsAgainst"].includes(c.k));
    const idCols = [{k: "date", l: "Date", cell: r => '<td class="txt dt">' + esc(r.date) + "</td>"}, {k: "team", l: "Team", cell: r => "<td><b>" + esc(r.team) + "</b></td>"},
      {k: "opp", l: "Opp", cell: r => "<td>" + (r.ha === "R" ? "@ " : "vs ") + esc(r.opp) + "</td>"}, {k: "res", l: "Res", cell: r => '<td class="res-' + esc(r.res) + '">' + esc(r.res) + "</td>"}];
    $("out").innerHTML = tableHTML(rows, shown, idCols, st) + '<p class="note">Showing ' + rows.length + " of " + total + " games" + (total > rows.length ? ' · <a href="#" id="more">show 100 more</a>' : "") + ". Click a heading to sort — for example sort a team's games by SAT% to see their best possession games.</p>";
    wireSort($("out"), st, draw, cols.concat(ids));
    const m = $("more"); if (m) m.onclick = e => { e.preventDefault(); st.limit += 100; draw(); };
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; draw(); });
  };
  $("app").innerHTML = '<div class="filters"><div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' +
    '<div class="field"><label for="ha">Venue</label><select id="ha">' + [["", "Home & away"], ["H", "Home"], ["R", "Away"]].map(([v, l]) => opt(v, l)).join("") + "</select></div>" +
    '<div class="field"><label for="res">Result</label><select id="res">' + [["", "All"], ["W", "Wins"], ["L", "Losses"], ["OTL", "OT/SO losses"]].map(([v, l]) => opt(v, l)).join("") + "</select></div></div><div id=\"grp\"></div><div id=\"out\"></div>";
  $("ss").onchange = e => { st.y = e.target.value === "all" ? "all" : +e.target.value; st.limit = 100; draw(); };
  ["team", "ha", "res"].forEach(k => $(k).onchange = e => { st[k] = e.target.value; st.limit = 100; draw(); });
  draw();
}

boot(async meta => {
  META = meta;
  $("stamp").textContent = seasonLabel(meta.season) + " season · updated " + new Date(meta.updated_utc).toLocaleString(undefined, {weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"});
  ({index: standings, standings, teams, skaters: () => players("skaters"), goalies: () => players("goalies"), games})[PAGE]();
});
