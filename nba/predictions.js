/* NBA Forecast > Games: upcoming game predictions, then completed games scored on the forecast published before tip-off.
   Reads data/predictions.json written by pipeline/nba.py (_prediction_record). No number on this page is recomputed after a game. */
boot(async () => {
  const app = $("app");
  const sty = document.createElement("style");
  sty.textContent = ".pr-sum{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,170px),1fr));gap:12px;margin:0 0 8px}" +
    ".pr-sum .panel{gap:2px;padding:12px 14px}.pr-sum b{font-size:1.5rem;font-family:var(--font-display)}.pr-sum span{font-size:.85rem;color:var(--muted)}" +
    ".stbl td.l,.stbl th.l{text-align:left}.ok{color:var(--off-ink);font-weight:600}.no{color:var(--def-ink);font-weight:600}" +
    ".pr-day{margin:18px 0 6px;font-family:var(--font-display);font-size:1.05rem;text-transform:uppercase;letter-spacing:.04em}section+section{margin-top:28px}";
  document.head.appendChild(sty);
  let d;
  try { d = await getJSON("predictions.json"); } catch (e) { app.innerHTML = '<p class="note">Game predictions are not available yet.</p>'; return; }
  setStamp(d.updated, "NBA game predictions");
  const when = iso => { const t = new Date(iso); return isNaN(t) ? null : t; };
  const dayKey = g => { const t = g.tip && when(g.tip); return t ? t.toLocaleDateString(undefined, {weekday: "long", day: "numeric", month: "long"}) : fmtDate(g.date); };
  const clock = g => { const t = g.tip && when(g.tip); return t ? t.toLocaleTimeString(undefined, {hour: "numeric", minute: "2-digit"}) : "–"; };
  const fav = g => g.p_home >= 0.5 ? [g.home, g.home_name, g.p_home] : [g.away, g.away_name, 1 - g.p_home];
  const mg = g => { if (g.margin == null) return "–"; const m = g.p_home >= 0.5 ? g.margin : -g.margin; return (m >= 0 ? "by " : "trail by ") + Math.abs(m).toFixed(1); };
  const matchup = g => esc(g.away_name) + ' <span class="note">at</span> ' + esc(g.home_name);
  const table = (head, rows) => '<div class="scroll"><table class="stbl"><thead><tr>' + head.map(([l, n]) => "<th" + (n ? "" : ' class="l"') + ">" + esc(l) + "</th>").join("") +
    "</tr></thead><tbody>" + rows.join("") + "</tbody></table></div>";
  const td = (v, l) => "<td" + (l ? ' class="l"' : "") + ">" + v + "</td>";
  let out = "";

  // record first, so the track record is visible at a glance; detailed results stay at the bottom
  const r = d.record || {};
  if (r.games) {
    const cells = [[r.correct + " of " + r.games, "favourite won (" + Math.round(100 * r.correct / r.games) + "%)"],
                   [r.brier.toFixed(3), "Brier score (coin flip 0.250; lower is better)"],
                   [r.log_loss.toFixed(3), "log loss (coin flip 0.693; lower is better)"],
                   [Math.round(100 * r.avg_fav) + "%", "average favourite chance (expected hit rate)"]];
    if (r.margin_games) cells.push([r.margin_mae.toFixed(1), "average margin miss, points (" + r.margin_games + " games)"]);
    out += '<section><h2>Track record</h2><div class="pr-sum">' + cells.map(([b, s]) => '<div class="panel"><b>' + b + "</b><span>" + esc(s) + "</span></div>").join("") + "</div>" +
      '<p class="note">Scored only on the last forecast published before each tip-off' + (d.since ? ", archived since " + esc(fmtDate(d.since)) : "") +
      ". A well-calibrated forecaster's favourites win about as often as the average favourite chance says." +
      (r.games < 100 ? " " + r.games + " games is a very small sample: differences of several percentage points are noise at this size." : "") +
      (r.not_recorded ? " " + r.not_recorded + " played game" + (r.not_recorded === 1 ? " was" : "s were") + " not recorded in time and " + (r.not_recorded === 1 ? "is" : "are") + " left out." : "") +
      (r.margin_games ? "" : " Margin accuracy starts with games archived from 21 Oct 2026.") + "</p></section>";
  }

  const up = d.upcoming || [];
  out += "<section><h2>Upcoming games</h2>";
  if (!up.length) out += '<p class="note">No upcoming games are listed.</p>';
  else {
    const days = [];
    up.slice(0, 120).forEach(g => { const k = dayKey(g); if (!days.length || days[days.length - 1][0] !== k) days.push([k, []]); days[days.length - 1][1].push(g); });
    out += days.slice(0, 7).map(([k, gs]) => '<div class="pr-day">' + esc(k) + "</div>" + table([["Tip-off"], ["Game"], ["Favourite"], ["Win chance", 1], ["Projected margin", 1]],
      gs.map(g => { const [, n, p] = fav(g); return "<tr>" + td(clock(g), 1) + td(matchup(g), 1) + td(esc(n), 1) + td(pct(p)) + td(mg(g)) + "</tr>"; }))).join("");
    out += '<p class="note">Times are in your time zone. Chances update with each refresh (injury reports, results) until tip-off; the number in place just before tip-off is the one scored.</p>';
  }
  out += "</section>";

  if ((d.in_progress || []).length)
    { const hm = d.in_progress.some(g => g.margin != null);
      out += "<section><h2>Awaiting result</h2>" + table([["Game"], ["Forecast at tip-off"], ["Win chance", 1]].concat(hm ? [["Projected margin", 1]] : []),
        d.in_progress.map(g => { const [, n, p] = fav(g); return "<tr>" + td(matchup(g), 1) + td(esc(n), 1) + td(pct(p)) + (hm ? td(mg(g)) : "") + "</tr>"; })) + "</section>"; }

  const res = d.results || [];
  out += "<section><h2>Results</h2>";
  if (!res.length) out += '<p class="note">No scored games yet. Played games appear here once their pre-tip-off forecast can be checked against the result.</p>';
  else {
    const hasM = res.some(g => g.margin != null);
    out += table([["Date"], ["Game"], ["Forecast favourite"], ["Win chance", 1]].concat(hasM ? [["Projected margin", 1]] : []).concat([["Final", 1], ["Right?"]]),
      res.map(g => {
        const [ft, n, p] = fav(g), am = ft === g.home ? g.home_score - g.away_score : g.away_score - g.home_score;
        return "<tr>" + td(esc(fmtDate(g.date)), 1) + td(matchup(g), 1) + td(esc(n), 1) + td(pct(p)) + (hasM ? td(mg(g)) : "") +
          td(g.away_score + "–" + g.home_score) +
          td((g.correct ? '<span class="ok">✓ right</span>' : '<span class="no">✗ wrong</span>') + ' <span class="note">(' + (am > 0 ? "won by " : "lost by ") + Math.abs(am) + ")</span>", 1) + "</tr>";
      }));
    out += '<p class="note">Final score is away–home. "Right" means the team we made favourite won; a 55% favourite losing is expected 45% of the time, so single games say little.</p>';
  }
  out += "</section>";

  if ((r.calibration || []).length)
    out += "<section><h2>Calibration</h2>" + table([["Favourite chance"], ["Games", 1], ["Average forecast", 1], ["Favourite won", 1]],
      r.calibration.map(c => "<tr>" + td(Math.round(c.lo * 100) + "–" + Math.round(c.hi * 100) + "%", 1) + td(c.n) + td(Math.round(100 * c.pred) + "%") + td(Math.round(100 * c.won) + "%") + "</tr>")) +
      '<p class="note">In each band the two percentages should be close once there are a few hundred games.</p></section>';

  out += '<p class="note">Evidence label: the single-game model (team rating plus the injury layer) is a historical improvement over the team rating alone on past seasons; this page is its live, forward record. Independent projections from public data, not betting advice.</p>';
  app.innerHTML = out;
});
