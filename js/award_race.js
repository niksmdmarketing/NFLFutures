/* Award race: current contenders (stats to date, 17-game pace, team record, model chance) next to every winner since
   2018 at the same week and at season's end. All tables sort by clicking a heading. */
const ORDER = ["MVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY", "COY"];
let AR = null, CURA = "MVP";
const n = (v, d) => v == null ? "–" : (Math.round(v * Math.pow(10, d)) / Math.pow(10, d)).toLocaleString();

function playerTables(a, week) {
  const cols = a.cols;
  const dec = k => (k === "tot_epa" ? 1 : k === "dsacks" ? 1 : 0);
  let h = '<h2>Current race <small class="muted">through Week ' + week + '</small></h2>' +
    '<p class="note">Bold is the total so far; the small number is the 17-game pace. Model chance is the site\'s award model.</p>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th>Player</th><th>Team</th><th>Pos</th><th>Record</th><th>Model chance</th><th>G</th>' +
    cols.map(([, lab]) => '<th>' + esc(lab) + '</th>').join("") + '</tr></thead><tbody>' +
    a.current.map(r => '<tr><td><b>' + esc(r.name) + '</b></td><td style="text-align:left">' + esc(r.team) + '</td><td style="text-align:left">' + esc(r.pos) +
      '</td><td data-v="' + r.win_pct + '">' + esc(r.record) + '</td><td data-v="' + (r.model_prob || 0) + '">' + (r.model_prob != null ? pct(r.model_prob) : "–") + '</td><td>' + r.games + '</td>' +
      cols.map(([k]) => '<td data-v="' + r[k] + '"><b>' + n(r[k], dec(k)) + '</b> <small>' + n(r[k + "_pace"], 0) + '</small></td>').join("") + '</tr>').join("") +
    '</tbody></table></div>';
  h += '<h2 style="margin-top:22px">Past winners <small class="muted">at Week ' + week + ' → season end</small></h2>' +
    '<p class="note">Each winner\'s totals through the same week (bold) and at the end of the regular season (small), with the team record at both points.</p>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th>Season</th><th>Winner</th><th>Team</th><th>Record at Wk ' + week + '</th><th>Final record</th>' +
    cols.map(([, lab]) => '<th>' + esc(lab) + '</th>').join("") + '</tr></thead><tbody>' +
    a.past.slice().reverse().map(r => '<tr><td>' + r.season + '</td><td style="text-align:left"><b>' + esc(r.name) + '</b></td><td style="text-align:left">' + esc(r.team) +
      '</td><td>' + esc(r.record_at) + '</td><td>' + esc(r.record_final) + '</td>' +
      cols.map(([k]) => '<td data-v="' + r[k + "_at"] + '"><b>' + n(r[k + "_at"], dec(k)) + '</b> <small>' + n(r[k + "_final"], dec(k)) + '</small></td>').join("") + '</tr>').join("") +
    '</tbody></table></div>';
  return h;
}
function coachTables(a, week) {
  let h = '<h2>Current race <small class="muted">through Week ' + week + '</small></h2>' +
    '<p class="note">Coach of the Year usually goes to a big jump on last season\'s record, so the change in win % is shown next to the model chance.</p>' +
    '<div class="scroll"><table class="stbl"><thead><tr><th>Coach</th><th>Team</th><th>Record</th><th>Win %</th><th>Last season</th><th>Change in win %</th><th>Model chance</th></tr></thead><tbody>' +
    a.current.map(r => '<tr><td style="text-align:left"><b>' + esc(r.coach) + '</b></td><td style="text-align:left">' + esc(r.team) + '</td><td data-v="' + r.win_pct + '">' + esc(r.record) +
      '</td><td>' + pct(r.win_pct) + '</td><td data-v="' + r.prev_win_pct + '">' + esc(r.prev_record) + '</td><td data-v="' + r.improve + '" class="' + (r.improve > 0 ? "adj-pos" : r.improve < 0 ? "adj-neg" : "") + '">' +
      (r.improve > 0 ? "+" : "") + Math.round(r.improve * 100) + ' pts</td><td data-v="' + (r.model_prob || 0) + '">' + (r.model_prob != null ? pct(r.model_prob) : "–") + '</td></tr>').join("") +
    '</tbody></table></div>';
  h += '<h2 style="margin-top:22px">Past winners</h2><div class="scroll"><table class="stbl"><thead><tr><th>Season</th><th>Team</th><th>Record at Wk ' + week + '</th><th>Final record</th><th>Previous season</th></tr></thead><tbody>' +
    a.past.slice().reverse().map(r => '<tr><td>' + r.season + '</td><td style="text-align:left"><b>' + esc(nm(r.team)) + '</b></td><td>' + esc(r.record_at) + '</td><td>' + esc(r.record_final) + '</td><td>' + esc(r.prev_record) + '</td></tr>').join("") +
    '</tbody></table></div>';
  return h;
}
function draw() {
  document.querySelectorAll("[data-aw]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.aw === CURA)));
  const a = AR.awards[CURA];
  $("race").innerHTML = '<h2 style="margin-bottom:6px">' + esc(a.title) + '</h2>' + (CURA === "COY" ? coachTables(a, AR.week) : playerTables(a, AR.week));
  $("race").querySelectorAll("table").forEach(sortableTable);
  try { history.replaceState(null, "", "#" + CURA); } catch (e) {}
}
boot(async () => {
  AR = await getJSON("award_race.json");
  try { const h = location.hash.slice(1); if (ORDER.includes(h)) CURA = h; } catch (e) {}
  $("app").innerHTML = '<div class="filters"><div class="field"><span class="flabel">Award</span><div class="seg" role="group" aria-label="Award" style="flex-wrap:wrap">' +
    ORDER.filter(k => AR.awards[k]).map(k => '<button type="button" data-aw="' + k + '">' + k + '</button>').join("") + '</div></div></div><div id="race" class="page"></div>';
  document.querySelectorAll("[data-aw]").forEach(b => b.addEventListener("click", () => { CURA = b.dataset.aw; draw(); }));
  draw();
});
