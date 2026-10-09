/* Player stat pages (QBs, Rushing, Receiving, Defense, Kicking & returns), 2018 onward.
   Season table with filters, sortable columns shaded by fifths among the players shown; click a player for
   career by season and that season's weekly game log. */
const C = (key, label, fmt, dir, note) => ({key, label, fmt, dir, note});
const VIEWS = {
  qb: {title: "Quarterbacks", vol: ["att", "Min. attempts", [0, 25, 50, 100, 200, 300], 50], sort: "epa_db",
       intro: "Every passer since 2018. EPA per dropback includes sacks; ANY/A is adjusted net yards per attempt (TD +20, INT −45, sacks count). CPOE, time to throw and aggressiveness are NFL Next Gen Stats; pressure and bad-throw rates are Pro Football Reference charting.",
       cols: [C("games", "G", "int", null), C("att", "Att", "int", 1), C("cmp_pct", "Cmp %", "pct", 1), C("pass_yds", "Pass yds", "int", 1),
              C("pass_yds_g", "Yds/G", "num1", 1), C("pass_td", "TD", "int", 1), C("int", "INT", "int", -1), C("ypa", "Y/A", "num2", 1),
              C("anya", "ANY/A", "num2", 1), C("epa_db", "EPA/dropback", "num2", 1), C("pass_epa", "Pass EPA", "num1", 1),
              C("cpoe", "CPOE", "pct", 1), C("td_pct", "TD %", "pct", 1), C("int_pct", "INT %", "pct", -1), C("sacks", "Sacked", "int", -1),
              C("sack_pct", "Sack %", "pct", -1), C("adot", "aDOT", "num1", null, "Average depth of target"), C("ttt", "Time to throw", "num2", null),
              C("aggr", "Aggressive", "pct", null, "Throws into tight windows (NGS)"), C("press_pct", "Pressured %", "pct", -1),
              C("bad_pct", "Bad throw %", "pct", -1), C("pass_fd", "1st downs", "int", 1), C("pass_20", "20+ comp", "int", 1),
              C("car", "Rush att", "int", null), C("rush_yds", "Rush yds", "int", 1), C("rush_td", "Rush TD", "int", 1),
              C("fum_lost", "Fum lost", "int", -1), C("off_snap_pct", "Snap %", "pct", null)]},
  rb: {title: "Rushing", vol: ["car", "Min. carries", [0, 10, 25, 50, 100, 150], 25], sort: "rush_yds",
       intro: "Every ball carrier since 2018, with receiving work. Rush yards over expected (RYOE), NGS efficiency and 8+ box rate are NFL Next Gen Stats; yards before and after contact and broken tackles are Pro Football Reference charting.",
       pos: ["RB", "QB", "WR", "TE", "FB"],
       cols: [C("games", "G", "int", null), C("car", "Car", "int", 1), C("rush_yds", "Rush yds", "int", 1), C("rush_yds_g", "Yds/G", "num1", 1),
              C("ypc", "YPC", "num2", 1), C("rush_td", "TD", "int", 1), C("epa_car", "EPA/carry", "num2", 1), C("rush_epa", "Rush EPA", "num1", 1),
              C("ryoe_att", "RYOE/att", "num2", 1), C("ryoe", "RYOE", "num1", 1), C("ybc_att", "YBC/att", "num2", 1), C("yac_att", "YAC/att", "num2", 1),
              C("btk", "Broken tkl", "int", 1), C("rush_fd", "1st downs", "int", 1), C("rush_10", "10+ runs", "int", 1), C("rush_20", "20+ runs", "int", 1),
              C("box8", "8+ box %", "pct", null), C("ngs_eff", "NGS eff.", "num2", null, "Distance travelled per rushing yard; lower is more north-south"),
              C("tgt", "Tgt", "int", 1), C("rec", "Rec", "int", 1), C("rec_yds", "Rec yds", "int", 1), C("scrim_yds", "Scrim yds", "int", 1),
              C("tot_td", "Total TD", "int", 1), C("fum_lost", "Fum lost", "int", -1), C("off_snap_pct", "Snap %", "pct", null)]},
  wr: {title: "Receiving", vol: ["tgt", "Min. targets", [0, 10, 20, 40, 60, 100], 20], sort: "rec_yds",
       intro: "Every pass catcher since 2018. Target share, air-yards share and WOPR (weighted opportunity) use team totals; separation, cushion and YAC over expected are NFL Next Gen Stats; drops are Pro Football Reference charting.",
       pos: ["WR", "TE", "RB", "FB"],
       cols: [C("games", "G", "int", null), C("tgt", "Tgt", "int", 1), C("rec", "Rec", "int", 1), C("catch_pct", "Catch %", "pct", 1),
              C("rec_yds", "Rec yds", "int", 1), C("rec_yds_g", "Yds/G", "num1", 1), C("ypr", "Y/R", "num1", 1), C("ypt", "Y/Tgt", "num2", 1),
              C("rec_td", "TD", "int", 1), C("epa_tgt", "EPA/tgt", "num2", 1), C("rec_epa", "Rec EPA", "num1", 1), C("tgt_share", "Tgt share", "pct", 1),
              C("air_share", "Air share", "pct", 1), C("wopr", "WOPR", "num2", 1), C("rec_air", "Air yds", "int", 1), C("rec_adot", "aDOT", "num1", null),
              C("yac", "YAC", "int", 1), C("yacoe", "YAC over exp.", "num2", 1), C("sep", "Separation", "num2", 1), C("cushion", "Cushion", "num2", null),
              C("rec_fd", "1st downs", "int", 1), C("rec_20", "20+ catches", "int", 1), C("drops", "Drops", "int", -1), C("drop_pct", "Drop %", "pct", -1),
              C("btk", "Broken tkl", "int", 1), C("off_snap_pct", "Snap %", "pct", null)]},
  def: {title: "Defensive players", vol: ["tkl", "Min. tackles", [0, 5, 10, 20, 40, 60], 5], sort: "dsacks",
        intro: "Every defender since 2018. Pressures, hurries, coverage (targets, completion %, yards per target and TDs allowed) and missed tackles are Pro Football Reference charting; the rest is official play-by-play.",
        pos: ["DL", "LB", "DB"], posKey: "grp",
        cols: [C("games", "G", "int", null), C("tkl", "Tackles", "int", 1), C("solo", "Solo", "int", 1), C("tfl", "TFL", "int", 1),
               C("dsacks", "Sacks", "num1", 1), C("qb_hits", "QB hits", "int", 1), C("pressures", "Pressures", "int", 1), C("hurries", "Hurries", "int", 1),
               C("dint", "INT", "int", 1), C("pd", "PD", "int", 1), C("ff", "FF", "int", 1), C("fr", "FR", "int", 1), C("dtd", "TD", "int", 1),
               C("tgt_allowed", "Tgt allowed", "int", null), C("cmp_allowed", "Cmp % allowed", "pct", -1), C("ypt_allowed", "Y/Tgt allowed", "num1", -1),
               C("td_allowed", "TD allowed", "int", -1), C("missed", "Missed tkl", "int", -1), C("missed_pct", "Missed %", "pct", -1),
               C("def_snap_pct", "Snap %", "pct", null)]},
  k: {title: "Kicking, punting and returns", vol: null, sort: "fgm",
      intro: "Kickers, punters and returners since 2018. Net punting average subtracts return yards and touchbacks.",
      cols: [C("games", "G", "int", null), C("fgm", "FGM", "int", 1), C("fga", "FGA", "int", null), C("fg_pct", "FG %", "pct", 1),
             C("fg40", "40–49 %", "pct", 1), C("fg50", "50+ %", "pct", 1), C("fg50m", "50+ made", "int", 1), C("fg_long", "Long", "int", 1),
             C("xpm", "XPM", "int", 1), C("xpa", "XPA", "int", null), C("xp_pct", "XP %", "pct", 1), C("punts", "Punts", "int", null),
             C("punt_avg", "Punt avg", "num1", 1), C("punt_net", "Net avg", "num1", 1), C("punt_in20", "Inside 20 %", "pct", 1),
             C("kr", "KR", "int", null), C("kr_avg", "KR avg", "num1", 1), C("pr", "PR", "int", null), C("pr_avg", "PR avg", "num1", 1),
             C("st_td", "Return TD", "int", 1)]},
};
const V = VIEWS[document.body.dataset.page];
const ST = {season: null, rows: [], sortKey: V.sort, sortDir: -1, q: "", team: "", pos: "", rookies: false, vol: V.vol ? V.vol[3] : 0, sel: null};
let INDEX = null, CAREER = null;

async function loadSeason(y) {
  const P = await getJSON("players_" + y + ".json");
  const n = P.data.id.length, rows = [];
  for (let i = 0; i < n; i++) { const r = {}; P.cols.forEach(c => { r[c] = P.data[c][i]; }); rows.push(r); }
  return rows;
}
function eligible(r) {
  if (V === VIEWS.k) return (r.fga || 0) > 0 || (r.punts || 0) > 0 || (r.kr || 0) + (r.pr || 0) >= 5;
  if (V === VIEWS.def) return ["DL", "LB", "DB"].includes(r.grp) && (r.tkl || 0) + (r.dsacks || 0) > 0;
  if (V === VIEWS.qb) return (r.att || 0) > 0;
  if (V === VIEWS.rb) return (r.car || 0) > 0;
  if (V === VIEWS.wr) return (r.tgt || 0) > 0;
  return true;
}
function filtered() {
  return ST.rows.filter(r => eligible(r) && (!V.vol || (r[V.vol[0]] || 0) >= ST.vol) && (!ST.team || r.team === ST.team) &&
    (!ST.pos || r[V.posKey || "pos"] === ST.pos) && (!ST.rookies || r.rookie === 1) &&
    (!ST.q || (r.name + " " + r.team).toLowerCase().includes(ST.q)));
}
function ranks(rows, c) {
  const vals = rows.map(r => r[c.key]).filter(v => typeof v === "number" && isFinite(v)).sort((a, b) => c.dir > 0 ? b - a : a - b);
  const m = new Map(); rows.forEach(r => { const v = r[c.key]; if (typeof v === "number" && isFinite(v)) m.set(r.id, vals.indexOf(v) + 1); });
  return {m, n: vals.length};
}
function th(key, label, note, extra) {
  const s = ST.sortKey === key ? ' aria-sort="' + (ST.sortDir > 0 ? "ascending" : "descending") + '"' : "";
  return '<th scope="col" tabindex="0" data-k="' + key + '"' + (note ? ' title="' + esc(note) + '"' : "") + (extra || "") + s + '>' + esc(label) + '</th>';
}
function render() {
  const rows0 = filtered();
  const R = {}; V.cols.forEach(c => { if (c.dir) R[c.key] = ranks(rows0, c); });
  const rows = sortRows(rows0, ST.sortKey, ST.sortDir, (r, k) => k === "name" ? r.name : r[k]).slice(0, 400);
  $("thead").innerHTML = '<tr>' + th("name", "Player") + th("team", "Team") + th("pos", "Pos") + th("age", "Age") + V.cols.map(c => th(c.key, c.label, c.note)).join("") + '</tr>';
  $("tbody").innerHTML = rows.map(r => '<tr><td><button type="button" class="plink" data-id="' + esc(r.id) + '">' + esc(r.name) + '</button>' + (r.rookie ? ' <span class="badge good">R</span>' : '') +
    '</td><td style="text-align:left">' + esc(r.team) + '</td><td style="text-align:left">' + esc(r.pos) + '</td><td>' + fmtVal(r.age, "num1") + '</td>' +
    V.cols.map(c => { const rk = R[c.key] ? R[c.key].m.get(r.id) : null; return '<td class="' + (rk ? qClass(rk, R[c.key].n) : "") + '">' + fmtVal(r[c.key], c.fmt) + '</td>'; }).join("") + '</tr>').join("") ||
    '<tr><td colspan="' + (V.cols.length + 4) + '" class="empty">No players match these filters.</td></tr>';
  $("count").textContent = rows0.length + " players" + (rows0.length > 400 ? " (top 400 shown; narrow the filters to see more)" : "") +
    ". Shading compares the players shown. Select a heading to sort, again to reverse; select a name for career and game log.";
}
async function showPlayer(id) {
  const r = ST.rows.find(x => x.id === id); if (!r) return;
  ST.sel = id;
  if (!CAREER) { const c = await getJSON("players_career.json"); CAREER = []; for (let i = 0; i < c.data.id.length; i++) { const o = {}; c.cols.forEach(k => { o[k] = c.data[k][i]; }); CAREER.push(o); } }
  const car = CAREER.filter(x => x.id === id).sort((a, b) => a.season - b.season);
  const ccols = V === VIEWS.qb ? [["att", "Att", "int"], ["pass_yds", "Yds", "int"], ["pass_td", "TD", "int"], ["int", "INT", "int"], ["anya", "ANY/A", "num2"], ["epa_db", "EPA/db", "num2"], ["cpoe", "CPOE", "pct"], ["rush_yds", "Rush yds", "int"]]
    : V === VIEWS.rb ? [["car", "Car", "int"], ["rush_yds", "Yds", "int"], ["ypc", "YPC", "num2"], ["rush_td", "TD", "int"], ["ryoe_att", "RYOE/att", "num2"], ["rec", "Rec", "int"], ["scrim_yds", "Scrim", "int"], ["tot_td", "Tot TD", "int"]]
    : V === VIEWS.wr ? [["tgt", "Tgt", "int"], ["rec", "Rec", "int"], ["rec_yds", "Yds", "int"], ["ypt", "Y/Tgt", "num2"], ["rec_td", "TD", "int"], ["scrim_yds", "Scrim", "int"]]
    : V === VIEWS.def ? [["tkl", "Tkl", "int"], ["tfl", "TFL", "int"], ["dsacks", "Sacks", "num1"], ["pressures", "Press", "int"], ["dint", "INT", "int"], ["pd", "PD", "int"], ["ff", "FF", "int"]]
    : [["fgm", "FGM", "int"], ["fga", "FGA", "int"], ["fg_pct", "FG %", "pct"], ["punt_net", "Net punt", "num1"]];
  let h = '<div class="pdetail panel"><div class="hdr" style="display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap"><h2>' + esc(r.name) +
    ' <small class="muted">' + esc(r.pos) + ' · ' + esc(r.team) + (r.age ? ' · age ' + r.age : '') + ' · ' + esc(r.draft || "") + '</small></h2><button type="button" class="plink" id="pclose">Close</button></div>';
  h += '<h3>Season by season</h3><div class="scroll"><table class="stbl"><thead><tr><th>Season</th><th>Team</th><th>G</th>' + ccols.map(c => '<th>' + c[1] + '</th>').join("") + '</tr></thead><tbody>' +
    (car.map(x => '<tr' + (x.season === ST.season ? ' class="hl"' : '') + '><td data-v="' + x.season + '">' + x.season + '</td><td style="text-align:left">' + esc(x.team) + '</td><td>' + x.games + '</td>' +
      ccols.map(c => '<td>' + fmtVal(x[c[0]], c[2]) + '</td>').join("") + '</tr>').join("") || '<tr><td colspan="9" class="empty">Only seasons with meaningful volume are listed.</td></tr>') + '</tbody></table></div>';
  let wk = null;
  try { wk = await getJSON("players_weekly/" + ST.season + "_" + r.team + ".json"); } catch (e) {}
  if (wk) {
    const idx = wk.id.map((x, i) => x === id ? i : -1).filter(i => i >= 0);
    const wcols = V === VIEWS.qb ? [["cmp", "Cmp"], ["att", "Att"], ["pass_yds", "Yds"], ["pass_td", "TD"], ["int", "INT"], ["sacks", "Sk"], ["pass_epa", "EPA", "num1"], ["car", "Car"], ["rush_yds", "Rush yds"]]
      : V === VIEWS.rb ? [["car", "Car"], ["rush_yds", "Yds"], ["rush_td", "TD"], ["rush_epa", "EPA", "num1"], ["tgt", "Tgt"], ["rec", "Rec"], ["rec_yds", "Rec yds"]]
      : V === VIEWS.wr ? [["tgt", "Tgt"], ["rec", "Rec"], ["rec_yds", "Yds"], ["rec_td", "TD"], ["rec_epa", "EPA", "num1"]]
      : V === VIEWS.def ? [["tkl_solo", "Solo"], ["tkl_ast", "Ast"], ["tfl", "TFL"], ["dsacks", "Sacks", "num1"], ["qb_hits", "Hits"], ["dint", "INT"], ["pd", "PD"], ["ff", "FF"]]
      : [["fgm", "FGM"], ["fga", "FGA"], ["xpm", "XPM"], ["punts", "Punts"]];
    h += '<h3>' + ST.season + ' game log (' + esc(r.team) + ')</h3><div class="scroll"><table class="stbl"><thead><tr><th>Week</th><th>Opp</th>' + wcols.map(c => '<th>' + c[1] + '</th>').join("") + '</tr></thead><tbody>' +
      idx.map(i => '<tr><td>' + wk.week[i] + '</td><td style="text-align:left">' + esc(wk.opp[i]) + '</td>' + wcols.map(c => '<td>' + fmtVal(wk[c[0]][i], c[2] || "int") + '</td>').join("") + '</tr>').join("") + '</tbody></table></div>';
  }
  $("detail").innerHTML = h + '</div>';
  $("detail").querySelectorAll("table").forEach(sortableTable);
  $("pclose").addEventListener("click", () => { $("detail").innerHTML = ""; ST.sel = null; });
  $("detail").scrollIntoView({behavior: "smooth", block: "start"});
}
async function setSeason(y) {
  ST.season = y;
  $("tbody").innerHTML = '<tr><td class="empty" colspan="9">Loading…</td></tr>';
  ST.rows = await loadSeason(y);
  const teams = [...new Set(ST.rows.map(r => r.team))].filter(Boolean).sort();
  const cur = $("team").value;
  $("team").innerHTML = '<option value="">All teams</option>' + teams.map(t => '<option value="' + t + '">' + esc(nm(t)) + '</option>').join("");
  if (teams.includes(cur)) $("team").value = cur;
  $("detail").innerHTML = "";
  render();
}
boot(async meta => {
  INDEX = await getJSON("players_index.json");
  document.title = V.title + " · NFLFutures";
  $("pageTitle").textContent = V.title; $("pageIntro").textContent = V.intro;
  const sel = (id, label, opts) => '<div class="field"><label for="' + id + '">' + label + '</label><select id="' + id + '">' + opts.map(([v, t]) => '<option value="' + v + '">' + t + '</option>').join("") + '</select></div>';
  const curLabel = y => y === meta.season && meta.through_week < 18 ? y + " so far" : String(y);
  $("app").innerHTML = '<div class="filters">' +
    sel("season", "Season", [...INDEX.seasons].reverse().map(y => [y, curLabel(y)])) +
    sel("team", "Team", [["", "All teams"]]) +
    (V.pos ? sel("pos", "Position", [["", "All"]].concat(V.pos.map(p => [p, p]))) : "") +
    (V.vol ? sel("vol", V.vol[1], V.vol[2].map(v => [v, v])) : "") +
    '<div class="field"><label for="rk">Rookies</label><select id="rk"><option value="">All players</option><option value="1">Rookies only</option></select></div>' +
    '<div class="field"><label for="q">Find a player</label><input type="search" id="q" placeholder="Name or team" autocomplete="off"></div></div>' +
    '<p class="note" id="count"></p><div id="detail"></div>' +
    '<div class="scroll"><table class="stbl"><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>';
  if (V.vol) $("vol").value = String(V.vol[3]);
  $("season").addEventListener("change", e => setSeason(+e.target.value));
  $("team").addEventListener("change", e => { ST.team = e.target.value; render(); });
  if (V.pos) $("pos").addEventListener("change", e => { ST.pos = e.target.value; render(); });
  if (V.vol) $("vol").addEventListener("change", e => { ST.vol = +e.target.value; render(); });
  $("rk").addEventListener("change", e => { ST.rookies = !!e.target.value; render(); });
  $("q").addEventListener("input", e => { ST.q = e.target.value.trim().toLowerCase(); render(); });
  const onSort = e => {
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    const h = e.target.closest("th[data-k]"); if (!h) return;
    e.preventDefault();
    const k = h.dataset.k;
    if (ST.sortKey === k) ST.sortDir = -ST.sortDir;
    else { ST.sortKey = k; const c = V.cols.find(x => x.key === k); ST.sortDir = ["name", "team", "pos"].includes(k) ? 1 : (c && c.dir < 0 ? 1 : -1); }
    render();
  };
  $("thead").addEventListener("click", onSort); $("thead").addEventListener("keydown", onSort);
  $("tbody").addEventListener("click", e => { const b = e.target.closest(".plink"); if (b) showPlayer(b.dataset.id); });
  await setSeason(INDEX.current);
});
