/* Season futures: division/conference/Super Bowl table, win-total over/under, QB changes. */
let FT = null;
function pcell(p) {
  return '<td class="pc"><span class="bar" style="width:calc(' + (Math.min(1, p) * 100).toFixed(1) + '% - 8px)"></span><b>' + pct(p) + '</b></td>';
}
function renderFutures() {
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
  const rows = Object.entries(FT).filter(([, v]) => v.qb_note && Math.abs(v.qb_adj) >= 0.05).sort((a, b) => a[1].qb_adj - b[1].qb_adj);
  $("qbchg").innerHTML = rows.length ? rows.map(([t, v]) => '<li><b>' + t + '</b><span>' + esc(v.qb_note) + '</span><span class="num ' + (v.qb_adj < 0 ? "adj-neg" : "adj-pos") + '">' + (v.qb_adj > 0 ? "+" : "") + v.qb_adj.toFixed(1) + '</span></li>').join("")
    : '<li class="muted">No quarterback changes are expected this week.</li>';
}
function renderChallenger(C) {
  if (!C || !C.teams) return;
  $("challengerSec").hidden = false;
  const pair = (a, b) => '<td class="num">' + pct(a) + ' <span class="muted">· ' + pct(b) + '</span></td>';
  let h = "";
  Object.entries(DIVS).forEach(([dn, ts]) => {
    h += '<tr class="divhead"><td colspan="5">' + dn + '</td></tr>';
    [...ts].sort((a, b) => FT[b].p_div - FT[a].p_div).forEach(t => {
      const v = FT[t], c = C.teams[t];
      h += '<tr><td><b>' + t + '</b> <span class="muted">' + nm(t) + '</span></td>' + pair(v.p_div, c.p_div) + pair(v.p_playoff, c.p_playoff) + pair(v.p_conf, c.p_conf) + pair(v.p_sb, c.p_sb) + '</tr>';
    });
  });
  $("cbody").innerHTML = h;
}
boot(async meta => {
  const F = await getJSON("futures.json");
  FT = F.teams;
  document.querySelectorAll("[data-nsims]").forEach(el => { if (meta.n_sims) el.textContent = meta.n_sims.toLocaleString(); });
  renderFutures();
  initWT();
  renderQB();
  renderChallenger(F.challenger);
});
