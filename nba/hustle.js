/* NBA Hustle and Synergy rankings (descriptive; nothing here feeds a forecast).
   Reads data/meta.json, team_<season>[p].json and players_<season>[p].json written by pipeline/nba_site.py. */
boot(async () => {
  const app = $("app");
  const sty = document.createElement("style");
  sty.textContent = ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,330px),1fr));gap:16px;align-items:start}.card h3{margin:0 0 2px}.card .note{margin:0 0 6px}" +
    ".card th.l,.card td.l{text-align:left}.card td:first-child,.card th:first-child{width:2em}.controls{display:flex;flex-wrap:wrap;gap:12px 18px;align-items:flex-end;margin-bottom:10px}";
  document.head.appendChild(sty);
  const meta = await getJSON("meta.json");
  const FIRST = 2017;                                   // hustle tracking starts 2016-17 (the provider's 2015-16 file duplicates it)
  const ids = { team: ["team", "name"], players: ["name", "team", "pos"] };
  const memo = {};
  const label = y => (y - 1) + "-" + String(y % 100).padStart(2, "0");
  const hydrate = (d, kind) => d && ({ cols: d.cols, rows: d.rows.map(a => { const o = {}; ids[kind].forEach((k, i) => o[k] = a[i]); d.cols.forEach((c, i) => o[c.k] = a[ids[kind].length + i]); return o; }) });
  const load = (kind, y, po) => { const f = kind + "_" + y + (po ? "p" : ""); return memo[f] || (memo[f] = getJSON(f + ".json").then(d => hydrate(d, kind)).catch(() => null)); };
  const PLAYS = [["isolation", "Isolation"], ["prballhandler", "P&R ball handler"], ["prrollman", "P&R roll man"], ["spotup", "Spot-ups"], ["transition", "Transition"],
                 ["postup", "Post-ups"], ["cut", "Cuts"], ["handoff", "Hand-offs"], ["offscreen", "Off screens"], ["offrebound", "Putbacks"], ["misc", "Miscellaneous"]];
  const DEF_OK = new Set(["isolation", "prballhandler", "prrollman", "spotup", "postup", "handoff", "offscreen"]);
  const st = { y: meta.season, po: false, tab: "team", play: "isolation", minG: 20, minPoss: 100, all: false };
  const seasons = () => ((st.po ? meta.po_seasons : meta.seasons) || []).filter(y => y >= FIRST);
  const seg = (id, opts, cur) => '<div class="seg" id="' + id + '" role="group">' + opts.map(([k, l]) => '<button type="button" data-k="' + esc(k) + '" aria-pressed="' + (k === cur) + '">' + esc(l) + "</button>").join("") + "</div>";
  const fmt = (v, f) => v == null || !isFinite(v) ? "–" : f === "num2" ? v.toFixed(2) : f === "pct" ? (v * 100).toFixed(1) + "%" : v.toFixed(1);
  const card = (title, note, rows, cols, n) => {
    const shown = st.all ? rows : rows.slice(0, n);
    return '<section class="card"><h3>' + esc(title) + "</h3>" + (note ? '<p class="note">' + esc(note) + "</p>" : "") + '<div class="scroll"><table class="stbl"><thead><tr><th>#</th>' +
      cols.map(c => "<th" + (c.num ? ' class="num"' : ' class="l"') + ">" + esc(c.l) + "</th>").join("") + "</tr></thead><tbody>" +
      shown.map((r, i) => "<tr><td>" + (i + 1) + "</td>" + cols.map(c => "<td" + (c.num ? ' class="num"' : ' class="l"') + ">" + c.v(r) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div></section>";
  };
  const rank = (rows, k, asc) => rows.filter(r => r[k] != null && isFinite(r[k])).sort((a, b) => asc ? a[k] - b[k] : b[k] - a[k]);

  async function draw() {
    const ys = seasons();
    if (!ys.includes(st.y)) st.y = ys[0];
    const tabs = [["team", "Team hustle"], ["player", "Player hustle"], ["syno", "Synergy offense"], ["synd", "Synergy defense"]];
    let head = '<div class="controls"><div class="field"><span class="flabel">Season</span><select id="hs">' + ys.map(y => '<option value="' + y + '"' + (y === st.y ? " selected" : "") + ">" + label(y) + "</option>").join("") + "</select></div>" +
      ((meta.po_seasons || []).length ? '<div class="field"><span class="flabel">Season type</span>' + seg("hpo", [["0", "Regular season"], ["1", "Playoffs"]], st.po ? "1" : "0") + "</div>" : "") +
      '<div class="field"><span class="flabel">Rankings</span>' + seg("htab", tabs, st.tab) + "</div>";
    if (st.tab === "syno" || st.tab === "synd") {
      const opts = PLAYS.filter(p => st.tab === "syno" || DEF_OK.has(p[0]));
      if (!opts.some(p => p[0] === st.play)) st.play = opts[0][0];
      head += '<div class="field"><span class="flabel">Play type</span><select id="hplay">' + opts.map(p => '<option value="' + p[0] + '"' + (p[0] === st.play ? " selected" : "") + ">" + esc(p[1]) + "</option>").join("") + "</select></div>" +
        '<div class="field"><span class="flabel">Min. possessions (season)</span><input id="hposs" type="number" min="0" step="25" value="' + st.minPoss + '" style="width:5em"></div>';
    }
    if (st.tab === "player") head += '<div class="field"><span class="flabel">Min. games</span><input id="hg" type="number" min="0" step="5" value="' + st.minG + '" style="width:4em"></div>';
    head += '<div class="field"><span class="flabel">Show</span>' + seg("hall", [["0", "Top 10"], ["1", "All"]], st.all ? "1" : "0") + "</div></div>";
    let body = "";
    if (st.tab === "team") {
      const d = await load("team", st.y, st.po);
      const cs = d ? d.cols.filter(c => c.k.startsWith("h_")) : [];
      body = !cs.length ? '<p class="note">No hustle data for this season yet.</p>' : '<div class="cards">' + cs.map(c =>
        card(c.l, "Per game, whole team", rank(d.rows, c.k, false), [{ l: "Team", v: r => esc(r.name || r.team) }, { l: "Per game", num: 1, v: r => fmt(r[c.k], c.f) }], 10)).join("") + "</div>";
    } else if (st.tab === "player") {
      const d = await load("players", st.y, st.po);
      const cs = d ? d.cols.filter(c => c.k.startsWith("h_")) : [];
      body = !cs.length ? '<p class="note">No hustle data for this season yet.</p>' : '<div class="cards">' + cs.map(c =>
        card(c.l, "Per game, players with at least " + st.minG + " games", rank(d.rows.filter(r => (r.gp || 0) >= st.minG), c.k, false),
          [{ l: "Player", v: r => esc(r.name) }, { l: "Team", v: r => esc(r.team) }, { l: "GP", num: 1, v: r => fmt(r.gp, "num0").replace(".0", "") }, { l: "Per game", num: 1, v: r => fmt(r[c.k], c.f) }], 10)).join("") + "</div>";
    } else {
      const d = await load("players", st.y, st.po);
      const side = st.tab === "syno" ? "o" : "d", p = "syn_" + side + "_" + st.play + "_";
      if (!d || !d.cols.some(c => c.k === p + "ppp")) body = '<p class="note">No Synergy data for this season yet.</p>';
      else {
        const rows = d.rows.filter(r => r[p + "poss"] != null && (r.gp || 0) * r[p + "poss"] >= st.minPoss);
        const asc = side === "d";
        body = card((side === "o" ? "Offense: " : "Defense: ") + PLAYS.find(x => x[0] === st.play)[1], (asc ? "Points allowed per possession, lowest is best. " : "Points per possession, highest is best. ") +
          "Players with at least " + st.minPoss + " possessions of this play type in the season; the provider leaves out players below its own minimum.", rank(rows, p + "ppp", asc),
          [{ l: "Player", v: r => esc(r.name) }, { l: "Team", v: r => esc(r.team) }, { l: "Poss/G", num: 1, v: r => fmt(r[p + "poss"], "num1") }, { l: "Freq", num: 1, v: r => fmt(r[p + "freq"], "pct") },
           { l: "PPP", num: 1, v: r => fmt(r[p + "ppp"], "num2") }], 25);
      }
    }
    app.innerHTML = head + '<p class="note">Descriptive rankings from NBA Stats hustle and Synergy tracking via SportsDataverse. They do not feed any forecast: tested on 2003-2026, rebounds, free throws and hustle tracking add no information about future results beyond a team\'s point margin.</p>' + body;
    $("hs").onchange = e => { st.y = +e.target.value; draw(); };
    const bind = (id, fn) => { const g = $(id); if (g) g.querySelectorAll("button").forEach(b => b.onclick = () => { fn(b.dataset.k); draw(); }); };
    bind("hpo", k => { st.po = k === "1"; st.minG = st.po ? 4 : 20; st.minPoss = st.po ? 25 : 100; });
    bind("htab", k => { st.tab = k; });
    bind("hall", k => { st.all = k === "1"; });
    if ($("hplay")) $("hplay").onchange = e => { st.play = e.target.value; draw(); };
    if ($("hposs")) $("hposs").onchange = e => { st.minPoss = Math.max(0, +e.target.value || 0); draw(); };
    if ($("hg")) $("hg").onchange = e => { st.minG = Math.max(0, +e.target.value || 0); draw(); };
  }
  draw();
});
