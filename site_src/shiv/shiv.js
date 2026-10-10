/* Shiv Value Models page. Reads data/live.json. */
(function () {
  "use strict";
  var app = document.getElementById("app"), tabs = document.getElementById("tabs");
  var SPORTS = [["nfl", "NFL"], ["nba", "NBA"], ["nhl", "NHL"], ["afl", "AFL"], ["nbl", "NBL"]];
  var state = { d: null, sport: "nfl" };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pc(p) { return p == null ? "–" : p < 0.005 ? "<1%" : p > 0.995 ? ">99%" : (p * 100).toFixed(p < 0.1 ? 1 : 0) + "%"; }
  function cents(p) { return p == null ? "–" : (p * 100).toFixed(1); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  function marketTable(m, solo) {
    var rows = m.rows.map(function (r) {
      var g = r.model - r.market, big = Math.abs(g) >= 0.05;
      return "<tr><td class=\"sv-team\">" + esc(r.name) + "</td><td>" + pc(r.model) + "</td><td>" + pc(r.market) + "</td><td>" + pc(r.shiv) + "</td>" +
        '<td class="gap' + (big ? " big" : "") + '" data-v="' + g + '">' + (g >= 0 ? "+" : "−") + Math.abs(g * 100).toFixed(1) + (big ? '<span class="sv-flag" title="Large disagreement: check news before reading anything into it">check</span>' : "") + "</td>" +
        '<td class="q" title="Best bid / best ask in cents per $1 share">' + cents(r.bid) + " / " + cents(r.ask) + "</td></tr>";
    }).join("");
    var fee = m.fee && m.fee.rate ? "Taker fee rate " + (m.fee.rate * 100).toFixed(1) + "% (applied to the trade, on top of the ask). " : "";
    return '<div class="sv-card">' + (solo ? "" : "<h3>" + esc(m.label) + "</h3>") + '<div class="scroll"><table class="stbl sv-tbl"><thead><tr><th scope="col">Team</th><th scope="col">Our model</th><th scope="col">Market</th><th scope="col">Shiv</th><th scope="col">Model − market<small>pts</small></th><th scope="col">Bid / ask<small>¢</small></th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" + (fee || !m.one_winner ? '<p class="sv-note">' + fee + (m.one_winner ? "" : "Yes/no market per team: market is the midpoint as quoted; Shiv averages the two in log-odds.") + "</p>" : "") + "</div>";
  }

  var BT = {
    nfl: [["div", "Division winner"], ["playoff", "Make the playoffs"], ["conf", "Conference champion"], ["sb", "Super Bowl"]],
    nba: [["title", "NBA title"], ["conf", "Conference champion"]],
    nhl: [["cup", "Stanley Cup"], ["conf", "Conference champion"]]
  };
  var STAGE = { nfl: { wk0: "Before week 1", wk4: "After week 4", wk9: "After week 9", wk13: "After week 13" },
                nba: { "0%": "Before the season", "20%": "20% played", "40%": "40%", "60%": "60%", "80%": "80%" } };

  function backtest(sport) {
    var B = state.d.backtest && state.d.backtest[sport];
    if (!B) return "";
    var rows = "";
    Object.keys(B).forEach(function (k) {
      var v = B[k];
      if (!v || v.model == null) return;
      var parts = k.split(" "), mk = parts[0], st = parts.slice(1).join(" ");
      var label = (BT[sport].filter(function (x) { return x[0] === mk; })[0] || [mk, mk])[1];
      var stage = sport === "nhl" ? st.replace(/(\d{4}) N0/, "$1-" + "start").replace(/(\d{4}) N20/, "$1 after 20 games").replace("-start", " season start") : ((STAGE[sport] || {})[st] || st);
      if (sport === "nhl") stage = st.replace(/(\d{4}) N0/, function (_, y) { return y + "-" + (+y + 1 + "").slice(2) + ", season start"; }).replace(/(\d{4}) N20/, function (_, y) { return y + "-" + (+y + 1 + "").slice(2) + ", after 20 games"; });
      var vals = [["model", v.model], ["market", v.market], ["shiv", v.blend]];
      var best = vals.reduce(function (a, b) { return b[1] < a[1] ? b : a; })[0];
      rows += "<tr><td>" + esc(label) + "</td><td>" + esc(stage) + "</td>" + vals.map(function (x) {
        return '<td class="' + (x[0] === best ? "sv-best" : "") + '">' + x[1].toFixed(3) + "</td>";
      }).join("") + "<td>" + (v.events || v.teams || "") + (v.metric === "brier" ? " teams" : "") + "</td></tr>";
    });
    return '<h2 class="sv-h">Back-test on past seasons</h2><p class="sv-note">Each column scored at the same dates on past seasons (' + (sport === "nfl" ? "2024 and 2025" : sport === "nba" ? "2024-25 and 2025-26" : "2024-25 and 2025-26") +
      "), using only what was known at the time, against what actually happened. Score = average penalty for the probability given to the eventual winner (yes/no rows: Brier score per team). <b>Lower is better</b>; the best of the three is bold. Market history is one price per day, and these are only one or two seasons, so read it as a first look, not proof.</p>" +
      '<div class="scroll"><table class="stbl sv-score"><thead><tr><th scope="col">Market</th><th scope="col">When</th><th scope="col">Our model</th><th scope="col">Market</th><th scope="col">Shiv</th><th scope="col">Races</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }

  function forward(sport) {
    var F = (state.d.forward || {})[sport];
    var h = '<h2 class="sv-h">This season, forecasts made in real time</h2>';
    if (!F || !Object.keys(F).length) return h + '<p class="sv-note">Every refresh saves all three columns together with the live quote (bid, ask, spread, liquidity, fees, time). Nothing has settled yet, so there is no score: the first results arrive when division races and playoff places are decided. This is the test that counts.</p>';
    var rows = Object.keys(F).map(function (k) {
      var v = F[k], vals = [["model", v.model], ["market", v.market], ["shiv", v.shiv]].filter(function (x) { return x[1] != null; });
      var best = vals.length ? vals.reduce(function (a, b) { return b[1] < a[1] ? b : a; })[0] : null;
      return "<tr><td>" + esc(k) + "</td>" + vals.map(function (x) { return '<td class="' + (x[0] === best ? "sv-best" : "") + '">' + x[1].toFixed(3) + "</td>"; }).join("") + "<td>" + v.forecasts + "</td></tr>";
    }).join("");
    return h + '<p class="sv-note">Scored only on forecasts saved before the result was known (last record of each day). Same scores as below: lower is better; yes/no markets use the Brier score.</p><div class="scroll"><table class="stbl sv-score"><thead><tr><th scope="col">Market</th><th scope="col">Our model</th><th scope="col">Market</th><th scope="col">Shiv</th><th scope="col">Daily forecasts scored</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }

  function render() {
    tabs.innerHTML = SPORTS.map(function (s) { return '<a href="#' + s[0] + '"' + (s[0] === state.sport ? ' aria-current="page"' : "") + ">" + s[1] + "</a>"; }).join("");
    var S = state.d.sports[state.sport];
    if (!S) {
      app.innerHTML = '<p class="note sv-note">No prediction-market coverage for the ' + state.sport.toUpperCase() + ": Polymarket does not list " + state.sport.toUpperCase() +
        " futures, so only our model exists here (see the sport's Futures page). Australian bookmaker prices could be added later as a separate benchmark.</p>";
      return;
    }
    var groups = {}, order = [];
    S.markets.forEach(function (m) { var g = m.group || m.label; if (!groups[g]) { groups[g] = []; order.push(g); } groups[g].push(m); });
    var h = '<p class="sv-note">Market quotes at ' + new Date(state.d.updated_utc).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) +
      ". \"Check\" marks a gap of 5 points or more between our model and the market: a prompt to look for injuries, trades or other news, not a value label.</p>";
    order.forEach(function (g) {
      var solo = groups[g].length === 1;
      h += '<h2 class="sv-h">' + esc(g) + '</h2><div class="' + (solo ? "sv-solo" : "sv-grid") + '">' + groups[g].map(function (m) { return marketTable(m, solo); }).join("") + "</div>";
    });
    h += forward(state.sport) + backtest(state.sport);
    app.innerHTML = h;
    if (window.sortableTable) document.querySelectorAll("#app table").forEach(window.sortableTable);
  }

  function route() {
    var s = (location.hash || "").replace("#", "");
    state.sport = SPORTS.some(function (x) { return x[0] === s; }) ? s : (store("shiv.sport") || "nfl");
    store("shiv.sport", state.sport);
    if (state.d) render();
  }
  window.addEventListener("hashchange", route);
  fetch("data/live.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    state.d = d;
    document.getElementById("stamp").textContent = "Updated " + new Date(d.updated_utc).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    route();
    render();
  }).catch(function (e) { app.innerHTML = '<p class="note">Not available yet (' + esc(e.message) + ").</p>"; });
})();
