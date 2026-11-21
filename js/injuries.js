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
  document.querySelectorAll("#app table").forEach(sortableTable);
  monitor();
});

/* Collection-only monitor of the official NFL report (data/injury_monitor.json). Shown for transparency; it feeds no rating. */
async function monitor() {
  let M;
  try { M = await getJSON("injury_monitor.json"); } catch (e) { M = null; }
  const sec = document.createElement("section");
  sec.className = "inj-mon";
  const when = s => s ? new Date(s).toLocaleString(undefined, {weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"}) : "–";
  if (!M) {
    sec.innerHTML = '<div class="table-head"><h2>Official report monitor <small>collection only</small></h2></div><p class="note">The monitor has not produced a status file yet. It runs with every site refresh.</p>';
    $("app").appendChild(sec);
    return;
  }
  const label = {ok: "Up to date", degraded: "Last check failed", stale: "Out of date", unavailable: "No report collected yet"}[M.collection_status] || M.collection_status;
  const cov = M.expected_teams ? M.covered_teams.length + " of " + M.expected_teams.length + " teams playing this week" : M.covered_teams.length + " teams";
  const counts = Object.entries(M.status_counts || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => '<span class="mon-chip">' + esc(k) + " <b>" + v + "</b></span>").join("");
  const changes = (M.recent_changes || []).slice(0, 15).map(c => {
    const who = (c.after || c.before || {}).player || c.player_id;
    const what = c.kind === "updated" ? esc((c.before.practice_status || "–") + " / " + (c.before.game_status || "no status")) + " → " + esc((c.after.practice_status || "–") + " / " + (c.after.game_status || "no status"))
      : c.kind === "appeared" ? "added to the report" : c.kind === "team_table_missing" ? "team table not on the page" : "no longer listed (not proof of recovery)";
    return "<li><b>" + esc(c.team) + "</b> " + esc(who) + ' <span class="muted">' + what + " · seen " + when(c.observed_at) + "</span></li>";
  }).join("");
  sec.innerHTML = '<div class="table-head"><h2>Official report monitor <small>collection only</small></h2></div>' +
    '<p class="note">A record of what the NFL\'s public injury report said each time this site checked it (every three hours), kept for future research. ' +
    "<b>It does not change any rating, projection or award probability.</b> Check times are when this site looked, not when the NFL published. " +
    "A blank game status is not an Active designation, and a player who drops off the report has not been shown to have recovered. No return dates are collected.</p>" +
    '<div class="mon-grid">' +
    '<div><span>Status</span><b class="mon-' + esc(M.collection_status) + '">' + esc(label) + "</b></div>" +
    "<div><span>Last successful check</span><b>" + when(M.last_success_at) + "</b></div>" +
    "<div><span>Last attempt</span><b>" + when(M.last_attempt_at) + (M.last_attempt_ok ? "" : " (failed)") + "</b></div>" +
    "<div><span>Report</span><b>" + (M.report_season ? M.report_season + " season, week " + M.report_week : "–") + "</b></div>" +
    "<div><span>Coverage</span><b>" + cov + "</b></div>" +
    "<div><span>History</span><b>" + M.distinct_reports + " distinct reports, " + M.checks + " checks</b></div></div>" +
    (counts ? '<p class="mon-counts">' + counts + "</p>" : "") +
    (M.warnings && M.warnings.length ? '<ul class="mon-warn">' + M.warnings.map(w => "<li>" + esc(w) + "</li>").join("") + "</ul>" : "") +
    (M.last_error ? '<p class="note">Last error: ' + esc(M.last_error) + "</p>" : "") +
    (changes ? '<details class="mon-changes"><summary>Recent changes within the week</summary><ul>' + changes + "</ul></details>" : "");
  $("app").appendChild(sec);
}
