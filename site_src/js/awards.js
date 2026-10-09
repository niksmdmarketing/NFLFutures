/* Award probabilities with each model's historical track record. */
const AWARD_ORDER = ["MVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY", "COY"];
function badgeFor(e) {
  if (!e) return '<span class="badge weak">Untested</span>';
  const gap = e.baseline_log_loss - e.log_loss;
  return gap <= 0 ? '<span class="badge weak">No proven skill</span>' : gap < 0.5 ? '<span class="badge weak">Weak signal</span>' : '<span class="badge good">Tested</span>';
}
function relFor(e) {
  if (!e) return "";
  const n = e.seasons || 8, gap = e.baseline_log_loss - e.log_loss;
  let s = "From Week 4 in 2018–2025, the eventual winner averaged " + Math.round(e.mean_p_winner * 100) + "% and was in the top three in " + Math.round(e.top3_rate * n) + " of " + n + " seasons.";
  if (e.winner_in_pool != null && e.winner_in_pool < 1) {
    const miss = Math.round((1 - e.winner_in_pool) * n);
    s += " The winner was outside the candidate list in " + miss + " of " + n + " seasons.";
  }
  if (gap <= 0) s += " This model did no better than picking at random, so use the list as names to watch, not odds.";
  return s;
}
boot(async () => {
  const A = await getJSON("awards.json");
  $("awards").innerHTML = AWARD_ORDER.filter(k => A[k]).map(k => {
    const a = A[k];
    if (!a.candidates || !a.candidates.length) {
      return '<article class="panel award"><h2>' + esc(a.title) + '</h2><p class="rel">No candidates yet. The list fills in once games have been played.</p></article>';
    }
    const items = a.candidates.slice(0, 10).map(c => '<li><span class="who">' + esc(c.name) + ' <small>' + esc(c.team) + (c.pos && c.pos !== "HC" ? " · " + esc(c.pos) : "") + '</small></span><span class="pct">' + pct(c.prob) + '</span><span class="stat">' + esc(c.detail) + '</span></li>').join("");
    const rest = (a.field || 0) + a.candidates.slice(10).reduce((s, c) => s + c.prob, 0);
    return '<article class="panel award"><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap"><h2>' + esc(a.title) + '</h2>' + badgeFor(a.eval) + '</div><p class="rel">' + relFor(a.eval) + '</p><ol>' + items +
      '<li><span class="who muted">Rest of the field</span><span class="pct muted">' + pct(rest) + '</span></li></ol></article>';
  }).join("");
});
