/* Shared stats engine for the NBA, NBL and AFL sections (same look and behaviour as the NHL pages).
   One script, many pages (body[data-page]). Everything sport-specific comes from data/meta.json -> cfg.
   Data files are columnar: {season, cols:[{k,l,g,f,lo,t}], rows:[[identity..., value per col...]]}. */
const PAGE = document.body.dataset.page;
let META = null, CFG = null;
const memo = {};
let PO = false;                                   // false = regular season, true = playoffs / finals
const load = (kind, y) => { const f = kind + "_" + y + (PO ? "p" : ""); return memo[f] || (memo[f] = getJSON(f + ".json").then(d => hydrate(d, kind))); };
const seasons = () => (PO ? META.po_seasons : META.seasons) || [];
const hasPO = () => (META.po_seasons || []).length > 0;
let KIND = null;                                  // data kind of the current page (for the playoffs toggle)
const typeToggle = () => (!hasPO() || (KIND && CFG.po_kinds && !CFG.po_kinds.includes(KIND))) ? "" : '<div class="field"><span class="flabel">Season type</span><div class="seg" id="gt" role="group"><button type="button" data-p="0" aria-pressed="' + !PO +
  '">' + esc(CFG.reg_label || "Regular season") + '</button><button type="button" data-p="1" aria-pressed="' + PO + '">' + esc(CFG.po_label || "Playoffs") + "</button></div></div>";
const wireType = () => { const g = $("gt"); if (g) g.querySelectorAll("button").forEach(b => b.onclick = () => { PO = b.dataset.p === "1"; ROUTES[PAGE](); }); };

function hydrate(d, kind) {
  const ids = CFG.ids[kind];
  d.rows = d.rows.map(a => {
    const o = {};
    ids.forEach((k, i) => o[k] = a[i]);
    d.cols.forEach((c, i) => o[c.k] = a[ids.length + i]);
    o.season = d.season;
    return o;
  });
  return d;
}
function seasonLabel(y) {
  y = +y;
  if (CFG.season_style === "calendar") return String(y);
  if (CFG.season_style === "split_end") return (y - 1) + "-" + String(y % 100).padStart(2, "0");
  return y + "-" + String((y + 1) % 100).padStart(2, "0");
}
const tname = t => (META.teams && META.teams[t]) || t;

function fmt(v, f) {
  if (v == null || (typeof v === "number" && !isFinite(v))) return "–";
  switch (f) {
    case "pct": return (v * 100).toFixed(1) + "%";
    case "pct0": return Math.round(v * 100) + "%";
    case "sv": return v.toFixed(3).replace(/^0/, "");
    case "num0": return Math.round(v).toLocaleString();
    case "num1": return v.toFixed(1);
    case "num2": return v.toFixed(2);
    case "pm1": return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);
    case "pm": return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(Math.round(v)).toLocaleString();
    case "int": return Math.round(v).toLocaleString();
    default: return esc(v);
  }
}
const opt = (v, l, sel) => '<option value="' + esc(v) + '"' + (sel ? " selected" : "") + ">" + esc(l) + "</option>";
const seasonOpts = (cur, all) => (all ? opt("all", "All seasons", cur === "all") : "") +
  seasons().map(y => opt(y, seasonLabel(y) + (!PO && y === META.season && META.in_progress ? " (so far)" : ""), String(cur) === String(y))).join("");

/* ---------------- generic sortable table ---------------- */
function rankBy(rows, key, lo, idk) {
  const vals = rows.filter(r => r[key] != null && isFinite(r[key]));
  vals.sort((a, b) => lo ? a[key] - b[key] : b[key] - a[key]);
  const m = new Map(); let last = null, rank = 0;
  vals.forEach((r, i) => { if (r[key] !== last) { rank = i + 1; last = r[key]; } m.set(r[idk], rank); });
  return {m, n: vals.length};
}
function tableHTML(rows, cols, idCols, st, o) {
  o = o || {};
  const idk = o.idk || "team";
  const th = (k, l, t, cls) => '<th scope="col" tabindex="0" data-k="' + esc(k) + '"' + (cls ? ' class="' + cls + '"' : "") + (t ? ' title="' + esc(t) + '"' : "") +
    (st.sortKey === k ? ' aria-sort="' + (st.sortDir > 0 ? "ascending" : "descending") + '"' : "") + ">" + esc(l) + "</th>";
  const rk = {};
  if (o.shade) cols.forEach(c => { if (c.f !== "text" && !(CFG.noshade || []).includes(c.k) && new Set(o.shade.map(r => r[c.k])).size > 1) rk[c.k] = rankBy(o.shade, c.k, c.lo, idk); });
  const head = "<tr>" + (o.rank ? "<th>#</th>" : "") + idCols.map(c => th(c.k, c.l, c.t, c.cls)).join("") + cols.map(c => th(c.k, c.l, c.t || c.l)).join("") + "</tr>";
  const body = rows.map((r, i) => "<tr>" + (o.rank ? "<td>" + (i + 1) + "</td>" : "") + idCols.map(c => c.cell ? c.cell(r) : "<td>" + esc(r[c.k]) + "</td>").join("") +
    cols.map(c => {
      const R = rk[c.k], rank = R ? R.m.get(r[idk]) : null;
      return '<td class="' + (c.f === "text" ? "txt " : "") + (R ? qClass(rank, R.n) : "") + '">' + fmt(r[c.k], c.f) + (rank && o.ranks ? "<small>" + rank + "</small>" : "") + "</td>";
    }).join("") + "</tr>").join("");
  return '<div class="scroll"><table class="stbl nhl' + (o.rank ? " ranked" : "") + '"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
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
const keyList = kind => (CFG.key || {})[kind] || [];
const groupsOf = (cols, kind) => { const has = keyList(kind).some(k => cols.some(c => c.k === k)); return [...(has ? ["Key stats"] : []), "All", ...new Set(cols.map(c => c.g))]; };
function visibleCols(cols, group, kind) {
  const pin = CFG.pinned || [];
  if (group === "Key stats") return keyList(kind).map(k => cols.find(c => c.k === k)).filter(Boolean);
  return cols.filter(c => group === "All" || c.g === group || pin.includes(c.k));
}
const teamCell = r => "<td><b>" + esc(r.team) + "</b> <small>" + esc(r.name || tname(r.team)) + "</small></td>";
const mergeCols = ds => { const seen = new Map(); ds.forEach(d => d.cols.forEach(c => { if (!seen.has(c.k)) seen.set(c.k, c); })); return [...seen.values()]; };

/* ---------------- standings / ladder ---------------- */
async function standings() {
  const S = CFG.standings;
  const views = (META.groupings || []).map(g => g.name);
  const st = {y: META.seasons[0], view: views[0] || "League", sortKey: S.sort, sortDir: -1};
  const draw = async () => {
    const d = await load("team", st.y);
    const cols = S.cols.map(k => d.cols.find(c => c.k === k)).filter(Boolean).map(c => ({...c, l: (S.alias || {})[c.k] || c.l}));
    const rows = d.rows.slice();
    const G = (META.groupings || []).find(g => g.name === st.view);
    const by = (a, b) => S.order.reduce((acc, [k, dir]) => acc || ((b[k] ?? -1e9) - (a[k] ?? -1e9)) * dir, 0);
    let groups = [["League", rows]];
    if (G && G.groups) {
      const gmap = (G.by_season && G.by_season[st.y]) || G.groups;
      groups = Object.entries(gmap).map(([n, ts]) => [n, rows.filter(r => ts.includes(r.team))]).filter(([, rs]) => rs.length);
      const left = rows.filter(r => !groups.some(([, rs]) => rs.includes(r)));
      if (left.length) groups.push(["Other", left]);
    }
    const idCols = [{k: "team", l: "Team", cell: teamCell}];
    const all = cols.concat([{k: "team", f: "text"}]);
    let html = "";
    groups.forEach(([title, rs]) => {
      rs = st.sortKey === S.sort && st.sortDir === -1 ? rs.sort(by) : sortBy(rs, st, all);
      html += (groups.length > 1 || title !== "League" ? "<h2>" + esc(title) + "</h2>" : "") + tableHTML(rs, cols, idCols, st, {rank: true, shade: d.rows});
    });
    $("tbl").innerHTML = html;
    $("tbl").querySelectorAll(".scroll").forEach(s => wireSort(s, st, draw, all));
    $("note").innerHTML = S.note || "";
  };
  $("app").innerHTML = '<div class="filters"><div class="field"><label for="ss">Season</label><select id="ss">' + META.seasons.map(y => opt(y, seasonLabel(y) + (y === META.season && META.in_progress ? " (so far)" : ""), y === st.y)).join("") + "</select></div>" +
    (views.length > 1 ? '<div class="field"><span class="flabel">Group by</span><div class="seg" id="vw" role="group">' + views.map(v => '<button type="button" data-v="' + esc(v) + '" aria-pressed="' + (v === st.view) + '">' + esc(v) + "</button>").join("") + "</div></div>" : "") +
    '</div><div id="tbl"></div><p class="note" id="note"></p>';
  $("ss").onchange = e => { st.y = +e.target.value; draw(); };
  if ($("vw")) $("vw").querySelectorAll("button").forEach(b => b.onclick = () => { st.view = b.dataset.v; st.sortKey = S.sort; st.sortDir = -1; $("vw").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); draw(); });
  draw();
}

/* ---------------- team stats ---------------- */
async function teams() {
  KIND = "team";
  const st = {y: seasons()[0], mode: "season", group: "Key stats", sortKey: CFG.team_sort || "wins", sortDir: -1, q: "", stat: CFG.team_sort || "wins", from: null, to: null};
  const seasonDraw = async () => {
    const d = await load("team", st.y);
    const groups = groupsOf(d.cols, "teams");
    if (!groups.includes(st.group)) st.group = groups[0];
    const cols = visibleCols(d.cols, st.group, "teams");
    let rows = d.rows.filter(r => !st.q || (r.team + " " + r.name).toLowerCase().includes(st.q));
    const all = d.cols.concat([{k: "team", f: "text"}]);
    rows = sortBy(rows, st, all);
    $("out").innerHTML = tableHTML(rows, cols, [{k: "team", l: "Team", cell: teamCell}], st, {shade: d.rows, ranks: true});
    wireSort($("out"), st, seasonDraw, all);
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; seasonDraw(); });
  };
  const yearDraw = async () => {
    const ys = seasons().slice().reverse();
    const ds = await Promise.all(seasons().map(y => load("team", y)));
    const byY = {}; ds.forEach(d => byY[d.season] = d);
    const col = mergeCols(ds).find(c => c.k === st.stat) || ds[0].cols[0];
    st.from = st.from && ys.includes(+st.from) ? +st.from : ys[0];
    st.to = st.to && ys.includes(+st.to) ? +st.to : ys[ys.length - 1];
    const shown = ys.filter(y => y >= Math.min(st.from, st.to) && y <= Math.max(st.from, st.to));
    const teamsAll = [...new Set(ds.flatMap(d => d.rows.map(r => r.team)))];
    let rows = teamsAll.map(t => {
      const o = {team: t, name: tname(t)};
      shown.forEach(y => { const r = byY[y] && byY[y].rows.find(x => x.team === t); o["y" + y] = r ? r[col.k] : null; });
      const vs = shown.map(y => o["y" + y]).filter(v => v != null);
      o.change = vs.length > 1 ? vs[vs.length - 1] - vs[0] : null;
      o.avg = vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
      return o;
    }).filter(r => !st.q || (r.team + " " + r.name).toLowerCase().includes(st.q));
    if (!st.ysort) st.ysort = {sortKey: "y" + shown[shown.length - 1], sortDir: col.lo ? 1 : -1};
    rows = sortBy(rows, st.ysort, [{k: "team", f: "text"}]);
    const flt = shown.map(y => rankBy(byY[y] ? byY[y].rows : [], col.k, col.lo, "team"));
    const th = (k, l) => '<th scope="col" tabindex="0" data-k="' + k + '"' + (st.ysort.sortKey === k ? ' aria-sort="' + (st.ysort.sortDir > 0 ? "ascending" : "descending") + '"' : "") + ">" + esc(l) + "</th>";
    $("out").innerHTML = '<p class="note">' + esc(col.l) + (col.t && col.t !== col.l ? " — " + esc(col.t) : "") + ". Shading ranks each season's league (best to worst). Change is last shown season minus first.</p>" +
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
  const gs = {}; d0.cols.forEach(c => (gs[c.g] = gs[c.g] || []).push(c));
  const ysOld = seasons().slice().reverse();
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><span class="flabel">View</span><div class="seg" id="modes" role="group"><button type="button" data-m="season">Season table</button><button type="button" data-m="year">Year by year</button></div></div>' +
    '<div class="field" id="seasonF"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y) + "</select></div>" +
    '<div class="field" id="statF"><label for="stat">Stat</label><select id="stat">' + Object.entries(gs).map(([g, cs]) => '<optgroup label="' + esc(g) + '">' + cs.map(c => opt(c.k, c.l, c.k === st.stat)).join("") + "</optgroup>").join("") + "</select></div>" +
    '<div class="field" id="rangeF"><label for="fy">From → to</label><span class="pair"><select id="fy">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[0])).join("") + '</select><select id="ty">' + ysOld.map(y => opt(y, seasonLabel(y), y === ysOld[ysOld.length - 1])).join("") + "</select></span></div>" +
    '<div class="field"><label for="q">Team</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">Click any heading to sort high to low, again for low to high. Small numbers are league ranks; shading runs from best (teal) to worst (orange). ' + (CFG.team_note || "") + "</p>";
  wireType();
  $("modes").querySelectorAll("button").forEach(b => b.onclick = () => { st.mode = b.dataset.m; draw(); });
  $("ss").onchange = e => { st.y = +e.target.value; draw(); };
  $("stat").onchange = e => { st.stat = e.target.value; st.ysort = null; draw(); };
  $("fy").onchange = e => { st.from = +e.target.value; draw(); };
  $("ty").onchange = e => { st.to = +e.target.value; draw(); };
  $("q").oninput = e => { st.q = e.target.value.trim().toLowerCase(); draw(); };
  draw();
}

/* ---------------- players ---------------- */
async function players() {
  KIND = "players"; if (CFG.po_kinds && !CFG.po_kinds.includes("players")) PO = false;
  const P = CFG.players;
  const st = {y: seasons()[0], group: "Key stats", sortKey: P.sort, sortDir: -1, q: "", team: "", pos: "", min: PO ? 1 : (P.min_default || 0), limit: 100};
  const idsText = CFG.ids.players.map(k => ({k, f: "text"})).concat([{k: "season", f: "int"}]);
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") { const ds = await Promise.all(seasons().map(y => load("players", y))); cols = mergeCols(ds); rows = ds.flatMap(d => d.rows); }
    else { const d = await load("players", st.y); cols = d.cols; rows = d.rows; }
    const groups = groupsOf(cols, "players");
    if (!groups.includes(st.group)) st.group = groups[0];
    const teams = [...new Set(rows.flatMap(r => String(r.team || "").split(",")).filter(Boolean))].sort();
    $("team").innerHTML = opt("", "All teams", !st.team) + teams.map(t => opt(t, t, t === st.team)).join("");
    const gp = r => r[P.gp_key] || 0;
    const posOk = r => !st.pos || String(r.pos || "").split(/[ ,\/-]/).some(p => p === st.pos || (P.pos_groups && (P.pos_groups[st.pos] || []).includes(p)));
    rows = rows.filter(r => gp(r) >= st.min && posOk(r) && (!st.team || String(r.team).split(",").includes(st.team)) && (!st.q || String(r.name).toLowerCase().includes(st.q)));
    rows = sortBy(rows, st, cols.concat(idsText));
    const total = rows.length;
    rows = rows.slice(0, st.limit);
    const shown = visibleCols(cols, st.group, "players");
    const idCols = [{k: "name", l: "Player", cell: r => "<td><b>" + esc(r.name) + "</b></td>"}];
    if (st.y === "all") idCols.push({k: "season", l: "Season", cell: r => "<td>" + seasonLabel(r.season) + "</td>"});
    idCols.push({k: "team", l: "Team", cell: r => "<td>" + esc(r.team) + "</td>"});
    if (CFG.ids.players.includes("pos")) idCols.push({k: "pos", l: "Pos", cell: r => "<td>" + esc(r.pos || "") + "</td>"});
    $("out").innerHTML = tableHTML(rows, shown, idCols, st, {rank: true}) +
      '<p class="note">Showing ' + rows.length + " of " + total + " rows" + (total > rows.length ? ' · <a href="#" id="more">show 100 more</a>' : "") + ". Click a heading to sort.</p>";
    wireSort($("out"), st, draw, cols.concat(idsText));
    const m = $("more"); if (m) m.onclick = e => { e.preventDefault(); st.limit += 100; draw(); };
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; draw(); });
  };
  const posSel = P.positions ? '<div class="field"><label for="pos">Position</label><select id="pos">' + P.positions.map(([v, l]) => opt(v, l)).join("") + "</select></div>" : "";
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' + posSel +
    '<div class="field"><label for="min">Min games</label><input id="min" type="number" min="0" value="' + st.min + '" style="width:84px"></div>' +
    '<div class="field"><label for="q">Player</label><input id="q" type="search" placeholder="Search"></div></div><div id="grp"></div><div id="out"></div>' +
    '<p class="note">' + (P.note || "") + " 'All seasons' lists every player-season since " + seasonLabel(seasons()[seasons().length - 1]) + ", so you can rank the best single seasons.</p>";
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
  KIND = "games";
  const G = CFG.games;
  const st = {y: seasons()[0], team: "", ha: "", res: "", sortKey: "date", sortDir: -1, group: null, limit: 100};
  const ids = CFG.ids.games.map(k => ({k, f: "text"}));
  const draw = async () => {
    let cols, rows;
    if (st.y === "all") { const ds = await Promise.all(seasons().map(y => load("games", y))); cols = mergeCols(ds); rows = ds.flatMap(d => d.rows); }
    else { const d = await load("games", st.y); cols = d.cols; rows = d.rows; }
    const groups = ["All", ...new Set(cols.map(c => c.g))];
    if (!st.group || !groups.includes(st.group)) st.group = groups[1] || "All";
    const teams = [...new Set(rows.map(r => r.team))].sort();
    $("team").innerHTML = opt("", "All teams", !st.team) + teams.map(t => opt(t, t + " · " + tname(t), t === st.team)).join("");
    rows = rows.filter(r => (!st.team || r.team === st.team) && (!st.ha || r.ha === st.ha) && (!st.res || r.res === st.res));
    rows = sortBy(rows, st, cols.concat(ids));
    const total = rows.length; rows = rows.slice(0, st.limit);
    const pin = G.pinned || [];
    const shown = cols.filter(c => st.group === "All" || c.g === st.group || pin.includes(c.k));
    const idCols = [{k: "date", l: "Date", cell: r => '<td class="txt dt">' + esc(r.date) + "</td>"}, {k: "team", l: "Team", cell: r => "<td><b>" + esc(r.team) + "</b></td>"},
      {k: "opp", l: "Opp", cell: r => "<td>" + (r.ha === "A" ? "@ " : r.ha === "N" ? "v " : "vs ") + esc(r.opp) + "</td>"}, {k: "res", l: "Res", cell: r => '<td class="res-' + esc(r.res) + '">' + esc(r.res) + "</td>"}];
    if (CFG.ids.games.includes("rnd")) idCols.splice(1, 0, {k: "rnd", l: "Round", cell: r => "<td>" + esc(r.rnd) + "</td>"});
    $("out").innerHTML = tableHTML(rows, shown, idCols, st) + '<p class="note">Showing ' + rows.length + " of " + total + " games" + (total > rows.length ? ' · <a href="#" id="more">show 100 more</a>' : "") + ". " + (G.note || "") + "</p>";
    wireSort($("out"), st, draw, cols.concat(ids));
    const m = $("more"); if (m) m.onclick = e => { e.preventDefault(); st.limit += 100; draw(); };
    $("grp").innerHTML = chips(groups, st.group);
    $("grp").querySelectorAll("button").forEach(b => b.onclick = () => { st.group = b.dataset.g; draw(); });
  };
  $("app").innerHTML = '<div class="filters">' + typeToggle() + '<div class="field"><label for="ss">Season</label><select id="ss">' + seasonOpts(st.y, true) + "</select></div>" +
    '<div class="field"><label for="team">Team</label><select id="team"></select></div>' +
    '<div class="field"><label for="ha">Venue</label><select id="ha">' + [["", "Home & away"], ["H", "Home"], ["A", "Away"]].map(([v, l]) => opt(v, l)).join("") + "</select></div>" +
    '<div class="field"><label for="res">Result</label><select id="res">' + [["", "All"]].concat(G.results).map(([v, l]) => opt(v, l)).join("") + '</select></div></div><div id="grp"></div><div id="out"></div>';
  wireType();
  $("ss").onchange = e => { st.y = e.target.value === "all" ? "all" : +e.target.value; st.limit = 100; draw(); };
  ["team", "ha", "res"].forEach(k => $(k).onchange = e => { st[k] = e.target.value; st.limit = 100; draw(); });
  draw();
}

/* ---------------- futures ---------------- */
async function futuresPage() {
  const F = await getJSON("futures.json");
  const T = F.teams || [];
  const pcx = v => v == null ? "–" : v < 0.0005 ? "<0.1%" : v > 0.9995 ? ">99.9%" : v < 0.1 ? (v * 100).toFixed(1) + "%" : Math.round(v * 100) + "%";
  const P = F.proj;
  const sk = {key: F.main || (F.cols[F.cols.length - 1] || {}).k, dir: -1};
  const hasGroup = T.some(r => r.group);
  const head = [["Team", "team"]].concat(hasGroup ? [[F.group_label || "Group", null]] : [], [["GP", null], ["Record", null]]);
  const EX = F.extra || [];
  EX.forEach(c => head.push([c.l, c.k, c.t]));
  if (T.some(r => r.rating != null)) head.push(["Rating", "rating", F.rating_note]);
  head.push([P.l, P.k, "Average of the simulated seasons"], ["10–90%", null, "Range containing 80% of simulated seasons"]);
  F.cols.forEach(c => head.push([c.l, c.k, c.t]));
  const cellsFor = r => {
    let h = "<td><b>" + esc(r.team) + "</b> <small>" + esc(r.name || tname(r.team)) + "</small></td>" + (hasGroup ? "<td>" + esc(r.group || "") + "</td>" : "") + "<td>" + (r.gp ?? "–") + "</td><td>" + esc(r.record || "") + "</td>";
    EX.forEach(c => { h += "<td>" + fmt(r[c.k], c.f) + "</td>"; });
    if (head.some(x => x[1] === "rating")) h += "<td>" + (r.rating == null ? "–" : fmt(r.rating, "pm1")) + "</td>";
    h += "<td>" + fmt(r[P.k], P.f || "num1") + "</td><td>" + (r[P.lo] == null ? "–" : fmt(r[P.lo], "int") + "–" + fmt(r[P.hi], "int")) + "</td>";
    return h + F.cols.map(c => "<td" + (c.k === F.main ? ' style="font-weight:700"' : "") + ">" + pcx(r[c.k]) + "</td>").join("");
  };
  const draw = () => {
    const rs = T.slice().sort((a, b) => sk.key === "team" ? a.team.localeCompare(b.team) * -sk.dir : ((b[sk.key] ?? -1) - (a[sk.key] ?? -1)) * (sk.dir === -1 ? 1 : -1));
    $("ft").querySelector("tbody").innerHTML = rs.map(r => "<tr>" + cellsFor(r) + "</tr>").join("");
    $("ft").querySelectorAll("th").forEach((h, i) => h.setAttribute("aria-sort", head[i][1] === sk.key ? (sk.dir > 0 ? "ascending" : "descending") : "none"));
  };
  const L = F.line;
  $("app").innerHTML = (F.status ? '<p class="note"><b>' + esc(F.status) + "</b></p>" : "") +
    '<p class="note">' + esc(F.intro || "") + " " + (F.sims ? F.sims.toLocaleString() + " simulations. " : "") + "Chances only. Click a heading to sort.</p>" +
    '<div class="scroll"><table class="stbl nhl" id="ft"><thead><tr>' + head.map(([h, k, t]) => "<th" + (k ? ' data-k="' + k + '" tabindex="0"' : "") + (t ? ' title="' + esc(t) + '"' : "") + ">" + esc(h) + "</th>").join("") + "</tr></thead><tbody></tbody></table></div>" +
    (L ? '<h2 style="margin-top:22px">' + esc(L.label) + '</h2><p class="note">Pick a team and a line to see the chance it finishes over or under.</p>' +
      '<div class="filters"><div class="field"><label for="pt">Team</label><select id="pt">' + T.slice().sort((a, b) => a.team.localeCompare(b.team)).map(r => opt(r.team, r.team + " · " + (r.name || tname(r.team)))).join("") + "</select></div>" +
      '<div class="field"><label for="pl">Line</label><input id="pl" type="number" step="0.5" style="width:100px"></div></div><div id="pout" class="panel" style="margin-top:10px"></div>' : "") +
    (F.backtest_html ? '<h2 style="margin-top:22px">How good is it?</h2>' + F.backtest_html : "") +
    (F.about && F.about.length ? '<h2 style="margin-top:22px">What it does and does not know</h2><ul class="note" style="max-width:80ch">' + F.about.map(x => "<li>" + esc(x) + "</li>").join("") + "</ul>" : "");
  draw();
  $("ft").querySelectorAll("th[data-k]").forEach(h => { const go = () => { const k = h.dataset.k; sk.dir = sk.key === k ? -sk.dir : -1; sk.key = k; draw(); }; h.style.cursor = "pointer"; h.onclick = go; h.onkeydown = e => { if (e.key === "Enter") go(); }; });
  if (L) {
    const upd = () => {
      const r = T.find(x => x.team === $("pt").value); const v = parseFloat($("pl").value);
      if (!r || !isFinite(v) || !r.over) { $("pout").textContent = ""; return; }
      const ge = x => { const i = Math.round(x) - L.min; return i <= 0 ? 1 : i >= r.over.length ? 0 : r.over[i]; };
      const over = ge(Math.floor(v) + 1), under = 1 - ge(Math.ceil(v)), push = Number.isInteger(v) ? ge(v) - ge(v + 1) : 0;
      $("pout").innerHTML = "<div><b>" + esc(r.name || r.team) + "</b> projected " + fmt(r[P.k], "num1") + " " + esc(L.unit) + " (10–90%: " + r[P.lo] + "–" + r[P.hi] + "). Line " + v + ": <b>over " + pct(over) + "</b> · <b>under " + pct(under) + "</b>" + (push > 0.0005 ? " · exactly " + v + " " + pct(push) : "") + "</div>";
    };
    $("pt").onchange = () => { const r = T.find(x => x.team === $("pt").value); const m = Math.round(r[P.k] * 2) / 2; $("pl").value = Number.isInteger(m) ? m + 0.5 : m; upd(); };
    $("pl").oninput = upd;
    $("pt").onchange();
  }
}

/* ---------------- awards ---------------- */
async function awardsPage() {
  const A = await getJSON("awards.json");
  const order = (A.order || Object.keys(A.awards)).filter(k => A.awards[k]);
  const st = {a: (location.hash.slice(1) && A.awards[location.hash.slice(1)]) ? location.hash.slice(1) : order[0]};
  const draw = () => {
    document.querySelectorAll("[data-aw]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.aw === st.a)));
    const a = A.awards[st.a];
    let h = "<h2>" + esc(a.title) + "</h2>";
    if (a.backtest) {
      const b = a.backtest;
      h += '<p class="note"><b>Track record.</b> Tested one season at a time with that season held out: the model\'s top pick won ' + b.top1 + " of " + b.n + " seasons (top three: " + b.top3 +
        ")." + (b.leader_hits != null ? " Simply picking the " + esc(b.leader_label || "stat leader") + " would have won " + b.leader_hits + "." : "") + " On average it gave the eventual winner " + pct(b.avg_p) + ". Voters are not fully predictable, so treat these as chances, not locks.</p>";
    }
    if (a.note) h += '<p class="note">' + esc(a.note) + "</p>";
    const cols = a.cols || [];
    const rows = a.current || [];
    if (rows.length) {
      h += '<div class="scroll"><table class="stbl nhl"><thead><tr><th>Player</th><th>Team</th>' + cols.map(c => "<th" + (c.t ? ' title="' + esc(c.t) + '"' : "") + ">" + esc(c.l) + "</th>").join("") + (a.has_prob === false ? "" : "<th>Chance</th>") + "</tr></thead><tbody>" +
        rows.map(r => "<tr><td><b>" + esc(r.name) + "</b></td><td>" + esc(r.team) + "</td>" + cols.map(c => "<td>" + fmt(r[c.k], c.f) + "</td>").join("") + (a.has_prob === false ? "" : '<td data-v="' + r.prob + '"><b>' + pct(r.prob) + "</b></td>") + "</tr>").join("") + "</tbody></table></div>";
    } else h += '<p class="note">' + esc(a.empty || "No current-season candidates yet.") + "</p>";
    if (a.past && a.past.length) {
      const pc = a.past_cols || cols;
      h += '<h2 style="margin-top:22px">Past winners</h2><p class="note">' + esc(a.past_note || "Each winner's final numbers and where they ranked.") + "</p>" +
        '<div class="scroll"><table class="stbl nhl"><thead><tr><th>Season</th><th>Winner</th><th>Team</th>' + pc.map(c => "<th>" + esc(c.l) + "</th>").join("") + "</tr></thead><tbody>" +
        a.past.map(r => "<tr><td>" + seasonLabel(r.season) + "</td><td><b>" + esc(r.name) + "</b></td><td>" + esc(r.team) + "</td>" + pc.map(c => "<td>" + fmt(r[c.k], c.f) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>";
    }
    $("race").innerHTML = h;
    $("race").querySelectorAll("table").forEach(sortableTable);
    try { history.replaceState(null, "", "#" + st.a); } catch (e) {}
  };
  $("app").innerHTML = (A.intro ? '<p class="note">' + esc(A.intro) + "</p>" : "") + '<div class="filters"><div class="field"><span class="flabel">Award</span><div class="seg" role="group" style="flex-wrap:wrap">' +
    order.map(k => '<button type="button" data-aw="' + k + '">' + esc(A.awards[k].short || k) + "</button>").join("") + '</div></div></div><div id="race"></div>';
  document.querySelectorAll("[data-aw]").forEach(b => b.onclick = () => { st.a = b.dataset.aw; draw(); });
  draw();
}

const ROUTES = {index: standings, standings, futures: futuresPage, awards: awardsPage, teams, players, games};
boot(async meta => {
  META = meta; CFG = meta.cfg;
  const s = $("stamp");
  if (s) s.textContent = seasonLabel(meta.season) + " season · updated " + new Date(meta.updated_utc).toLocaleString(undefined, {weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"});
  ROUTES[PAGE]();
});
