/* NFL player forecasts: "if he plays" distributions, grouped by the latest injury designation (26 Oct 2026). */
let D;
const statName = s => s === "pass_attempts" ? "Pass attempts" : "Receptions";
const statusOf = p => p.report_status || (p.availability_probability === 0 ? "out" : "clear");

function rows(g) {
  const stat = $("stat").value, team = $("team").value;
  return g.teams.flatMap(t => t.players.map(p => ({...p, team: t.team})))
    .filter(p => (stat === "all" || p.stat === stat) && (team === "all" || p.team === team))
    .sort((a, b) => b.mean - a.mean);
}

function row(p) {
  const backup = p.usual_availability != null && p.usual_availability < 0.6 ? '<small>backup</small>' : "";
  return `<tr><td><b>${esc(p.name)}</b><small>${esc(p.position)}</small>${backup}</td><td>${esc(p.team)}</td><td>${statName(p.stat)}</td>` +
    `<td data-v="${p.mean}">${p.mean.toFixed(1)}</td><td data-v="${p.interval80[0]}">${p.interval80[0]}–${p.interval80[1]}</td>` +
    `<td data-v="${p.illustrative_line}">${p.illustrative_line.toFixed(1)}</td><td data-v="${p.over_probability}"><b>${pct(p.over_probability)}</b></td></tr>`;
}

function render() {
  const g = D.games.find(x => x.game_id === $("game").value) || D.games[0];
  if (!g) { $("clearRows").innerHTML = '<tr><td colspan="7" class="empty">No upcoming games in the next eight days.</td></tr>'; return; }
  const teams = [...new Set(g.teams.map(t => t.team))], old = $("team").value;
  $("team").innerHTML = '<option value="all">All teams</option>' + teams.map(t => `<option value="${t}">${esc(nm(t))}</option>`).join("");
  $("team").value = teams.includes(old) ? old : "all";
  const all = rows(g), clear = all.filter(p => statusOf(p) === "clear"), q = all.filter(p => statusOf(p) === "questionable");
  const hidden = all.filter(p => ["doubtful", "out"].includes(statusOf(p)));
  $("clearRows").innerHTML = clear.map(row).join("") || '<tr><td colspan="7" class="empty">No available players match these filters.</td></tr>';
  $("qRows").innerHTML = q.map(row).join("") || '<tr><td colspan="7" class="empty">No questionable players for this selection.</td></tr>';
  $("hidden").textContent = hidden.length ? `Not shown: ${hidden.length} doubtful or out (${hidden.map(p => p.name).filter((v, i, a) => a.indexOf(v) === i).join(", ")}).` : "";
}

boot(async () => {
  D = await getJSON("nfl_player_props.json");
  setStamp(D.generated_utc, "experimental NFL player forecasts");
  $("game").innerHTML = D.games.map(g => `<option value="${g.game_id}">${esc(nm(g.away))} at ${esc(nm(g.home))} · ${new Date(g.kickoff_utc).toLocaleString([], {weekday: "short", hour: "numeric", minute: "2-digit"})}</option>`).join("");
  $("method").textContent = D.method_note;
  const e = D.evidence || {};
  $("evidence").textContent = "Historical evidence: " + [e.qb_attempts, e.receptions, e.availability].filter(Boolean).join(" ");
  ["game", "stat", "team"].forEach(id => $(id).addEventListener("change", render));
  render();
  sortableTable($("clearTable")); sortableTable($("qTable"));
});
