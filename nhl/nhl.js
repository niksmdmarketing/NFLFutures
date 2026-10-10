/* NHL pages. One script, five pages (body[data-page]): standings, teams, skaters, goalies, games.
   Data files are columnar: {cols:[{k,l,g,f,lo,t}], rows:[[identity..., value per col...]]}. Click any heading to sort. */
const PAGE = document.body.dataset.page;
const IDS = {teams: ["team", "name"], skaters: ["name", "team", "pos"], goalies: ["name", "team", "pos"], games: ["date", "team", "opp", "ha", "res"]};
const memo = {};
let PO = false;                                   // false = regular season, true = playoffs
const load = (kind, y) => { const f = kind + "_" + y + (PO ? "p" : ""); return memo[f] || (memo[f] = getJSON(f + ".json").then(d => hydrate(d, kind))); };
let META = null;
const seasons = () => (PO ? META.po_seasons : META.seasons);
const typeToggle = () => '<div class="field"><span class="flabel">Season type</span><div class="seg" id="gt" role="group"><button type="button" data-p="0" aria-pressed="' + !PO + '">Regular season</button><button type="button" data-p="1" aria-pressed="' + PO + '">Playoffs</button></div></div>';
const wireType = () => { const g = $("gt"); if (g) g.querySelectorAll("button").forEach(b => b.onclick = () => { PO = b.dataset.p === "1"; ROUTES[PAGE](); }); };

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
const seasonOpts = (cur, all) => (all ? opt("all", "All seasons", cur === "all") : "") + seasons().map(y => opt(y, seasonLabel(y) + (!PO && y === META.season ? " (so far)" : ""), String(cur) === String(y))).join("");

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
const KEY = {
  teams: ["gamesPlayed", "points", "mp_xGoalsFor", "mp_xGoalsAgainst", "mp_xGoalsPercentage", "mp5v5_xGoalsPercentage", "mp_highDangerShotsFor", "mp_highDangerShotsAgainst",
    "mp_highDangerxGoalsFor", "mp_highDangerxGoalsAgainst", "satFor", "satAgainst", "satPct", "mp_shotAttemptsFor", "mp_shotAttemptsAgainst", "savePct5v5", "powerPlayPct", "penaltyKillPct", "shootingPlusSavePct5v5"],
  skaters: ["gamesPlayed", "goals", "points", "mp_I_F_xGoals", "mp_I_F_highDangerShots", "mp_I_F_highDangerxGoals", "satPct", "mp_onIce_xGoalsPercentage", "ppGoals", "ppPoints", "ppPointsPer60", "timeOnIcePerGame"],
  goalies: ["gamesPlayed", "wins", "savePct", "goalsAgainstAverage", "savesAboveAvg", "mp_gsax", "mp_hdSavePct", "evSavePct", "ppSavePct", "shSavePct"],
};
let KEYSET = "teams";
const groupsOf = cols => { const has = KEY[KEYSET].some(k => cols.some(c => c.k === k)); return [...(has ? ["Key stats"] : []), "All", ...new Set(cols.map(c => c.g))]; };
const PINNED = ["gamesPlayed"];
function visibleCols(cols, group) {
  if (group === "Key stats") return KEY[KEYSET].map(k => cols.find(c => c.k === k)).filter(Boolean);
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
    const want = ["gamesPlayed", "wins", "losses", "otLosses", "points", "pointPct", "regulationAndOtWins", "goalsFor", "goalsAgainst", "goalDiff", "ptsPace", "expPoints", "luck", "shootingPlusSavePct5v5", "satPct", "mp_xGoalsPercentage", "mp_highDangerShotsFor", "mp_highDangerShotsAgainst", "powerPlayPct", "penaltyKillPct"];
    const cols = want.map(k => d.cols.find(c => c.k === k)).filter(Boolean).map(c => ({...c}));
    const alias = {gamesPlayed: "GP", wins: "W", losses: "L", otLosses: "OTL", points: "PTS", pointPct: "P%", regulationAndOtWins: "ROW", goalsFor: "GF", goalsAgainst: "GA",
      goalDiff: "GD", ptsPace: "PTS pace", expPoints: "Exp PTS", luck: "Luck", shootingPlusSavePct5v5: "PDO", satPct: "Corsi%", mp_xGoalsPercentage: "xG%", mp_highDangerShotsFor: "HDC For", mp_highDangerShotsAgainst: "HDC Ag", powerPlayPct: "PP%", penaltyKillPct: "PK%"};
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
  KEYSET = "teams";
  const st = {y: seasons()[0], mode: "season", group: "Key stats", sortKey: "points", sortDir: -1, q: "", stat: "points", from: null, to: null};
  const seasonDraw = async () => {
    const d = await load("team", st.y);
    const groups = groupsOf(d.cols);
    if (!groups.includes(st.group)) st.group = "All";
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
    const ds = await Promise.all(seasons().map(y => load("team", y)));
    const first = ds[0];                       // newest season fixes the stat list
    const col = first.cols.find(c => c.k === st.stat) || first.cols[0];
    const ys = seasons().slice().reverse();                      // oldest to newest
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
  const d0 = await load("team", seasons()[0]);
  const statOpts = () => {
    const gs = {}; d0.cols.forEach(c => (gs[c.g] = gs[c.g] || []).push(c));
    return Object.entries(gs).map(([g, cs]) => '<optgroup label="' + esc(g) + '">' + cs.map(c => opt(c.k, c.l, c.k === st.stat)).join("") + "</optgroup>").join("");
  };
  const ysOld = seasons().slice().reverse();
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><span class="flabel">View</span><div class="seg" id="modes" role="group"><button type="button" data-m="season">Season table</button><button type="button" data-m="year">Year by year</button></div></div>' +
    '<div class="field" id="seasonF"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y) + "</select></div>" +
    '<div class="field" id="statF"><label for="stat">Stat</label><select id="stat">' + statOpts() + "</select></div>" +
    '<div class="field" id="rangeF"><label for="fy">From → to</label><span class="pair"><select id="fy">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[0])).join("") + '</select><select id="ty">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[ysOld.length - 1])).join("") + "</select></span></div>" +
    '<div class="field"><label for="q">Team</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">Click any heading to sort high to low, again for low to high. Small numbers are league ranks; shading runs from best (teal) to worst (orange). PDO, SAT% (Corsi) and zone starts are 5v5.</p>';
  wireType();
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
  KEYSET = kind;
  const st = {y: seasons()[0], group: "Key stats", sortKey: isG ? "wins" : "points", sortDir: -1, q: "", team: "", pos: "", min: 0, limit: 100};
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") {
      const ds = await Promise.all(seasons().map(y => load(kind, y)));
      const seen = new Map(); ds.forEach(d => d.cols.forEach(c => { if (!seen.has(c.k)) seen.set(c.k, c); }));
      cols = [...seen.values()]; rows = ds.flatMap(d => d.rows);
    } else { const d = await load(kind, st.y); cols = d.cols; rows = d.rows; }
    const groups = groupsOf(cols);
    if (!groups.includes(st.group)) st.group = "All";
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
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' + posBtns +
    '<div class="field"><label for="min">Min games</label><input id="min" type="number" min="0" value="0" style="width:84px"></div>' +
    '<div class="field"><label for="q">Player</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">' + (isG ? "Saves above average is saves minus what a league-average goalie would have saved on the same shots (it does not account for shot quality). " : "") +
    "'All seasons' lists every player-season since " + seasonLabel(seasons()[seasons().length - 1]) + ", so you can rank the best single seasons.</p>";
  wireType();
  $("ss").onchange = e => { st.y = e.target.value === "all" ? "all" : +e.target.value; st.limit = 100; draw(); };
  $("team").onchange = e => { st.team = e.target.value; st.limit = 100; draw(); };
  if ($("pos")) $("pos").onchange = e => { st.pos = e.target.value; st.limit = 100; draw(); };
  $("min").oninput = e => { st.min = +e.target.value || 0; st.limit = 100; draw(); };
  $("q").oninput = e => { st.q = e.target.value.trim().toLowerCase(); st.limit = 100; draw(); };
  draw();
}

/* ---------------- game log ---------------- */
async function games() {
  const st = {y: seasons()[0], team: "", ha: "", res: "", sortKey: "date", sortDir: -1, group: "Result", limit: 100};
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") {
      const ds = await Promise.all(seasons().map(y => load("games", y)));
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
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' +
    '<div class="field"><label for="ha">Venue</label><select id="ha">' + [["", "Home & away"], ["H", "Home"], ["R", "Away"]].map(([v, l]) => opt(v, l)).join("") + "</select></div>" +
    '<div class="field"><label for="res">Result</label><select id="res">' + [["", "All"], ["W", "Wins"], ["L", "Losses"], ["OTL", "OT/SO losses"]].map(([v, l]) => opt(v, l)).join("") + "</select></div></div><div id=\"grp\"></div><div id=\"out\"></div>";
  wireType();
  $("ss").onchange = e => { st.y = e.target.value === "all" ? "all" : +e.target.value; st.limit = 100; draw(); };
  ["team", "ha", "res"].forEach(k => $(k).onchange = e => { st[k] = e.target.value; st.limit = 100; draw(); });
  draw();
}

/* ---------------- team futures ---------------- */
async function futuresPage() {
  const F = await getJSON("futures.json");
  const T = F.teams, P = F.params, bt = F.backtest || {};
  const pc = v => v == null ? "–" : v < 0.0005 ? "<0.1%" : v < 0.1 ? (v * 100).toFixed(1) + "%" : Math.round(v * 100) + "%";
  const head = [["Team", null], ["Div", null], ["GP", null], ["PTS", null], ["Rating", "Goal difference per game vs average, after blending last season with this one"], ["Proj. PTS", "Average of the simulated seasons"],
    ["10–90%", "Range containing 80% of simulated seasons"], ["Playoffs", null], ["Division", null], ["Round 2", null], ["Conf. final", null], ["Final", null], ["Cup", null], ["Best record", null]];
  const sk = {key: "p_cup", dir: -1};
  const rowsHtml = () => T.slice().sort((a, b) => (b[sk.key] - a[sk.key]) * (sk.dir === -1 ? 1 : -1)).map(r => "<tr><td><b>" + esc(r.team) + '</b> <small>' + esc(r.name) + "</small></td><td>" + esc(r.div) + "</td><td>" + r.gp + "</td><td>" + r.points + '</td><td data-v="' + r.rating + '">' +
    (r.rating >= 0 ? "+" : "−") + Math.abs(r.rating).toFixed(2) + '</td><td data-v="' + r.pts_mean + '">' + r.pts_mean.toFixed(1) + "</td><td>" + r.pts_p10 + "–" + r.pts_p90 + "</td>" +
    ["p_playoffs", "p_div", "p_r2", "p_r3", "p_final", "p_cup", "p_pres"].map(k => '<td data-v="' + r[k] + '"' + (k === "p_cup" ? " style=\"font-weight:700\"" : "") + ">" + pc(r[k]) + "</td>").join("") + "</tr>").join("");
  const draw = () => { $("ft").querySelector("tbody").innerHTML = rowsHtml(); };
  const calib = (bt.calibration_20 || []).map(c => "<tr><td>" + esc(c.bin.replace("(-0.001", "[0").replace("]", "]")) + "</td><td>" + pct(c.pred) + "</td><td>" + pct(c.actual) + "</td><td>" + c.n + "</td></tr>").join("");
  const b0 = bt["0"], b20 = bt["20"];
  $("app").innerHTML = '<p class="note">Through ' + Math.round(F.games_played) + " games per team. " + F.sims.toLocaleString() + " simulations of the rest of the season and the playoffs. Chances only. Click a heading to sort.</p>" +
    '<div class="scroll"><table class="stbl nhl" id="ft"><thead><tr>' + head.map(([h, t]) => "<th" + (t ? ' title="' + esc(t) + '"' : "") + ">" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" + rowsHtml() + "</tbody></table></div>" +
    '<h2 style="margin-top:22px">Points total</h2><p class="note">Pick a team and a line to see the chance the team finishes over or under it.</p>' +
    '<div class="filters"><div class="field"><label for="pt">Team</label><select id="pt">' + T.slice().sort((a, b) => a.team.localeCompare(b.team)).map(r => opt(r.team, r.team + " · " + r.name)).join("") + "</select></div>" +
    '<div class="field"><label for="pl">Line</label><input id="pl" type="number" step="0.5" style="width:100px"></div></div><div id="pout" class="panel" style="margin-top:10px"></div>' +
    (b0 && b20 ? '<h2 style="margin-top:22px">How good is it?</h2><p class="note">The same model was run from the start of each of the last ' + b0.seasons + " seasons (2021-22 on) and again after 20 games, using only what was known at the time (every setting is estimated from earlier seasons only). " +
      "Preseason, its points forecast was off by " + b0.mae_model.toFixed(1) + " on average versus " + b0.mae_naive.toFixed(1) + " for a simple 'last season, pulled halfway to average' guess, so it adds little before the season starts. After 20 games it is off by " + b20.mae_model.toFixed(1) + " versus " + b20.mae_naive.toFixed(1) +
      ". Playoff log-loss after 20 games: " + b20.logloss_playoffs.toFixed(3) + " (a 50/50 guess scores " + b20.logloss_playoffs_base.toFixed(3) + "); division log-loss " + b20.logloss_division.toFixed(3) + " versus " + b20.logloss_division_base.toFixed(3) + ". Lower is better. This is not a comparison with betting markets.</p>" +
      '<div class="scroll" style="max-width:520px"><table class="stbl nhl"><thead><tr><th>Predicted playoff chance (after 20 games)</th><th>Average predicted</th><th>Actually made it</th><th>Team-seasons</th></tr></thead><tbody>' + calib + "</tbody></table></div>" : "") +
    '<p class="note">Against prediction-market prices (Polymarket, 2025-26 only) at the same dates: before the season the market was slightly more accurate; after 20 games the model was more accurate on the Cup and conference winners. Prices are never used by the model.</p>' +
    '<h2 style="margin-top:22px">What it does and does not know</h2><ul class="note" style="max-width:80ch"><li>Rating = goal difference per game. Before the season it is a regression on last season\'s goal and expected-goal difference and the season before. In season it blends in the current rate (weight on last season worth ' + P.k + " games). Current rate is 60% goals, 40% expected goals; that split is a judgement call, not fitted.</li>" +
    "<li>Each simulation first shifts every team's rating by a random amount (typical size " + P.tau_now.toFixed(2) + " goals per game) so futures are not over-confident, then plays the actual remaining schedule and the real playoff format (3 per division plus 2 wild cards, best-of-7).</li>" +
    "<li>It does not know about injuries, trades, goalie changes, or off-season roster moves. Those are the main reasons to disagree with it.</li></ul>";
  $("ft").querySelectorAll("th").forEach((h, i) => { const keys = [null, null, null, null, "rating", "pts_mean", null, "p_playoffs", "p_div", "p_r2", "p_r3", "p_final", "p_cup", "p_pres"]; if (!keys[i]) return;
    h.style.cursor = "pointer"; h.onclick = () => { sk.dir = sk.key === keys[i] ? -sk.dir : -1; sk.key = keys[i]; draw(); }; });
  const upd = () => { const r = T.find(x => x.team === $("pt").value); const L = parseFloat($("pl").value); if (!r || !isFinite(L)) { $("pout").textContent = ""; return; }
    const ge = x => r.over[Math.min(Math.max(x, 30), 140) - 30]; const over = ge(Math.floor(L) + 1), under = 1 - ge(Math.ceil(L)), push = Number.isInteger(L) ? ge(L) - ge(L + 1) : 0;
    $("pout").innerHTML = "<div><b>" + esc(r.name) + "</b> projected " + r.pts_mean.toFixed(1) + " points (10–90%: " + r.pts_p10 + "–" + r.pts_p90 + "). Line " + L + ": <b>over " + pct(over) + "</b> · <b>under " + pct(under) + "</b>" + (push > 0.0005 ? " · exactly " + L + " " + pct(push) : "") + "</div>"; };
  $("pt").onchange = () => { const r = T.find(x => x.team === $("pt").value); $("pl").value = Math.round(r.pts_mean * 2) / 2 - (Number.isInteger(Math.round(r.pts_mean * 2) / 2) ? 0.5 : 0); upd(); };
  $("pl").oninput = upd;
  $("pt").onchange();
}

/* ---------------- award futures ---------------- */
async function awardsPage() {
  const A = await getJSON("awards.json");
  const order = ["Hart", "Vezina", "Norris", "Calder", "ArtRoss", "Richard"].filter(k => A.awards[k]);
  const st = {a: (location.hash.slice(1) && A.awards[location.hash.slice(1)]) ? location.hash.slice(1) : order[0]};
  const f1 = v => v == null || !isFinite(v) ? "–" : v.toFixed(1), n0 = v => v == null || !isFinite(v) ? "–" : Math.round(v);
  const draw = () => {
    document.querySelectorAll("[data-aw]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.aw === st.a)));
    const a = A.awards[st.a], g = st.a === "Vezina", race = st.a === "ArtRoss" || st.a === "Richard";
    let h = "<h2>" + esc(a.title) + "</h2>";
    if (a.backtest) {
      const b = a.backtest;
      h += '<p class="note"><b>Track record.</b> Fitted on every winner since 2010-11 and tested one season at a time with that season held out: the model\'s top pick won ' + b.top1 + " of " + b.n + " seasons (top three: " + b.top3 +
        "). Simply picking the stat leader would have won " + b.leader_hits + ". On average it gave the eventual winner " + pct(b.avg_p) + ". Voters are not fully predictable, so treat these as chances, not locks.</p>";
    } else {
      h += '<p class="note">Simulated finish: the rest of the season is played out ' + "thousands of times from each player\'s current total and his rate (blended with last season), with ties split. Not back-tested.</p>";
    }
    h += '<p class="note">' + (A.games_played ? "Through " + A.games_played + " games per team." : "") + (a.backtest ? " Chances come from simulating each candidate\'s season forward, so they are wide early and narrow as the season goes." : "") + "</p>";
    const rows = a.current || [];
    const head = g ? ["Goalie", "Team", "GP", "W", "SV%", "GAA", "Saves above avg", "Proj. saves above avg", "Chance"]
      : race ? ["Player", "Team", "GP", "G", "PTS", st.a === "ArtRoss" ? "Proj. PTS (10–90%)" : "Proj. goals (10–90%)", "Chance"]
      : ["Player", "Team", "Pos", "GP", "G", "PTS", "Saves above avg", "Proj. PTS", "Team P% (to date)", "Chance"];
    const cell = r => {
      const nm = '<td><b>' + esc(r.name) + "</b></td>", tm = "<td>" + esc(r.team) + "</td>";
      const ch = '<td data-v="' + r.prob + '"><b>' + pct(r.prob) + "</b></td>";
      if (g) return nm + tm + "<td>" + r.gp + "</td><td>" + r.wins + "</td><td>" + (r.save_pct ? r.save_pct.toFixed(3).replace(/^0/, "") : "–") + "</td><td>" + f1(r.gaa).replace(/^(\d)\.(\d)$/, "$1.$2") + "</td><td>" + f1(r.saa) + "</td><td>" + f1(r.proj_saa) + "</td>" + ch;
      if (race) return nm + tm + "<td>" + r.gp + "</td><td>" + r.goals + "</td><td>" + r.pts + "</td><td>" + n0(st.a === "ArtRoss" ? r.proj_pts : r.proj_goals) + " <small>(" + n0(r.lo) + "–" + n0(r.hi) + ")</small></td>" + ch;
      const isG = r.pos === "G";
      return nm + tm + "<td>" + esc(r.pos) + "</td><td>" + r.gp + "</td><td>" + (isG ? "–" : r.goals) + "</td><td>" + (isG ? "–" : r.pts) + "</td><td>" + (isG ? f1(r.saa) : "–") + "</td><td>" + (isG ? "–" : n0(r.proj_pts)) + "</td><td>" + pct(r.tm_pp) + "</td>" + ch;
    };
    h += '<div class="scroll"><table class="stbl nhl"><thead><tr>' + head.map(x => "<th>" + esc(x) + "</th>").join("") + "</tr></thead><tbody>" + rows.map(r => "<tr>" + cell(r) + "</tr>").join("") + "</tbody></table></div>";
    h += '<h2 style="margin-top:22px">Past winners</h2><p class="note">' + (race ? "The league leader each season and the margin over second place." :
      "Each winner's final numbers and where they ranked (points rank among " + (st.a === "Norris" ? "defencemen" : st.a === "Calder" ? "rookies" : "skaters") + ", saves above average rank among goalies).") + "</p>";
    const ph = race ? ["Season", "Player", "Team", "GP", "G", "PTS", "Margin"] : ["Season", "Winner", "Team", "Pos", "GP", "G", "PTS", "Rank", "Saves above avg", "Team P%"];
    h += '<div class="scroll"><table class="stbl nhl"><thead><tr>' + ph.map(x => "<th>" + esc(x) + "</th>").join("") + "</tr></thead><tbody>" + (a.past || []).map(r => {
      const isG = r.pos === "G";
      if (race) return "<tr><td>" + seasonLabel(r.season) + '</td><td><b>' + esc(r.name) + "</b></td><td>" + esc(r.team) + "</td><td>" + r.gp + "</td><td>" + r.goals + "</td><td>" + r.pts + "</td><td>" + (r.margin == null ? "–" : "+" + r.margin) + "</td></tr>";
      return "<tr><td>" + seasonLabel(r.season) + '</td><td><b>' + esc(r.name) + "</b></td><td>" + esc(r.team) + "</td><td>" + esc(r.pos) + "</td><td>" + r.gp + "</td><td>" + (isG ? "–" : r.goals) + "</td><td>" + (isG ? "–" : r.pts) +
        "</td><td>" + (isG ? "#" + r.saa_rank : r.pts_rank ? "#" + r.pts_rank : "–") + "</td><td>" + (isG ? f1(r.saa) : "–") + "</td><td>" + pct(r.tm_pp) + "</td></tr>";
    }).join("") + "</tbody></table></div>";
    $("race").innerHTML = h;
    $("race").querySelectorAll("table").forEach(sortableTable);
    try { history.replaceState(null, "", "#" + st.a); } catch (e) {}
  };
  $("app").innerHTML = '<div class="filters"><div class="field"><span class="flabel">Award</span><div class="seg" role="group" style="flex-wrap:wrap">' +
    order.map(k => '<button type="button" data-aw="' + k + '">' + esc({Hart: "Hart", Vezina: "Vezina", Norris: "Norris", Calder: "Calder", ArtRoss: "Art Ross", Richard: "Richard"}[k]) + "</button>").join("") + '</div></div></div><div id="race"></div>' +
    '<p class="note">Selke, Lady Byng, Jack Adams and the Conn Smythe are not modelled yet. Goalies are judged on saves above average (no shot quality) in the model; xG-based goalie value is shown elsewhere on the Goalies page.</p>';
  document.querySelectorAll("[data-aw]").forEach(b => b.onclick = () => { st.a = b.dataset.aw; draw(); });
  draw();
}

const ROUTES = {index: standings, futures: futuresPage, awards: awardsPage, teams, skaters: () => players("skaters"), goalies: () => players("goalies"), games};
boot(async meta => {
  META = meta;
  $("stamp").textContent = seasonLabel(meta.season) + " season · updated " + new Date(meta.updated_utc).toLocaleString(undefined, {weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"});
  ROUTES[PAGE]();
});
