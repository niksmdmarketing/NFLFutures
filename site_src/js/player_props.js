let D;
const statName = s => s === "pass_attempts" ? "Pass attempts" : "Receptions";
function rowsForGame(g) {
  const stat = $("stat").value, team = $("team").value;
  return g.teams.flatMap(t => t.players.map(p => ({...p, team:t.team})))
    .filter(p => (stat === "all" || p.stat === stat) && (team === "all" || p.team === team))
    .sort((a,b) => a.team.localeCompare(b.team) || a.stat.localeCompare(b.stat) || b.mean-a.mean);
}
function role(p) {
  const a = p.availability_probability;
  const label = a == null ? "Unknown" : a >= .8 ? "Expected active" : a <= .2 ? "Expected out" : "Uncertain";
  const note = (p.availability_notes || []).join(" · ");
  return `<span class="pill">${label}${a == null ? "" : " · " + pct(a)}</span>${note ? `<div class="muted small">${esc(note)}</div>` : ""}`;
}
function render() {
  const g = D.games.find(x => x.game_id === $("game").value) || D.games[0]; if (!g) return;
  const teams = [...new Set(g.teams.map(t => t.team))];
  const old = $("team").value; $("team").innerHTML = '<option value="all">All teams</option>' + teams.map(t => `<option value="${t}">${esc(nm(t))}</option>`).join("");
  $("team").value = teams.includes(old) ? old : "all";
  $("rows").innerHTML = rowsForGame(g).map(p => `<tr><td>${esc(p.team)}</td><td><b>${esc(p.name)}</b><div class="muted small">${esc(p.position)}</div></td><td>${role(p)}</td><td>${statName(p.stat)}</td><td data-v="${p.mean}">${p.mean.toFixed(1)}</td><td>${p.interval80[0]}–${p.interval80[1]}</td><td>${p.illustrative_line.toFixed(1)}</td><td data-v="${p.over_probability}"><b>${pct(p.over_probability)}</b></td></tr>`).join("") || '<tr><td colspan="8">No projections match these filters.</td></tr>';
}
boot(async () => {
  D = await getJSON("nfl_player_props.json");
  setStamp(D.generated_utc, "experimental NFL player forecasts");
  $("game").innerHTML = D.games.map(g => `<option value="${g.game_id}">${esc(nm(g.away))} at ${esc(nm(g.home))} · ${new Date(g.kickoff_utc).toLocaleString([], {weekday:"short",hour:"numeric",minute:"2-digit"})}</option>`).join("");
  $("method").textContent = D.method_note;
  $("evidence").textContent = "Historical evidence: " + D.evidence.qb_attempts + " " + D.evidence.receptions + " " + D.evidence.availability;
  ["game","stat","team"].forEach(id => $(id).addEventListener("change", render));
  render(); sortableTable(document.querySelector("table"));
});
