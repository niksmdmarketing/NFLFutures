/* Week-by-week history page (NBA, NHL). Reads data/replay.json. */
(function () {
  "use strict";
  var root = document.getElementById("replay");
  if (!root) return;
  var D = null, st = { s: 0, m: 0, w: 0 };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pc(v) { return v == null ? "–" : (v / 10).toFixed(1) + "%"; }
  function pc0(x) { return (100 * x).toFixed(0) + "%"; }
  function binLabel(b) {
    var m = String(b).match(/(-?[\d.]+),\s*([\d.]+)/);
    return m ? Math.max(0, Math.round(100 * parseFloat(m[1]))) + "–" + Math.round(100 * parseFloat(m[2])) + "%" : b;
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function stage(S, w) {
    if (w === 0) return "preseason";
    var f = w / Math.max(S.weeks.length - 1, 1);
    return f < 0.25 ? "first quarter" : f < 0.5 ? "second quarter" : f < 0.75 ? "third quarter" : "last quarter";
  }
  function delta(a, b) {
    if (a == null || b == null) return '<span class="muted">–</span>';
    var d = (a - b) / 10;
    if (Math.abs(d) < 0.05) return '<span class="muted">0.0</span>';
    return '<span class="' + (d > 0 ? "up" : "down") + '">' + (d > 0 ? "+" : "") + d.toFixed(1) + "</span>";
  }
  function reliability(S, M, w) {
    var sg = stage(S, w), r = D.reliability[sg] && D.reliability[sg][M.k];
    if (!r) return "";
    var verdict = r.gain > 0.02 ? "clearly better than a flat guess" : r.gain > 0.005 ? "only a little better than a flat guess" : "no better than a flat guess";
    var shape = r.slope == null ? "" : r.slope < 0.8 ? " Past percentages at this stage were <b>too extreme</b>: the favourites won less often than the model said."
      : r.slope > 1.25 ? " Past percentages at this stage were <b>too cautious</b>: the favourites won more often than the model said." : " Past percentages at this stage were <b>about the right size</b>.";
    var rows = r.cal.map(function (c) { return "<tr><td>" + esc(binLabel(c.bin)) + '</td><td class="num">' + pc0(c.pred) + '</td><td class="num">' + pc0(c.actual) + '</td><td class="num">' + c.n + "</td></tr>"; }).join("");
    return '<div class="rp-rel"><h3>How much to trust this</h3>' +
      "<p>Across " + r.n + " replayed seasons, at the <b>" + esc(sg) + "</b> of the season, the “" + esc(M.l) + "” percentages were " + verdict +
      " (error score " + r.ll.toFixed(3) + " against " + r.base.toFixed(3) + " for giving every team the same chance)." + shape + "</p>" +
      '<p class="muted">Weeks in one season move together, so this is really about ' + r.n + " seasons of evidence, not hundreds. Treat gaps of a few points as noise.</p>" +
      '<table class="rp-cal"><thead><tr><th>Model said (range)</th><th>Average said</th><th>Happened</th><th>Team-weeks</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }
  function render() {
    var S = D.seasons[st.s], M = D.markets[st.m], P = S.p[M.k];
    st.w = Math.max(0, Math.min(st.w, S.weeks.length - 1));
    var cur = P[st.w], prev = st.w > 0 ? P[st.w - 1] : null, prev4 = st.w > 3 ? P[st.w - 4] : (st.w > 0 ? P[0] : null);
    var idx = S.teams.map(function (t, i) { return i; }).sort(function (a, b) { return cur[b] - cur[a]; });
    var max = Math.max.apply(null, cur) || 1, o = S.o[M.k];
    var wk = S.weeks[st.w];
    var rows = idx.map(function (i) {
      return "<tr><td>" + esc(S.teams[i]) + '</td><td><span class="rp-bar" style="width:' + Math.round(70 * cur[i] / max) + 'px"></span>' + pc(cur[i]) + "</td><td>" + delta(cur[i], prev && prev[i]) +
        '</td><td class="hide-sm">' + delta(cur[i], prev4 && prev4[i]) + '</td><td>' + (o[i] ? '<span class="hit">✓</span>' : '<span class="muted">·</span>') + "</td></tr>";
    }).join("");
    var seasonOpts = D.seasons.map(function (s, i) { return '<option value="' + i + '"' + (i === st.s ? " selected" : "") + ">" + esc(s.label) + "</option>"; }).join("");
    var mk = D.markets.map(function (m, i) { return '<button type="button" data-m="' + i + '" aria-pressed="' + (i === st.m) + '">' + esc(m.l) + "</button>"; }).join("");
    root.innerHTML = '<div class="rp-controls"><div class="field"><label for="rp-s">Season</label><select id="rp-s">' + seasonOpts + '</select></div>' +
      '<div class="field"><label>Market</label><div class="seg" id="rp-m" role="group">' + mk + "</div></div>" +
      '<div class="rp-week"><label for="rp-w">Week ' + st.w + " of " + (S.weeks.length - 1) + " · " + esc(wk.d) + "</label>" +
      '<input type="range" id="rp-w" min="0" max="' + (S.weeks.length - 1) + '" value="' + st.w + '" step="1"></div></div>' +
      '<div class="rp-head"><b>' + esc(M.l) + "</b><span class=\"rp-tag\">replayed</span><span class=\"muted\">" + (wk.gp ? "about " + wk.gp.toFixed(0) + " games played per team" : "before the season") + "</span></div>" +
      '<div class="scroll"><table class="rp"><thead><tr><th>Team</th><th>Chance</th><th title="Change since the previous week, in percentage points">1 wk</th><th class="hide-sm" title="Change over the previous four weeks">4 wks</th><th title="Did it happen that season?">Result</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" + reliability(S, M, st.w);
    document.getElementById("rp-s").onchange = function (e) { st.s = +e.target.value; st.w = 0; store("rp-s", st.s); render(); };
    document.getElementById("rp-w").oninput = function (e) { st.w = +e.target.value; render(); document.getElementById("rp-w").focus(); };
    Array.prototype.forEach.call(document.querySelectorAll("#rp-m button"), function (b) { b.onclick = function () { st.m = +b.getAttribute("data-m"); render(); }; });
  }
  fetch(root.getAttribute("data-src") || "data/replay.json").then(function (r) { return r.json(); }).then(function (d) {
    D = d;
    st.s = D.seasons.length - 1;
    st.w = Math.floor((D.seasons[st.s].weeks.length - 1) / 2);
    render();
  }).catch(function () { root.innerHTML = '<p class="note">Could not load the history data.</p>'; });
})();
