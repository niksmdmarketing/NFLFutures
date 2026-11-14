/* Schedule difficulty page (all five sports). Reads data/schedule.json. */
(function () {
  "use strict";
  var root = document.getElementById("sched");
  if (!root) return;
  var SRC = root.getAttribute("data-src") || "data/schedule.json";
  var WIN = { "5": "Next 5", "10": "Next 10", "all": "Rest of season" };
  var state = { d: null, win: "5", sort: { k: null, dir: 1 }, team: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function f1(x) { return x == null ? "–" : x.toFixed(1); }
  function f2(x) { return x == null ? "–" : x.toFixed(2); }
  function sg(x, d) { return x == null ? "–" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d == null ? 1 : d); }
  function fmtDate(s) {
    var p = s.split("-");
    var m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+p[1] - 1];
    return +p[2] + " " + m;
  }
  function wkey() { return "w" + state.win; }
  function wd(t) { return t[wkey()]; }

  var BAND_NAME = { 1: "Very easy", 2: "Easy", 3: "Average", 4: "Hard", 5: "Very hard" };

  function cards(d) {
    var ok = d.teams.filter(function (t) { return wd(t); });
    if (ok.length < 4) return "";
    ok.sort(function (a, b) { return wd(a).diff - wd(b).diff; });
    function list(arr) {
      return arr.map(function (t) {
        return '<li><b>' + esc(t.name) + '</b><span>' + sg(-wd(t).eff, 1) + " wins vs a coin-flip schedule</span></li>";
      }).join("");
    }
    return '<div class="sc-cards"><section class="sc-card easy"><h3>Easiest ' + WIN[state.win].toLowerCase() + "</h3><ol>" + list(ok.slice(0, 3)) +
      '</ol></section><section class="sc-card hard"><h3>Hardest ' + WIN[state.win].toLowerCase() + "</h3><ol>" + list(ok.slice(-3).reverse()) + "</ol></section></div>";
  }

  function ticker(d) {
    var n = state.win === "5" ? 5 : state.win === "10" ? 10 : 15;
    var teams = d.teams.filter(function (t) { return wd(t); }).sort(function (a, b) { return wd(a).diff - wd(b).diff; });
    var head = '<th scope="col">Team</th>';
    for (var i = 1; i <= n; i++) head += '<th scope="col">' + i + "</th>";
    var rows = teams.map(function (t) {
      var cells = "";
      for (var i = 0; i < n; i++) {
        var g = t.games[i];
        if (!g) { cells += '<td class="sc-x"></td>'; continue; }
        var tip = fmtDate(g[0]) + ": " + (g[8] ? "neutral venue" : g[2] ? "home" : "away") + " vs " + (d.names[g[1]] || g[1]) +
          (g[6] ? ", short rest" : "") + (g[7] ? ", long rest" : "") + ". " + BAND_NAME[g[3]] + ": an average team wins " + Math.round(g[4] * 100) + "%, " +
          esc(t.name) + " " + Math.round(g[5] * 100) + "%.";
        cells += '<td class="sc-g b' + g[3] + '" title="' + esc(tip) + '"><span>' + (g[2] || g[8] ? "" : "@") + esc(g[1]) + "</span>" +
          (g[6] ? '<i title="Short rest">•</i>' : "") + "</td>";
      }
      return '<tr><td class="sc-team">' + esc(t.name) + "</td>" + cells + "</tr>";
    }).join("");
    var note = state.win === "all" ? " Showing the first 15 remaining games." : "";
    return '<h2 class="sc-h">Fixture ticker</h2><p class="note">Each box is an opponent, coloured by how hard the game is for an average team (venue and rest included). ' +
      '"@" means away; a dot means short rest. Easiest run first.' + note + '</p><div class="scroll"><table class="stbl sc-tick"><thead><tr>' + head +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" + legend();
  }

  function legend() {
    return '<div class="sc-leg">' + [1, 2, 3, 4, 5].map(function (b) {
      return '<span><i class="sc-sw b' + b + '"></i>' + BAND_NAME[b] + "</span>";
    }).join("") + "</div>";
  }

  var COLS = [
    { k: "name", l: "Team", get: function (t) { return t.name; }, txt: true },
    { k: "score", l: "Difficulty<small>0 easy – 10 hard</small>", get: function (t) { return wd(t) ? wd(t).score : null; }, fmt: "bar" },
    { k: "opp", l: "Opp. rating<small>avg, vs league</small>", get: function (t) { return wd(t) ? wd(t).opp : null; }, fmt: function (v) { return sg(v, 2); } },
    { k: "eff", l: "Schedule effect<small>wins</small>", get: function (t) { return wd(t) ? -wd(t).eff : null; }, fmt: function (v) { return sg(v, 2); } },
    { k: "n", l: "Games", get: function (t) { return wd(t) ? wd(t).n : null; }, fmt: function (v) { return v; } },
    { k: "home", l: "Home", get: function (t) { return wd(t) ? wd(t).home : null; }, fmt: function (v) { return v; } },
    { k: "short", l: "Short rest", get: function (t) { return wd(t) ? wd(t).short : null; }, fmt: function (v) { return v; } },
    { k: "expw", l: "Exp. wins<small>in window</small>", get: function (t) { return wd(t) ? wd(t).expw : null; }, fmt: f1 },
    { k: "proj", l: "Projected wins<small>final</small>", get: function (t) { return t.proj_w; }, fmt: f1 },
    { k: "rest", l: "Rest of season<small>effect, wins</small>", get: function (t) { return t.rest_eff == null ? null : -t.rest_eff; }, fmt: function (v) { return sg(v, 2); } },
    { k: "past", l: "Faced so far<small>effect, wins</small>", get: function (t) { return t.past_eff == null ? null : -t.past_eff; }, fmt: function (v) { return sg(v, 2); } }
  ];
  var DEFAULT_SORT = { k: "score", dir: 1 };

  function cellHtml(t, c) {
    var v = c.get(t);
    if (c.txt) return '<td class="sc-tname"><button type="button" class="sc-pick" data-team="' + esc(t.team) + '">' + esc(v) + "</button></td>";
    if (v == null) return '<td class="muted">–</td>';
    if (c.fmt === "bar") {
      return '<td data-v="' + v + '"><span class="sc-bar" title="' + v + ' out of 10"><i style="width:' + (v * 10) + '%" class="s' + Math.min(5, Math.floor(v / 2) + 1) + '"></i></span> <b>' + v.toFixed(1) + "</b></td>";
    }
    return '<td data-v="' + v + '">' + c.fmt(v) + "</td>";
  }

  function table(d) {
    var s = state.sort.k ? state.sort : DEFAULT_SORT;
    var col = COLS.filter(function (c) { return c.k === s.k; })[0] || COLS[1];
    var list = d.teams.slice().sort(function (a, b) {
      var va = col.get(a), vb = col.get(b);
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string") return s.dir * va.localeCompare(vb);
      return s.dir * (va - vb);
    });
    var head = COLS.map(function (c) {
      var as = s.k === c.k ? (s.dir > 0 ? "ascending" : "descending") : "none";
      return '<th scope="col" data-k="' + c.k + '" aria-sort="' + as + '" tabindex="0">' + c.l + "</th>";
    }).join("");
    var body = list.map(function (t) {
      return "<tr>" + COLS.map(function (c) { return cellHtml(t, c); }).join("") + "</tr>";
    }).join("");
    return '<h2 class="sc-h">All teams</h2><div class="scroll"><table class="stbl sc-tbl"><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  function rolling(d) {
    var t = d.teams.filter(function (x) { return x.team === state.team; })[0];
    var opts = d.teams.slice().sort(function (a, b) { return a.name.localeCompare(b.name); }).map(function (x) {
      return '<option value="' + esc(x.team) + '"' + (x.team === state.team ? " selected" : "") + ">" + esc(x.name) + "</option>";
    }).join("");
    var out = '<h2 class="sc-h">Rolling 5-game difficulty</h2><p class="note">Pick a team to see how hard every 5-game stretch of its remaining schedule is. ' +
      'Bars above the line are harder than an average team\'s run; below are easier.</p><label class="sc-sel">Team <select id="scTeam">' + opts + "</select></label>";
    if (!t || !t.roll.length) return out + '<p class="note">Fewer than 5 games left for this team.</p>';
    var r = t.roll, W = 640, H = 170, pad = 46, max = Math.max.apply(null, r.map(Math.abs).concat([1]));
    var bw = (W - pad * 2) / r.length, mid = H / 2, bars = "", lab = "";
    r.forEach(function (v, i) {
      var h = Math.abs(v) / max * (mid - 18), y = v >= 0 ? mid - h : mid;
      var cls = v > max * 0.33 ? "hard" : v < -max * 0.33 ? "easy" : "mid";
      bars += '<rect class="rb ' + cls + '" x="' + (pad + i * bw + 1) + '" y="' + y.toFixed(1) + '" width="' + Math.max(1, bw - 2).toFixed(1) + '" height="' + Math.max(1, h).toFixed(1) +
        '"><title>Games ' + (i + 1) + "–" + (i + 5) + ": " + sg(v, 2) + " " + d.unit + " vs an average run</title></rect>";
    });
    lab = '<text x="' + pad + '" y="' + (H - 4) + '" class="rl">next 5</text><text x="' + (W - pad) + '" y="' + (H - 4) + '" class="rl" text-anchor="end">last 5</text>' +
      '<text x="4" y="' + (mid - 8) + '" class="rl">harder</text><text x="4" y="' + (mid + 16) + '" class="rl">easier</text>';
    return out + '<svg class="sc-roll" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Rolling 5-game difficulty for ' + esc(t.name) + '"><line x1="' + pad + '" x2="' + (W - pad) + '" y1="' + mid +
      '" y2="' + mid + '" class="rz"/>' + bars + lab + "</svg>";
  }

  function method(d) {
    var terms = d.terms.length ? d.terms.map(function (x) { return x === "short" ? "short rest (" + d.short_days + " day" + (d.short_days === 1 ? "" : "s") + " or fewer between games): " + sg(d.b_short, 2) + " " + d.unit
      : "long rest (" + d.long_days + "+ days): " + sg(d.b_long, 2) + " " + d.unit; }).join("; ") : "none (rest did not improve forecasts in testing)";
    return '<details class="sc-method"><summary>How this is calculated</summary><ul>' +
      "<li><b>Game difficulty:</b> the margin an average team would be expected to lose by against that opponent, in that venue and rest situation. Opponent strength is the same rating the Futures page simulates with.</li>" +
      "<li><b>Home advantage:</b> " + sg(d.hfa, 2) + " " + d.unit + ". <b>Rest terms kept:</b> " + terms + ". Travel distance was tested and dropped because it did not improve forecasts.</li>" +
      "<li><b>Schedule effect:</b> wins gained or lost compared with a coin-flip schedule (positive is easier). The 0–10 score ranks teams by average difficulty over the window (10 is hardest).</li>" +
      "<li><b>Projected wins:</b> wins so far plus the team's own win chance in each remaining game. The Futures page runs a full simulation, so totals can differ a little.</li>" +
      "<li><b>Tested on</b> " + esc(d.tuned_on) + " results; the last five seasons were held out. Win chances use a normal margin model with a spread of " + d.sd.toFixed(1) + " " + d.unit + ".</li>" +
      "<li><b>Not included:</b> injuries, rest-day travel, weather, and rating changes during the window.</li></ul></details>";
  }

  function render() {
    var d = state.d, h = "";
    if (d.recap) {
      h += '<p class="note sc-banner">The ' + esc(d.season) + ' season is finished and the next fixture is not out yet, so this shows how hard each team\'s completed ' + esc(d.season) +
        ' schedule was. The next-5 and next-10 view appears automatically once the new fixture is published.</p>';
      var list = d.teams.slice().sort(function (a, b) { return b.past_diff - a.past_diff; });
      h += '<h2 class="sc-h">' + esc(d.season) + " schedule faced</h2><div class=\"scroll\"><table class=\"stbl sc-tbl\"><thead><tr><th scope=\"col\">Team</th><th scope=\"col\">Difficulty<small>0 easy – 10 hard</small></th>" +
        "<th scope=\"col\">Schedule effect<small>wins</small></th><th scope=\"col\">Rating now<small>vs league</small></th></tr></thead><tbody>" +
        list.map(function (t) {
          return "<tr><td>" + esc(t.name) + '</td><td data-v="' + t.past_score + '"><span class="sc-bar"><i style="width:' + (t.past_score * 10) + '%" class="s' + Math.min(5, Math.floor(t.past_score / 2) + 1) + '"></i></span> <b>' +
            t.past_score.toFixed(1) + "</b></td><td>" + sg(-t.past_eff, 2) + "</td><td>" + sg(t.rating, 2) + "</td></tr>";
        }).join("") + "</tbody></table></div>" + method(d);
      root.innerHTML = h;
      return;
    }
    h += '<div class="sc-ctrl"><span class="sc-lab">Window</span><div class="seg" role="group" aria-label="Window">' +
      Object.keys(WIN).map(function (k) { return '<button type="button" data-w="' + k + '" aria-pressed="' + (k === state.win) + '">' + WIN[k] + "</button>"; }).join("") + "</div></div>";
    h += cards(d) + ticker(d) + table(d) + rolling(d) + method(d);
    root.innerHTML = h;
  }

  root.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-w]");
    if (b) { state.win = b.getAttribute("data-w"); store("sched.win", state.win); render(); return; }
    var th = e.target.closest("th[data-k]");
    if (th) { sortBy(th.getAttribute("data-k")); return; }
    var p = e.target.closest(".sc-pick");
    if (p) { state.team = p.getAttribute("data-team"); render(); var el = document.getElementById("scTeam"); if (el) el.scrollIntoView({ block: "center" }); }
  });
  root.addEventListener("keydown", function (e) {
    var th = e.target.closest && e.target.closest("th[data-k]");
    if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); sortBy(th.getAttribute("data-k")); }
  });
  root.addEventListener("change", function (e) {
    if (e.target.id === "scTeam") { state.team = e.target.value; render(); }
  });
  function sortBy(k) {
    var s = state.sort.k ? state.sort : DEFAULT_SORT;
    var col = COLS.filter(function (c) { return c.k === k; })[0];
    state.sort = { k: k, dir: s.k === k ? -s.dir : (col && col.txt ? 1 : (k === "score" || k === "opp" ? -1 : -1)) };
    render();
  }

  fetch(SRC, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    state.d = d;
    var w = store("sched.win");
    if (w && WIN[w]) state.win = w;
    var first = d.teams.slice().sort(function (a, b) { return a.name.localeCompare(b.name); })[0];
    state.team = first ? first.team : null;
    render();
  }).catch(function (e) {
    root.innerHTML = '<p class="note">Schedule data is not available yet (' + esc(e.message) + "). It appears after the next refresh.</p>";
  });
})();
