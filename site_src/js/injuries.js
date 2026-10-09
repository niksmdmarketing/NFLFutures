/* Injury report: expected starting quarterbacks (what the model uses) and the full Out/Doubtful/Questionable list. */
boot(async () => {
  const P = await getJSON("page_injuries.json");
  const statusTag = s => s ? '<span class="status s-' + esc(s) + '">' + esc(s) + '</span>' : '<span class="status s-Active">Active</span>';
  const qbs = [...P.qbs].sort((a, b) => a.adj - b.adj || a.team.localeCompare(b.team));
  const qbRows = qbs.map(q => '<tr><td><b>' + esc(q.team) + '</b> <small>' + esc(nm(q.team)) + '</small></td><td style="text-align:left">' + esc(q.starter || "–") + '</td><td style="text-align:left">' + statusTag(q.status) +
    '</td><td style="text-align:left">' + esc(q.season_qb || "–") + '</td><td class="' + (q.adj < -0.05 ? "adj-neg" : q.adj > 0.05 ? "adj-pos" : "") + '">' + (q.adj > 0 ? "+" : "") + q.adj.toFixed(1) +
    '</td><td class="txt">' + esc(q.note || "") + '</td></tr>').join("");
  const teams = [...new Set(P.rows.map(r => r.team))].sort((a, b) => nm(a).localeCompare(nm(b)));
  $("app").innerHTML =
    '<section><div class="table-head"><h2>Expected starting quarterbacks</h2></div>' +
    '<p class="note" style="margin:6px 0 12px">The model starts each team\'s top quarterback on the latest depth chart, switching to the backup if he is listed Out or Doubtful. The rating shift (points per game) moves that team\'s strength in every simulated game.</p>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th scope="col">Team</th><th scope="col" style="text-align:left">Expected starter</th><th scope="col" style="text-align:left">Report</th><th scope="col" style="text-align:left">Season\'s main QB</th><th scope="col">Rating shift</th><th scope="col" style="text-align:left">Note</th></tr></thead><tbody>' + qbRows + '</tbody></table></div></section>' +
    '<section><div class="table-head"><h2>' + (P.week ? 'Week ' + P.week + ' practice report' : 'Practice report') + '</h2></div>' +
    '<div class="filters" style="margin:10px 0 12px"><div class="field"><label for="iq">Find a player</label><input type="search" id="iq" autocomplete="off" placeholder="Name or position"></div>' +
    '<div class="field"><label for="it">Team</label><select id="it"><option value="">All teams</option>' + teams.map(t => '<option value="' + t + '">' + esc(nm(t)) + '</option>').join("") + '</select></div>' +
    '<div class="field"><label for="is">Status</label><select id="is"><option value="">Out, Doubtful, Questionable</option><option>Out</option><option>Doubtful</option><option>Questionable</option></select></div></div>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th scope="col">Team</th><th scope="col" style="text-align:left">Player</th><th scope="col" style="text-align:left">Pos</th><th scope="col" style="text-align:left">Status</th><th scope="col" style="text-align:left">Injury</th><th scope="col" style="text-align:left">Practice</th></tr></thead><tbody id="ibody"></tbody></table></div>' +
    '<p class="note" id="icount" style="margin-top:8px"></p></section>';
  const draw = () => {
    const q = $("iq").value.trim().toLowerCase(), t = $("it").value, s = $("is").value;
    const rows = P.rows.filter(r => (!t || r.team === t) && (!s || r.status === s) && (!q || (r.player + " " + r.pos).toLowerCase().includes(q)));
    $("ibody").innerHTML = rows.map(r => '<tr><td><b>' + esc(r.team) + '</b></td><td style="text-align:left">' + esc(r.player) + '</td><td style="text-align:left">' + esc(r.pos) + '</td><td style="text-align:left">' + statusTag(r.status) +
      '</td><td style="text-align:left">' + esc(r.injury) + '</td><td class="txt">' + esc(r.practice) + '</td></tr>').join("") ||
      '<tr><td colspan="6" class="empty">' + (P.rows.length ? "No players match." : "No injury report has been published yet.") + '</td></tr>';
    $("icount").textContent = rows.length + " of " + P.rows.length + " players listed.";
  };
  ["iq", "it", "is"].forEach(id => $(id).addEventListener(id === "iq" ? "input" : "change", draw));
  draw();
});
