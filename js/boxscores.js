/* Advanced box scores since 2018.
   Games view: one card per game, better side highlighted, plus "best/worst since" notes comparing each team's
   performance (and what its defense allowed) with all its earlier games since 2018.
   Game log view: every game a team has played since 2018, ranked on one stat, offense or allowed. */
const STATS = [
  {k: "pts", label: "Points", fmt: "int", dir: 1},
  {k: "yards", label: "Total yards", fmt: "int", dir: 1},
  {k: "ypp", label: "Yards per play", fmt: "num2", dir: 1},
  {k: "first_downs", label: "First downs", fmt: "int", dir: 1},
  {k: "epa", label: "EPA per play", fmt: "num2", dir: 1},
  {k: "succ", label: "Success rate", fmt: "pct", dir: 1},
  {k: "early_succ", label: "Early-down success", fmt: "pct", dir: 1},
  {k: "pass_epa", label: "EPA per dropback", fmt: "num2", dir: 1},
  {k: "rush_epa", label: "EPA per designed run", fmt: "num2", dir: 1},
  {k: "pass_yds", label: "Net passing yards", fmt: "int", dir: 1},
  {k: "rush_yds", label: "Rushing yards (designed runs)", fmt: "int", dir: 1},
  {k: "expl", label: "Explosive plays", fmt: "int", dir: 1},
  {k: "third", label: "Third downs", fmt: "frac", dir: 1, num: "third_c", den: "third_a"},
  {k: "rz", label: "Red zone TDs", fmt: "frac", dir: 1, num: "rz_td", den: "rz_n"},
  {k: "to", label: "Turnovers", fmt: "int", dir: -1},
  {k: "sacks", label: "Sacks taken", fmt: "int", dir: -1},
  {k: "plays", label: "Plays", fmt: "int", dir: 0},
];
const NOTE_STATS = ["pts", "yards", "ypp", "first_downs", "epa", "succ", "pass_epa", "rush_epa", "pass_yds", "rush_yds"];
const MIN_SPAN = 17;  // only note streaks longer than about a season of games
let ROWS = [], BY_TEAM = {}, BY_GAME = {}, SEASONS = [], CUR = 0;

function val(r, s) {
  if (s.fmt === "frac") return r[s.den] ? r[s.num] / r[s.den] : null;
  if (s.k === "ypp") return r.plays ? r.yards / r.plays : null;
  return r[s.k];
}
function show(r, s) {
  if (s.fmt === "frac") return r[s.num] + "/" + r[s.den];
  const v = val(r, s);
  return s.fmt === "pct" ? fmtVal(v, "pct") : fmtVal(v, s.fmt);
}
const S_ = k => STATS.find(s => s.k === k);
const wk = r => "Wk " + r.week + " " + r.season;

/* best/worst since: walk back through earlier games of the same team (offense rows, or rows where it was the opponent) */
function sinceNote(row, s, side) {
  const list = side === "off" ? BY_TEAM[row.team] : BY_TEAM["@" + row.opp];
  const me = row;
  const v = val(me, s);
  if (v == null || !s.dir) return null;
  const i = list.indexOf(me);
  if (i < MIN_SPAN) return null;
  // for the offense, "best" = high when dir 1; for a defense (allowed), "worst" = high when dir 1
  let j = i - 1, beats = 0;
  while (j >= 0) {
    const x = val(list[j], s);
    if (x != null && x >= v) break;
    j--; beats++;
  }
  let k = i - 1, below = 0;
  while (k >= 0) {
    const x = val(list[k], s);
    if (x != null && x <= v) break;
    k--; below++;
  }
  const high = beats >= MIN_SPAN ? {n: beats, ref: j >= 0 ? list[j] : null, hi: true} : null;
  const low = below >= MIN_SPAN ? {n: below, ref: k >= 0 ? list[k] : null, hi: false} : null;
  const pickd = high || low;
  if (!pickd) return null;
  const good = (pickd.hi ? 1 : -1) * s.dir * (side === "off" ? 1 : -1) > 0;
  const who = side === "off" ? row.team : row.opp;
  const verb = side === "off" ? (pickd.hi ? "Highest" : "Lowest") : (pickd.hi ? "Most allowed" : "Fewest allowed");
  const since = pickd.ref ? "since " + wk(pickd.ref) + " vs " + (side === "off" ? pickd.ref.opp : pickd.ref.team)
                          : "in any game since " + list[0].season + " (" + (i + 1) + " games)";
  return {n: pickd.n + (pickd.ref ? 0 : 1000), good, text: "<b>" + esc(who) + "</b>: " + verb + " " + esc(s.label.replace(" (designed runs)", "").replace(/^[A-Z][a-z]/, m => m.toLowerCase())) + " (" + show(row, s) + ") " + since};
}
function notesFor(game) {
  const out = [];
  game.forEach(r => NOTE_STATS.forEach(k => {
    const s = S_(k);
    const a = sinceNote(r, s, "off"); if (a) out.push(a);
    const b = sinceNote(r, s, "def"); if (b) out.push(b);
  }));
  out.sort((x, y) => y.n - x.n);
  return out.slice(0, 5);
}
function card(game) {
  const [a, h] = game;
  const win = a.pts > h.pts ? 0 : h.pts > a.pts ? 1 : -1;
  let rows = "";
  STATS.filter(s => s.k !== "pts").forEach(s => {
    const va = val(a, s), vh = val(h, s);
    let ca = "", ch = "";
    if (s.dir && va != null && vh != null && va !== vh) { ((va > vh) === (s.dir > 0)) ? ca = "better" : ch = "better"; }
    rows += '<tr><td>' + s.label + '</td><td class="' + ca + '">' + show(a, s) + '</td><td class="' + ch + '">' + show(h, s) + '</td></tr>';
  });
  const notes = notesFor(game);
  return '<article class="panel game"><div class="hdr"><h3>' + fmtDate(a.date) + '</h3><span class="stamp">Week ' + a.week + ' · ' + a.season + '</span></div>' +
    '<table><thead><tr><th scope="col"></th><th scope="col">' + esc(a.team) + '</th><th scope="col">' + esc(h.team) + '</th></tr></thead><tbody>' +
    '<tr><td class="matchup">' + esc(nm(a.team)) + ' at ' + esc(nm(h.team)) + '</td><td class="pts' + (win === 0 ? " win" : "") + '">' + a.pts + '</td><td class="pts' + (win === 1 ? " win" : "") + '">' + h.pts + '</td></tr>' +
    rows + '</tbody></table>' +
    (notes.length ? '<ul class="notes">' + notes.map(n => '<li class="' + (n.good ? "up" : "down") + '">' + n.text + '</li>').join("") + '</ul>' : '') +
    '</article>';
}

function drawGames() {
  const y = +$("season").value, t = $("tm").value, w = +$("wk").value;
  $("wk").disabled = !!t;
  const keys = Object.keys(BY_GAME).filter(k => {
    const g = BY_GAME[k]; return g[0].season === y && (t ? g.some(r => r.team === t) : g[0].week === w);
  });
  const games = keys.map(k => BY_GAME[k]).sort((a, b) => (a[0].date + a[0].team).localeCompare(b[0].date + b[0].team));
  $("games").innerHTML = (t ? games.reverse() : games).map(card).join("") || '<p class="note">No games.</p>';
}
function fillWeeks() {
  const y = +$("season").value;
  const weeks = [...new Set(ROWS.filter(r => r.season === y).map(r => r.week))].sort((a, b) => a - b);
  $("wk").innerHTML = weeks.map(w => '<option value="' + w + '">Week ' + w + '</option>').join("");
  $("wk").value = String(weeks[weeks.length - 1]);
}

function drawLog() {
  const t = $("lteam").value, s = S_($("lstat").value), side = $("lside").value;
  let y0 = +$("lfrom").value, y1 = +$("lto").value; if (y0 > y1) [y0, y1] = [y1, y0];
  const list = (side === "off" ? BY_TEAM[t] : BY_TEAM["@" + t]).filter(r => val(r, s) != null && r.season >= y0 && r.season <= y1);
  const sign = (s.dir || 1) * (side === "off" ? 1 : -1);
  const ranked = [...list].sort((a, b) => sign * (val(b, s) - val(a, s)) || (b.date.localeCompare(a.date)));
  const latest = list[list.length - 1];
  const rk = ranked.indexOf(latest) + 1;
  const best = side === "off" ? (s.dir < 0 ? "fewest" : "best") : (s.dir < 0 ? "most forced" : "fewest allowed");
  if (!list.length) { $("lsum").textContent = "No games in this range."; $("lbody").innerHTML = ""; return; }
  $("lsum").innerHTML = latest ? '<b>' + esc(nm(t)) + '</b>, ' + wk(latest) + ' vs ' + esc(side === "off" ? latest.opp : latest.team) + ': ' +
    esc(s.label.toLowerCase()) + (side === "off" ? " " : " allowed ") + show(latest, s) +  ' ranks <b>' + rk + ' of ' + list.length + '</b> games ' + (y0 === y1 ? "in " + y0 : "from " + y0 + " to " + y1) +
    ' (1 = ' + best + ').' : "";
  $("lbody").innerHTML = ranked.map((r, i) => {
    const opp = side === "off" ? r.opp : r.team;
    const me = side === "off" ? r.pts : r.opp_pts, them = side === "off" ? r.opp_pts : r.pts;
    const res = me > them ? "W" : me < them ? "L" : "T";
    const home = side === "off" ? r.home : 1 - r.home;
    return '<tr' + (r === latest ? ' class="hl"' : '') + '><td data-v="' + (i + 1) + '">' + (i + 1) + '</td><td style="text-align:left" data-v="' + r.date.replace(/-/g, "") + '">' + wk(r) + '</td><td style="text-align:left">' + (home ? "vs " : "@ ") + esc(opp) +
      '</td><td style="text-align:left" data-v="' + (me - them) + '">' + res + ' ' + me + '–' + them + '</td><td data-v="' + val(r, s) + '">' + show(r, s) + '</td></tr>';
  }).join("");
}

function setView(v) {
  document.querySelectorAll("[data-view]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
  $("gamesView").hidden = v !== "games"; $("logView").hidden = v !== "log";
  if (v === "log") drawLog(); else drawGames();
}

boot(async meta => {
  const P = await getJSON("page_boxscores.json");
  if (!P.data) { $("app").innerHTML = '<p class="note">No games yet.</p>'; return; }
  const n = P.data.season.length;
  for (let i = 0; i < n; i++) { const r = {}; P.cols.forEach(c => { r[c] = P.data[c][i]; }); ROWS.push(r); }
  ROWS.sort((a, b) => a.date.localeCompare(b.date) || a.team.localeCompare(b.team));
  ROWS.forEach(r => {
    (BY_TEAM[r.team] = BY_TEAM[r.team] || []).push(r);
    (BY_TEAM["@" + r.opp] = BY_TEAM["@" + r.opp] || []).push(r);
    const key = r.season + "-" + r.date + "-" + [r.team, r.opp].sort().join("-");
    (BY_GAME[key] = BY_GAME[key] || []).push(r);
  });
  Object.values(BY_GAME).forEach(g => g.sort((a, b) => a.home - b.home));  // away first
  SEASONS = P.seasons; CUR = P.season;
  const teams = Object.keys(NAMES).sort((a, b) => nm(a).localeCompare(nm(b)));
  const topt = teams.map(t => '<option value="' + t + '">' + esc(nm(t)) + '</option>').join("");
  $("app").innerHTML =
    '<div class="filters"><div class="field"><span class="flabel">View</span><div class="seg" role="group" aria-label="View"><button type="button" data-view="games">Games</button><button type="button" data-view="log">Team game log</button></div></div></div>' +
    '<div id="gamesView"><div class="filters" style="margin:12px 0">' +
    '<div class="field"><label for="season">Season</label><select id="season">' + [...SEASONS].reverse().map(y => '<option value="' + y + '">' + y + '</option>').join("") + '</select></div>' +
    '<div class="field"><label for="wk">Week</label><select id="wk"></select></div>' +
    '<div class="field"><label for="tm">Team</label><select id="tm"><option value="">All teams</option>' + topt + '</select></div></div>' +
    '<p class="note">EPA is expected points added. Notes under each game flag performances that were a team\'s best or worst in more than a season of games, or the most or fewest its defense had allowed, going back to ' + SEASONS[0] + '.</p>' +
    '<div class="games" id="games"></div></div>' +
    '<div id="logView" hidden><div class="filters" style="margin:12px 0">' +
    '<div class="field"><label for="lteam">Team</label><select id="lteam">' + topt + '</select></div>' +
    '<div class="field"><label for="lstat">Stat</label><select id="lstat">' + STATS.map(s => '<option value="' + s.k + '">' + s.label + '</option>').join("") + '</select></div>' +
    '<div class="field"><label for="lside">Side</label><select id="lside"><option value="off">Offense</option><option value="def">Defense (allowed)</option></select></div>' +
    '<div class="field"><label for="lfrom">From season</label><select id="lfrom">' + SEASONS.map(y => '<option value="' + y + '">' + y + '</option>').join("") + '</select></div>' +
    '<div class="field"><label for="lto">To season</label><select id="lto">' + [...SEASONS].reverse().map(y => '<option value="' + y + '">' + y + '</option>').join("") + '</select></div></div>' +
    '<p class="note" id="lsum"></p><p class="note">Select a column heading to sort it; select it again to reverse the order.</p>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th scope="col">Rank</th><th scope="col" style="text-align:left">Game</th><th scope="col" style="text-align:left">Opponent</th><th scope="col" style="text-align:left">Result</th><th scope="col">Value</th></tr></thead><tbody id="lbody"></tbody></table></div></div>';
  $("season").value = String(CUR);
  fillWeeks();
  $("lstat").value = "rush_epa";
  $("lteam").value = teams[0];
  $("season").addEventListener("change", () => { fillWeeks(); drawGames(); });
  $("wk").addEventListener("change", drawGames);
  $("tm").addEventListener("change", drawGames);
  ["lteam", "lstat", "lside", "lfrom", "lto"].forEach(id => $(id).addEventListener("change", drawLog));
  sortableTable($("lbody").closest("table"));
  document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => setView(b.dataset.view)));
  setView("games");
});
