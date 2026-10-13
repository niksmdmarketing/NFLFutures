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
  const R = A.races || {};
  const keys = Object.keys(R).filter(k => R[k].candidates && R[k].candidates.length);
  if (keys.length) {
    const fmtv = v => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1));
    $("awards").insertAdjacentHTML("beforeend", '<article class="panel award" style="grid-column:1/-1"><h2>Season stat leaders</h2><p class="rel">Chance of finishing the regular season first in each stat: each player\'s total so far, his rate (blended with last season), the games he is likely to play and his team\'s games left are simulated, ties split. Replayed on 2012–2025 from week 3: favourites given about 34% early won 37% of the time, 44% mid-season won 46%, 65% late won 68%.</p></article>' +
      keys.map(k => {
        const a = R[k];
        const items = a.candidates.map(c => '<li><span class="who">' + esc(c.name) + ' <small>' + esc(c.team) + '</small></span><span class="pct">' + pct(c.prob) + '</span><span class="stat">' + fmtv(c.value) + ' in ' + c.games + ' games · projected ' + fmtv(c.proj) + '</span></li>').join("");
        return '<article class="panel award"><h2>' + esc(a.title) + '</h2><ol>' + items + '</ol></article>';
      }).join(""));
  }
});
