/* Season futures: division/conference/Super Bowl table, win-total over/under, QB changes. */
let FT = null;
function pcell(p) {
  return '<td class="pc" data-v="' + p + '"><span class="bar" style="width:calc(' + (Math.min(1, p) * 100).toFixed(1) + '% - 8px)"></span><b>' + pct(p) + '</b></td>';
}
function renderFutures() {
  if (!$("fbody")) return;
  let h = "";
  Object.entries(DIVS).forEach(([dn, ts]) => {
    h += '<tr class="divhead"><td colspan="7">' + dn + '</td></tr>';
    [...ts].sort((a, b) => FT[b].p_div - FT[a].p_div || FT[b].mean_wins - FT[a].mean_wins).forEach(t => {
      const v = FT[t];
      h += '<tr><td><b>' + t + '</b> <span class="muted">' + nm(t) + '</span></td><td class="num">' + v.mean_wins.toFixed(1) + '</td>' +
        pcell(v.p_div) + pcell(v.p_playoff) + pcell(v.p_seed1) + pcell(v.p_conf) + pcell(v.p_sb) + '</tr>';
    });
  });
  $("fbody").innerHTML = h;
  sortableTable($("fbody").closest("table"));
}
function renderWT() {
  const t = $("wtTeam").value, L = +$("wtLine").value, d = FT[t].win_dist;
  let over = 0, under = 0, push = 0;
  d.forEach((p, w) => { if (w > L) over += p; else if (w < L) under += p; else push += p; });
  $("ou").innerHTML = '<div><small>Over ' + L + '</small><span class="big l-off">' + pct(over) + '</span></div><div><small>Under ' + L + '</small><span class="big l-def">' + pct(under) + '</span></div><div><small>Push</small><span class="big">' + (Number.isInteger(L) ? pct(push) : "–") + '</span></div>';
  const mean = FT[t].mean_wins;
  let lo = 0, acc = 0; for (let w = 0; w < d.length; w++) { acc += d[w]; if (acc >= 0.1) { lo = w; break; } }
  let hi = 17; acc = 0; for (let w = 0; w < d.length; w++) { acc += d[w]; if (acc >= 0.9) { hi = w; break; } }
  $("wtNote").textContent = nm(t) + " project to " + mean.toFixed(1) + " wins. The 80% range is " + lo + " to " + hi + " wins.";
  $("distTitle").textContent = "Win distribution · " + t;
  const Wd = 360, Hd = 160, Lp = 30, Rp = 6, Tp = 10, Bp = 22, n = d.length, bw = (Wd - Lp - Rp) / n;
  const mx = Math.max(0.05, Math.ceil(Math.max(...d) * 20) / 20);
  const y = p => Tp + (1 - p / mx) * (Hd - Tp - Bp);
  let g = "";
  for (let v = 0; v <= mx + 1e-9; v += 0.05) g += '<line x1="' + Lp + '" x2="' + (Wd - Rp) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--line)"/><text x="' + (Lp - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end" font-size="9" fill="var(--muted)">' + Math.round(v * 100) + '%</text>';
  d.forEach((p, w) => {
    const col = w > L ? "var(--off)" : w < L ? "var(--def)" : "var(--even)";
    const x = Lp + w * bw + 1;
    g += '<rect x="' + x.toFixed(1) + '" y="' + y(p).toFixed(1) + '" width="' + (bw - 2).toFixed(1) + '" height="' + (y(0) - y(p)).toFixed(1) + '" fill="' + col + '"><title>' + w + ' wins: ' + (p * 100).toFixed(1) + '%</title></rect>';
    if (w % 2 === 0 || w === 17) g += '<text x="' + (x + bw / 2 - 1).toFixed(1) + '" y="' + (Hd - 8) + '" text-anchor="middle" font-size="9" fill="var(--muted)">' + w + '</text>';
  });
  $("dist").innerHTML = '<svg viewBox="0 0 ' + Wd + ' ' + Hd + '" role="img" aria-label="Chance of each final win total for ' + nm(t) + '">' + g + '</svg>';
}
function initWT() {
  if (!$("wtTeam")) return;
  const teams = Object.keys(FT).sort((a, b) => nm(a).localeCompare(nm(b)));
  const top = Object.keys(FT).sort((a, b) => FT[b].p_sb - FT[a].p_sb)[0];
  $("wtTeam").innerHTML = teams.map(t => '<option value="' + t + '"' + (t === top ? " selected" : "") + '>' + nm(t) + '</option>').join("");
  const lines = []; for (let v = 2.5; v <= 14.5; v += 0.5) lines.push(v);
  $("wtLine").innerHTML = lines.map(v => '<option value="' + v + '">' + v + '</option>').join("");
  const setDefault = () => { $("wtLine").value = String(Math.min(14.5, Math.max(2.5, Math.floor(FT[$("wtTeam").value].mean_wins) + 0.5))); };
  setDefault();
  $("wtTeam").addEventListener("change", () => { setDefault(); renderWT(); });
  $("wtLine").addEventListener("change", renderWT);
  renderWT();
}
function renderQB() {
  if (!$("qbchg")) return;
  const rows = Object.entries(FT).filter(([, v]) => v.qb_note && Math.abs(v.qb_adj) >= 0.05).sort((a, b) => a[1].qb_adj - b[1].qb_adj);
  $("qbchg").innerHTML = rows.length ? rows.map(([t, v]) => '<li><b>' + t + '</b><span>' + esc(v.qb_note) + '</span><span class="num ' + (v.qb_adj < 0 ? "adj-neg" : "adj-pos") + '">' + (v.qb_adj > 0 ? "+" : "") + v.qb_adj.toFixed(1) + '</span></li>').join("")
    : '<li class="muted">No quarterback changes are expected this week.</li>';
}
function renderChallenger(C) {
  if (!C || !C.teams || !$("challengerSec")) return;
  $("challengerSec").hidden = false;
  const pair = (a, b) => '<td class="num" data-v="' + a + '">' + pct(a) + ' <span class="muted">· ' + pct(b) + '</span></td>';
  let h = "";
  Object.entries(DIVS).forEach(([dn, ts]) => {
    h += '<tr class="divhead"><td colspan="5">' + dn + '</td></tr>';
    [...ts].sort((a, b) => FT[b].p_div - FT[a].p_div).forEach(t => {
      const v = FT[t], c = C.teams[t];
      h += '<tr><td><b>' + t + '</b> <span class="muted">' + nm(t) + '</span></td>' + pair(v.p_div, c.p_div) + pair(v.p_playoff, c.p_playoff) + pair(v.p_conf, c.p_conf) + pair(v.p_sb, c.p_sb) + '</tr>';
    });
  });
  $("cbody").innerHTML = h;
  sortableTable($("cbody").closest("table"));
}
function renderChallenger5(C) {
  if (!C || !C.teams || !$("challenger5Sec")) return;
  $("challenger5Sec").hidden = false;
  const pair = (a, b) => '<td class="num" data-v="' + b + '">' + pct(a) + ' <span class="muted">· ' + pct(b) + '</span></td>';
  const ts = Object.keys(FT).filter(t => C.teams[t]).sort((a, b) => C.teams[b].p_conf - C.teams[a].p_conf).slice(0, 32);
  $("c5body").innerHTML = ts.map(t => '<tr><td><b>' + t + '</b> <span class="muted">' + nm(t) + '</span></td>' + pair(FT[t].p_playoff, C.teams[t].p_playoff) + pair(FT[t].p_div, C.teams[t].p_div) + pair(FT[t].p_conf, C.teams[t].p_conf) + pair(FT[t].p_sb, C.teams[t].p_sb) + '</tr>').join("");
  sortableTable($("c5body").closest("table"));
}
/* futures page: v5 as the in-season betting number, v4 alongside (27 Oct 2026) */
function renderV5Tab(C) {
  const tb = $("v5body");
  if (!tb || !C || !C.teams) return;
  const pair = (a, b) => '<td class="num" data-v="' + a + '"><b>' + pct(a) + '</b> <span class="muted">· ' + pct(b) + '</span></td>';
  const ts = Object.keys(FT).filter(t => C.teams[t]).sort((a, b) => C.teams[b].p_playoff - C.teams[a].p_playoff);
  tb.innerHTML = ts.map(t => { const v = C.teams[t], f = FT[t];
    return '<tr><td><b>' + t + '</b> <span class="muted">' + nm(t) + '</span></td>' + pair(v.p_div, f.p_div) + pair(v.p_playoff, f.p_playoff) +
      pair(v.p_seed1, f.p_seed1) + pair(v.p_conf, f.p_conf) + pair(v.p_sb, f.p_sb) + '</tr>'; }).join("");
  sortableTable(tb.closest("table"));
}
function renderTrack(T) {
  if (!T || !T.markets || !$("trackSec")) return;
  $("trackSec").hidden = false;
  $("trackNote").innerHTML = "Tested on " + T.seasons + ": at each point the model only sees games already played, simulates the rest of that season, and is scored against what happened. " +
    "<b>Skill</b> is how much better than a blind guess (each team getting the base rate) the probabilities were: 0% means no better, higher is better. " +
    "<b>Winner got</b> is the average probability the model had given the team that actually won. The quarterback and pressure layers are left out because past depth charts are not available as they stood each week, and the simulation spread was tuned on these seasons, so read these as a fair guide rather than a strict out-of-sample test.";
  const live = "v4 (live)";
  let h = "";
  T.markets.forEach(m => {
    const v = m.by_model[live], c = m.by_model["v3 (challenger)"];
    h += "<tr><td><b>" + esc(m.label) + "</b></td>" + v.skill.map((s, i) => '<td class="num" data-v="' + s + '">' + Math.round(s * 100) + '% skill<br><span class="muted">winner got ' + pct(v.winner_p[i]) +
      (c ? " · v3 skill " + Math.round(c.skill[i] * 100) + "%" : "") + "</span></td>").join("") + "</tr>";
  });
  const w = T.wins;
  if (w && w[live]) h += '<tr><td><b>Win totals</b><br><span class="muted">average miss, wins</span></td>' + w[live].map((x, i) => '<td class="num">' + x.toFixed(2) +
    '<br><span class="muted">simple guess ' + w["base rate"][i].toFixed(2) + "</span></td>").join("") + "</tr>";
  $("trackBody").innerHTML = h;
}
/* in-page views on the futures page (Chances / vs the market / Win totals); the view is kept in the address (#market, #wins) */
function initTabs() {
  const tabs = document.querySelectorAll("[data-ftab]");
  if (!tabs.length) return;
  const show = k => {
    if (!document.querySelector('[data-fpanel="' + k + '"]')) k = "chances";
    document.querySelectorAll("[data-fpanel]").forEach(p => { p.hidden = p.dataset.fpanel !== k; });
    tabs.forEach(b => { const on = b.dataset.ftab === k; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
  };
  tabs.forEach(b => b.addEventListener("click", () => { show(b.dataset.ftab); try { history.replaceState(null, "", b.dataset.ftab === "chances" ? location.pathname : "#" + b.dataset.ftab); } catch (e) {} }));
  show((location.hash || "").slice(1) || "chances");
}
/* trust badges under the chances table's headings, and the by-stage table on the Model page */
function renderTrust(TR) {
  if (!TR) return;
  const tb = $("fbody");
  if (tb) {
    const keys = [null, null, "p_div", "p_playoff", "p_seed1", "p_conf", "p_sb"];
    tb.closest("table").querySelectorAll("thead th").forEach((th, i) => { if (keys[i]) th.insertAdjacentHTML("beforeend", trustBadge(TR, keys[i])); });
    tb.closest(".scroll").insertAdjacentHTML("beforebegin", trustLegend(TR));
  }
  const sec = $("trustSec");
  if (sec) sec.innerHTML = trustTable(TR, {p_div: "Win division", p_playoff: "Make the playoffs", p_seed1: "No. 1 seed", p_conf: "Win conference", p_sb: "Win the Super Bowl"});
}
boot(async meta => {
  initTabs();
  const F = await getJSON("futures.json");
  FT = F.teams;
  document.querySelectorAll("[data-nsims]").forEach(el => { if (meta.n_sims) el.textContent = meta.n_sims.toLocaleString(); });
  renderFutures();
  initWT();
  renderQB();
  renderChallenger(F.challenger);
  renderChallenger5(F.challenger_v5);
  renderV5Tab(F.challenger_v5);
  renderTrack(F.track_record);
  renderTrust(await getTrust());
});
