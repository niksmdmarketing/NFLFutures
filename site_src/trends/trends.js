/* Winner trends page (shared by NFL, NBA, NHL, NBL). Reads data/trends.json. */
(function () {
  "use strict";
  var root = document.getElementById("trends");
  if (!root) return;
  var SRC = root.getAttribute("data-src") || "data/trends.json";

  var VERDICT = {
    edge: { name: "Beats the record", cls: "v-edge", blurb: "Teams with this did better than their record said, in both halves of the history. Worth checking against the price." },
    fade: { name: "Worse than the record", cls: "v-fade", blurb: "Teams with this did worse than their record said, in both halves of the history. A reason to be wary of them." },
    priced: { name: "Real but priced", cls: "v-priced", blurb: "A genuine pattern, but it mostly reflects a good record, which the market already prices." },
    weak: { name: "Unproven", cls: "v-weak", blurb: "Points the same way in both halves of the history, but there is not yet enough evidence to rule out chance." },
    noise: { name: "Noise", cls: "v-noise", blurb: "Failed the tests. Ignore it, however often it gets quoted." }
  };
  var WHEN = { end: "End of regular season", prior: "Before the season", pre: "Weeks 1-4", q: "Quarter mark", h: "Halfway" };
  var state = { data: null, sec: 0, sort: {} };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pc(x, d) { return x == null ? "–" : (100 * x).toFixed(d == null ? 0 : d) + "%"; }
  function lift(r) {
    if (r.rate_with == null || r.rate_without == null) return null;
    if (!r.rate_without) return r.rate_with ? Infinity : null;
    return r.rate_with / r.rate_without;
  }
  function liftTxt(r) {
    var l = lift(r);
    if (l == null) return "–";
    if (l === Infinity) return "only these";
    return l.toFixed(1) + "×";
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  function nowCell(r, d) {
    if (r.now == null) return '<span class="muted" title="Not known yet this season">not yet</span>';
    if (!r.now.length) return '<span class="muted">none</span>';
    var so = r.timing === "end" ? ' <small title="Based on the season so far">so far</small>' : "";
    return esc(r.now.join(", ")) + so;
  }

  function header(d) {
    var counts = { edge: 0, fade: 0, priced: 0, weak: 0, noise: 0 };
    d.sections.forEach(function (s) { s.trends.forEach(function (r) { counts[r.verdict]++; }); });
    var legend = Object.keys(VERDICT).map(function (k) {
      return '<div class="tr-leg"><span class="tr-badge ' + VERDICT[k].cls + '">' + VERDICT[k].name + '</span><span class="tr-n">' + counts[k] +
        '</span><p>' + VERDICT[k].blurb + "</p></div>";
    }).join("");
    function group(kind, label) {
      var b = d.sections.map(function (s, i) {
        if ((s.kind || "team") !== kind) return "";
        return '<button type="button" data-sec="' + i + '" aria-pressed="' + (i === state.sec) + '">' + esc(s.title) + "</button>";
      }).join("");
      return b ? '<div class="tr-tabs"><span class="tr-tablab">' + label + '</span><div class="seg" role="group" aria-label="' + label + '">' + b + "</div></div>" : "";
    }
    return '<section class="tr-legend" aria-label="How to read the verdicts">' + legend + "</section>" +
      group("team", "Team markets") + group("award", "Awards") + '<div id="trSec"></div>';
  }

  function card(r, s) {
    var v = VERDICT[r.verdict];
    var review = r.review ? '<p class="tr-review">' + esc(r.review) + "</p>" : "";
    var exp = r.expected_with, big;
    if (exp != null && r.pool_with) {
      big = '<div class="tr-big"><b>' + pc(r.winners_with / r.pool_with) + '</b> <span>actual</span> <b class="muted">' +
        pc(exp / r.pool_with) + "</b> <span>their " + esc(r.base_word || "records") + " predicted</span></div>";
    } else {
      big = '<div class="tr-big"><b>' + pc(r.rate_with) + "</b> <span>with it</span></div>";
    }
    return '<article class="tr-card ' + v.cls + '"><span class="tr-badge ' + v.cls + '">' + v.name + "</span>" +
      "<h3>" + esc(r.label) + "</h3>" + big +
      '<p class="note">' + r.pool_with + " of " + r.pool + " " + esc(s.pool_desc) + " had this and " + r.winners_with +
      (s.kind === "award" ? " won" : " succeeded") + (exp != null ? " (about " + Math.round(exp) + " expected from their " + esc(r.base_word || "records") + ")" : "") +
      ". The gap held in both halves of the history.</p>" + review +
      '<p class="tr-now"><span>Fits now</span> ' + nowCell(r, s) + '</p><p class="tr-when">Known: ' + WHEN[r.timing] + "</p></article>";
  }

  var COLS = [
    { k: "label", l: "Trend", t: "text" },
    { k: "verdict", l: "Verdict", t: "verdict" },
    { k: "timing", l: "Known", t: "when" },
    { k: "winners_with", l: "Winners with it", t: "frac" },
    { k: "rate_with", l: "Win rate with", t: "pct" },
    { k: "rate_without", l: "Without", t: "pct" },
    { k: "lift", l: "× as likely", t: "lift" },
    { k: "recent_with", l: "Last 10 winners", t: "recent" },
    { k: "now", l: "Fits now", t: "now" }
  ];

  function val(r, c) {
    if (c.k === "lift") { var l = lift(r); return l == null ? -1 : (l === Infinity ? 1e9 : l); }
    if (c.k === "winners_with") return r.winners ? r.winners_with / r.winners : -1;
    if (c.k === "recent_with") return r.recent ? r.recent_with / r.recent : -1;
    if (c.k === "verdict") return ["edge", "fade", "priced", "weak", "noise"].indexOf(r.verdict);
    if (c.k === "now") return r.now ? r.now.length : -1;
    var x = r[c.k];
    return x == null ? -1 : x;
  }

  function cell(r, c, s) {
    switch (c.t) {
      case "text": return '<td class="txt tr-label">' + esc(r.label) + (r.verdict === "noise" ? '<small class="tr-why">' + esc(r.why) + "</small>" : "") + "</td>";
      case "verdict": return '<td><span class="tr-badge ' + VERDICT[r.verdict].cls + '">' + VERDICT[r.verdict].name + "</span></td>";
      case "when": return "<td>" + WHEN[r.timing] + "</td>";
      case "frac": return "<td>" + r.winners_with + "/" + r.winners + "</td>";
      case "pct": return "<td>" + pc(r[c.k]) + "</td>";
      case "lift": return "<td>" + liftTxt(r) + "</td>";
      case "recent": return "<td>" + (r.recent ? r.recent_with + "/" + r.recent : "–") + "</td>";
      case "now": return '<td class="txt">' + nowCell(r, s) + "</td>";
    }
    return "<td></td>";
  }

  function table(rows, s, id) {
    var sort = state.sort[id] || { k: null, dir: -1 };
    var list = rows.slice();
    if (sort.k) {
      var c = COLS.filter(function (x) { return x.k === sort.k; })[0];
      list.sort(function (a, b) {
        var va = val(a, c), vb = val(b, c);
        if (typeof va === "string") return sort.dir * va.localeCompare(vb);
        return sort.dir * (va - vb);
      });
    }
    var head = COLS.map(function (c) {
      var as = sort.k === c.k ? (sort.dir > 0 ? "ascending" : "descending") : "none";
      return '<th scope="col" data-k="' + c.k + '" aria-sort="' + as + '" tabindex="0">' + c.l + "</th>";
    }).join("");
    var body = list.map(function (r) {
      return "<tr>" + COLS.map(function (c) { return cell(r, c, s); }).join("") + "</tr>";
    }).join("");
    return '<div class="scroll"><table class="stbl tr-tbl" data-id="' + id + '"><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  function section() {
    var d = state.data, s = d.sections[state.sec];
    var act = s.trends.filter(function (r) { return r.verdict === "edge" || r.verdict === "fade"; });
    var mid = s.trends.filter(function (r) { return r.verdict === "priced" || r.verdict === "weak"; });
    var noise = s.trends.filter(function (r) { return r.verdict === "noise"; });
    var html = '<section class="tr-sec"><div class="table-head"><h2>' + esc(s.title) + "</h2></div>" +
      '<p class="note">' + s.n_seasons + " completed seasons (" + esc(s.seasons[0]) + " to " + esc(s.seasons[1]) + "). Compared against all " +
      esc(s.pool_desc) + " in those seasons (" + s.pool + "). " + (s.kind === "award" ? "A typical candidate in that pool won " : "A typical team in that pool succeeded ") + pc(s.base_rate) + " of the time. " + esc(s.note || "") +
      (d.current ? " “Fits now” refers to " + esc(d.current) + "." : "") + "</p>";
    html += "<h3 class=\"tr-h\">Worth acting on</h3>";
    html += act.length ? '<div class="tr-cards">' + act.map(function (r) { return card(r, s); }).join("") + "</div>"
      : '<p class="note tr-empty">' + (s.kind === "award" ? "Nothing here matters beyond the main production numbers once the noise is removed. Follow the leading candidates and let the price decide." : "Nothing in this market beats the record once the noise is removed. Back the best teams and let the price decide.") + "</p>";
    html += '<h3 class="tr-h">' + (mid.some(function (r) { return r.verdict === "priced"; }) ? "Real but priced, and unproven" : "Unproven patterns") + "</h3>";
    html += mid.length ? table(mid, s, "mid" + state.sec) : '<p class="note tr-empty">No pattern here passed the tests. Results in this market have been close to random once you know who made the pool.</p>';
    html += '<details class="tr-noise"><summary>Noise: ignore these (' + noise.length + ")</summary>" +
      '<p class="note">Each of these failed at least one test: too few cases, gone or reversed in one half of the history, or a gap within what chance produces.</p>' +
      table(noise, s, "noise" + state.sec) + "</details>";
    html += '<details class="tr-winners"><summary>Past winners (' + s.winners.length + ")</summary><ul>" +
      s.winners.map(function (w) { return "<li><b>" + esc(w[1]) + "</b> " + esc(w[2]) + "</li>"; }).join("") + "</ul></details>";
    html += "</section>";
    document.getElementById("trSec").innerHTML = html;
  }

  function method(d) {
    return '<section class="method"><div><h2>How the noise is filtered</h2><ul>' +
      "<li>Every pattern is checked against every other team in the same pool, not just the winners, using Fisher's exact test.</li>" +
      "<li>Because dozens of patterns are tested per market, the false-discovery rate is capped at " + Math.round(d.fdr * 100) + "% (Benjamini-Hochberg).</li>" +
      "<li>A pattern must point the same way in the earlier and later halves of the history. One-era wonders are thrown out.</li>" +
      "<li>Patterns that need fewer than " + d.min_pool + " teams to have them, or fewer than " + d.min_pool + " not to, are too rare to judge.</li>" +
      "</ul></div><div><h2>Beats the record?</h2><ul>" +
      "<li>Record is the first thing every price reflects. Each pattern is re-tested at the same record (the record at that point of the season, or last season's record for pre-season items) using a conditional logit, with its own false-discovery cap and the same two-halves rule. For awards the yardstick is the candidate's main production number instead of a record.</li>" +
      "<li>Only patterns that survive that are flagged as beating (or falling short of) the record. A further plausibility review with TypeSafe downgrades findings that look like small-sample streaks.</li>" +
      "<li>Markets know more than the record, so even these are prompts to check the price, not proof of value.</li>" +
      "</ul></div></section>";
  }

  function wire() {
    root.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-sec]");
      if (b) {
        state.sec = +b.getAttribute("data-sec");
        store("trends-sec-" + state.data.sport, String(state.sec));
        root.querySelectorAll("button[data-sec]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        section();
        return;
      }
      var th = e.target.closest("th[data-k]");
      if (th) sortBy(th);
    });
    root.addEventListener("keydown", function (e) {
      var th = e.target.closest && e.target.closest("th[data-k]");
      if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); sortBy(th); }
    });
  }

  function sortBy(th) {
    var id = th.closest("table").getAttribute("data-id"), k = th.getAttribute("data-k");
    var cur = state.sort[id] || {};
    var openNoise = !!root.querySelector(".tr-noise[open]");
    state.sort[id] = { k: k, dir: cur.k === k ? -cur.dir : (k === "label" || k === "verdict" ? 1 : -1) };
    section();
    if (openNoise) { var n = root.querySelector(".tr-noise"); if (n) n.open = true; }
  }

  fetch(SRC, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    state.data = d;
    var saved = +store("trends-sec-" + d.sport);
    if (saved >= 0 && saved < d.sections.length) state.sec = saved;
    root.innerHTML = header(d) + method(d);
    root.insertBefore(document.getElementById("trSec") || document.createElement("div"), root.querySelector(".method"));
    section();
    wire();
    var st = document.getElementById("stamp");
    if (st && d.updated_utc) st.textContent = "Updated " + new Date(d.updated_utc.replace("+00:00", "Z")).toLocaleString();
  }).catch(function (e) {
    root.innerHTML = '<p class="note">Trend data is not available yet (' + esc(e.message) + ").</p>";
  });
})();
