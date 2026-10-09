/* Advanced box scores: one card per game, stats as rows, better side highlighted. */
const LINES = [
  ["plays", "Plays", "int", 0], ["yards", "Yards", "int", 1], ["epa", "EPA per play", "num2", 1], ["succ", "Success rate", "pct", 1],
  ["early_succ", "Early-down success", "pct", 1], ["pass_epa", "EPA per dropback", "num2", 1], ["rush_epa", "EPA per designed run", "num2", 1],
  ["expl", "Explosive plays", "int", 1], ["third", "Third downs", "frac", 1], ["rz", "Red zone TDs", "frac", 1],
  ["to", "Turnovers", "int", -1], ["sacks", "Sacks taken", "int", -1],
];
function fracVal(s) { const [a, b] = String(s).split("/").map(Number); return b ? a / b : null; }
function card(g) {
  const [a, h] = g.teams;
  const win = a.pts > h.pts ? 0 : h.pts > a.pts ? 1 : -1;
  let rows = "";
  LINES.forEach(([k, label, fmt, better]) => {
    const va = a[k], vh = h[k];
    const na = fmt === "frac" ? fracVal(va) : va, nh = fmt === "frac" ? fracVal(vh) : vh;
    let ca = "", ch = "";
    if (better && na != null && nh != null && na !== nh) { ((na > nh) === (better > 0)) ? ca = "better" : ch = "better"; }
    const show = v => fmt === "frac" ? esc(v) : fmtVal(v, fmt);
    rows += '<tr><td>' + label + '</td><td class="' + ca + '">' + show(va) + '</td><td class="' + ch + '">' + show(vh) + '</td></tr>';
  });
  return '<article class="panel game"><div class="hdr"><h3>' + fmtDate(g.date) + '</h3><span class="stamp">Week ' + g.week + '</span></div>' +
    '<table><thead><tr><th scope="col"></th><th scope="col">' + esc(a.team) + '</th><th scope="col">' + esc(h.team) + '</th></tr></thead><tbody>' +
    '<tr><td class="matchup">' + esc(nm(a.team)) + ' at ' + esc(nm(h.team)) + '</td><td class="pts' + (win === 0 ? " win" : "") + '">' + a.pts + '</td><td class="pts' + (win === 1 ? " win" : "") + '">' + h.pts + '</td></tr>' +
    rows + '</tbody></table></article>';
}
boot(async () => {
  const P = await getJSON("page_boxscores.json");
  const weeks = [...new Set(P.games.map(g => g.week))].sort((a, b) => a - b);
  const app = $("app");
  if (!weeks.length) { app.innerHTML = '<p class="note">No games have been played yet this season.</p>'; return; }
  const teams = [...new Set(P.games.flatMap(g => g.teams.map(t => t.team)))].sort((a, b) => nm(a).localeCompare(nm(b)));
  app.innerHTML = '<div class="filters"><div class="field"><label for="wk">Week</label><select id="wk">' +
    weeks.map(w => '<option value="' + w + '">Week ' + w + '</option>').join("") + '</select></div>' +
    '<div class="field"><label for="tm">Team</label><select id="tm"><option value="">All teams</option>' +
    teams.map(t => '<option value="' + t + '">' + esc(nm(t)) + '</option>').join("") + '</select></div></div>' +
    '<p class="note">EPA is expected points added per play. Early downs are first and second down. Choosing a team shows its whole season.</p>' +
    '<div class="games" id="games"></div>';
  $("wk").value = String(weeks[weeks.length - 1]);
  const draw = () => {
    const t = $("tm").value, w = +$("wk").value;
    $("wk").disabled = !!t;
    const list = P.games.filter(g => t ? g.teams.some(x => x.team === t) : g.week === w);
    $("games").innerHTML = (t ? [...list].reverse() : list).map(card).join("");
  };
  $("wk").addEventListener("change", draw);
  $("tm").addEventListener("change", draw);
  draw();
});
