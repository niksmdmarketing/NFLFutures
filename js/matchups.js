/* Matchup edges: offense rank vs the defense rank it faces, five categories, with weekly rank trends. */
const CATS = [["overall","Overall"],["passing","Passing"],["rushing","Rushing"],["pressure","Pressure"],["explosives","Explosives"]];
let D = null;
const st = {week: 1, cat: "overall", sort: "kick", open: new Set()};
function kick(date, time) { return fmtDate(date) + (time ? " · " + time + " ET" : ""); }
function edgeClass(diff) {
  if (diff >= 15) return ["e-big-off", "Big OFF"];
  if (diff >= 8) return ["e-off", "OFF edge"];
  if (diff <= -15) return ["e-big-def", "Big DEF"];
  if (diff <= -8) return ["e-def", "DEF edge"];
  return ["e-even", "Even"];
}
function rowsFor(week) {
  const games = D.schedule.filter(g => g.week === week).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  const rows = [];
  games.forEach(g => {
    rows.push({off: g.away, def: g.home, g, first: true, key: g.away + g.home + "a"});
    rows.push({off: g.home, def: g.away, g, first: false, key: g.away + g.home + "h"});
  });
  // Ranks as they stood going into that week (current ranks for weeks not yet played).
  const src = D.history[String(Math.min(week - 1, D.data_through_week))] || D.current;
  rows.forEach(r => { r.cells = {}; CATS.forEach(([c]) => {
    const o = src[r.off][c].off_rank, d = src[r.def][c].def_rank;
    r.cells[c] = {o, d, diff: d - o};
  }); });
  return rows;
}
function renderEdges(rows) {
  const c = st.cat, label = CATS.find(x => x[0] === c)[1].toLowerCase();
  $("offTitle").textContent = "Biggest offense edges · " + label;
  $("defTitle").textContent = "Biggest defense edges · " + label;
  const byOff = [...rows].sort((a, b) => b.cells[c].diff - a.cells[c].diff).slice(0, 5);
  const byDef = [...rows].sort((a, b) => a.cells[c].diff - b.cells[c].diff).slice(0, 5);
  const li = r => {
    const x = r.cells[c];
    return '<li><span><b>' + r.off + '</b> offense vs <b>' + r.def + '</b> defense <span class="muted">(' + x.o + ' v ' + x.d + ')</span></span><span class="gap-pill num">' + Math.abs(x.diff) + '</span></li>';
  };
  $("offList").innerHTML = byOff.map(li).join("") || '<li class="muted">No games this week.</li>';
  $("defList").innerHTML = byDef.map(li).join("") || '<li class="muted">No games this week.</li>';
}
function spark(r, c) {
  const keys = Object.keys(D.history).map(Number).sort((a, b) => a - b);
  const W = 200, H = 96, L = 24, R = 22, T = 8, B = 20;
  const x = i => L + (keys.length === 1 ? 0 : i * (W - L - R) / (keys.length - 1));
  const y = rank => T + (rank - 1) * (H - T - B) / 31;
  const oS = keys.map(k => D.history[k][r.off][c].off_rank);
  const dS = keys.map(k => D.history[k][r.def][c].def_rank);
  const path = s => s.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
  let g = "";
  [1, 16, 32].forEach(v => { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--line)" stroke-width="1"/><text x="' + (L - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end" font-size="8" fill="var(--muted)">' + v + '</text>'; });
  const step = keys.length > 10 ? 2 : 1;
  keys.forEach((k, i) => { if (i % step === 0 || i === keys.length - 1) g += '<text x="' + x(i) + '" y="' + (H - 6) + '" text-anchor="middle" font-size="8" fill="var(--muted)">' + (k === 0 ? "Pre" : "W" + k) + '</text>'; });
  const end = (s, col) => '<circle cx="' + x(s.length - 1) + '" cy="' + y(s[s.length - 1]) + '" r="3" fill="' + col + '"/><text x="' + (x(s.length - 1) + 6) + '" y="' + (y(s[s.length - 1]) + 3) + '" font-size="9" font-weight="600" fill="' + col + '">' + s[s.length - 1] + '</text>';
  g += '<path d="' + path(oS) + '" fill="none" stroke="var(--off)" stroke-width="2"/><path d="' + path(dS) + '" fill="none" stroke="var(--def)" stroke-width="2" stroke-dasharray="4 3"/>' + end(oS, "var(--off)") + end(dS, "var(--def)");
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Rank trend, ' + c + ': ' + r.off + ' offense ' + oS.join(", ") + '; ' + r.def + ' defense ' + dS.join(", ") + '">' + g + '</svg>';
}
function renderTable(rows) {
  $("thead").innerHTML = '<tr><th class="col-match" scope="col">Matchup</th>' + CATS.map(([, n]) => '<th scope="col">' + n + '<small>off · def rank</small></th>').join("") + '</tr>';
  if (!rows.length) { $("tbody").innerHTML = '<tr><td colspan="6" class="empty">No games scheduled for this week.</td></tr>'; return; }
  let html = "";
  rows.forEach(r => {
    const id = r.key, open = st.open.has(id);
    html += '<tr class="' + (r.first && st.sort === "kick" ? "game-start" : "") + '"><td class="col-match"><button class="match-btn" type="button" data-k="' + id + '" aria-expanded="' + open + '" aria-controls="d-' + id + '"><span class="t"><i class="chev"></i>' + r.off + ' offense vs ' + r.def + ' defense</span><span class="k">' + nm(r.off) + (r.g.home === r.off ? " (home)" : " (away)") + ' · ' + kick(r.g.date, r.g.time) + '</span></button></td>';
    CATS.forEach(([c]) => {
      const x = r.cells[c], [cls, lab] = edgeClass(x.diff);
      html += '<td class="cell ' + cls + ' num"><div class="ranks">' + x.o + '<i>v</i>' + x.d + '</div><div class="lab">' + lab + '</div></td>';
    });
    html += '</tr>';
    if (open) {
      html += '<tr class="detail" id="d-' + id + '"><td colspan="6"><div class="detail-grid">' + CATS.map(([c, n]) => '<div class="trend"><h4>' + n + '</h4>' + spark(r, c) + '<div class="scores"><span class="l-off">' + r.off + ' off score ' + D.current[r.off][c].off_score.toFixed(2) + '</span><span class="l-def">' + r.def + ' def score ' + D.current[r.def][c].def_score.toFixed(2) + '</span></div></div>').join("") + '</div><div class="key"><span class="l-off"><b>Solid line:</b> ' + nm(r.off) + ' offense rank</span><span class="l-def"><b>Dashed line:</b> ' + nm(r.def) + ' defense rank</span><span>Rank 1 is best. Scores are team strength in standard deviations above or below average.</span></div></td></tr>';
    }
  });
  $("tbody").innerHTML = html;
}
function render() {
  let rows = rowsFor(st.week);
  renderEdges(rows);
  if (st.sort === "off") rows = [...rows].sort((a, b) => b.cells[st.cat].diff - a.cells[st.cat].diff);
  if (st.sort === "def") rows = [...rows].sort((a, b) => a.cells[st.cat].diff - b.cells[st.cat].diff);
  renderTable(rows);
}
boot(async () => {
  D = await getJSON("matchups.json");
  const through = D.complete_week != null ? D.complete_week : D.data_through_week, maxWeek = Math.max(18, ...D.schedule.map(g => g.week));
  st.week = D.next_week || Math.min(maxWeek, through + 1);
  $("week").innerHTML = Array.from({length: maxWeek}, (_, i) => i + 1).map(w => '<option value="' + w + '"' + (w === st.week ? " selected" : "") + '>Week ' + w + (w <= through ? " (played)" : "") + '</option>').join("");
  $("cat").innerHTML = CATS.map(([c, n]) => '<option value="' + c + '">' + n + '</option>').join("");
  $("week").addEventListener("change", e => { st.week = +e.target.value; st.open.clear(); render(); });
  $("cat").addEventListener("change", e => { st.cat = e.target.value; render(); });
  $("sort").addEventListener("change", e => { st.sort = e.target.value; render(); });
  $("tbody").addEventListener("click", e => {
    const b = e.target.closest(".match-btn"); if (!b) return;
    const k = b.dataset.k; st.open.has(k) ? st.open.delete(k) : st.open.add(k);
    render();
    const nb = document.querySelector('.match-btn[data-k="' + k + '"]'); if (nb) nb.focus();
  });
  render();
});
