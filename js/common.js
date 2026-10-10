/* Shared helpers: data loading, formatting, team names, update stamp. */
const NAMES = {ARI:"Arizona Cardinals",ATL:"Atlanta Falcons",BAL:"Baltimore Ravens",BUF:"Buffalo Bills",CAR:"Carolina Panthers",CHI:"Chicago Bears",CIN:"Cincinnati Bengals",CLE:"Cleveland Browns",DAL:"Dallas Cowboys",DEN:"Denver Broncos",DET:"Detroit Lions",GB:"Green Bay Packers",HOU:"Houston Texans",IND:"Indianapolis Colts",JAX:"Jacksonville Jaguars",KC:"Kansas City Chiefs",LA:"Los Angeles Rams",LAC:"Los Angeles Chargers",LV:"Las Vegas Raiders",MIA:"Miami Dolphins",MIN:"Minnesota Vikings",NE:"New England Patriots",NO:"New Orleans Saints",NYG:"New York Giants",NYJ:"New York Jets",PHI:"Philadelphia Eagles",PIT:"Pittsburgh Steelers",SEA:"Seattle Seahawks",SF:"San Francisco 49ers",TB:"Tampa Bay Buccaneers",TEN:"Tennessee Titans",WAS:"Washington Commanders"};
const DIVS = {"AFC East":["BUF","MIA","NE","NYJ"],"AFC North":["BAL","CIN","CLE","PIT"],"AFC South":["HOU","IND","JAX","TEN"],"AFC West":["DEN","KC","LV","LAC"],"NFC East":["DAL","NYG","PHI","WAS"],"NFC North":["CHI","DET","GB","MIN"],"NFC South":["ATL","CAR","NO","TB"],"NFC West":["ARI","LA","SEA","SF"]};
const nm = t => NAMES[t] || t;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = p => p == null ? "–" : p < 0.005 ? "<1%" : p > 0.995 ? ">99%" : Math.round(p * 100) + "%";
const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"], MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(date) {
  const [y, m, d] = date.split("-").map(Number);
  return DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] + " " + d + " " + MONTHS[m - 1];
}
function fmtVal(v, fmt) {
  if (v == null || (typeof v === "number" && !isFinite(v))) return "–";
  switch (fmt) {
    case "pct": return (v * 100).toFixed(1) + "%";
    case "num1": return v.toFixed(1);
    case "num2": return v.toFixed(2);
    case "num3": return v.toFixed(3);
    case "int": return Math.round(v).toString();
    default: return esc(v);
  }
}
async function getJSON(name) {
  const r = await fetch("data/" + name, {cache: "no-cache"});
  if (!r.ok) throw new Error("Could not load " + name + " (" + r.status + ")");
  return r.json();
}
function stamp(meta) {
  let when = meta.updated_utc;
  try {
    when = new Date(meta.updated_utc).toLocaleString(undefined, {weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"});
  } catch (e) {}
  let games = meta.through_week ? "games through Week " + meta.through_week : "preseason";
  if (meta.next_week_played) games += " + " + meta.next_week_played + (meta.next_week_played === 1 ? " game" : " games") + " of Week " + meta.next_week;
  const bits = [meta.season + " season", games];
  if (meta.injury_week) bits.push("Week " + meta.injury_week + " injury report");
  bits.push("updated " + when);
  $("stamp").textContent = bits.join(" · ");
}
async function boot(fn) {
  try {
    const meta = await getJSON("meta.json");
    stamp(meta);
    await fn(meta);
  } catch (e) {
    console.error(e);
    const m = $("main");
    const div = document.createElement("p");
    div.className = "err";
    div.textContent = "Something went wrong loading this page: " + e.message;
    m.insertBefore(div, m.children[1] || null);
  }
}

/* Ranked-table helpers shared by the stat pages. */
function rankMap(rows, key, dir) {
  const vals = rows.map(r => r[key]).filter(v => typeof v === "number" && isFinite(v));
  const sorted = [...vals].sort((a, b) => dir === "low" ? a - b : b - a);
  const m = new Map();
  rows.forEach(r => { const v = r[key]; if (typeof v === "number" && isFinite(v)) m.set(r.team, sorted.indexOf(v) + 1); });
  return {m, n: vals.length};
}
function qClass(rank, n) {
  if (!rank || n < 5) return "";
  const q = Math.min(5, Math.floor((rank - 1) / n * 5) + 1);
  return q === 3 ? "" : "q" + q;
}
function sortRows(rows, key, dir, getter) {
  return [...rows].sort((a, b) => {
    const x = getter(a, key), y = getter(b, key);
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
  });
}
function fmtDelta(d, fmt) {
  if (d == null || !isFinite(d)) return "–";
  const sign = d > 0 ? "+" : d < 0 ? "−" : "";
  const a = Math.abs(d);
  if (fmt === "pct") return sign + (a * 100).toFixed(1);
  if (fmt === "num3") return sign + a.toFixed(3);
  if (fmt === "num2") return sign + a.toFixed(2);
  if (fmt === "int") return sign + Math.round(a);
  return sign + a.toFixed(1);
}


/* Click-to-sort for plain HTML tables. Cells may carry data-v (numeric sort value); otherwise text is used.
   Click cycles: highest first -> lowest first -> original order (group header rows return with it). */
function sortableTable(table) {
  if (!table || table.dataset.sortable) return;
  table.dataset.sortable = "1";
  const thead = table.tHead, tbody = table.tBodies[0];
  const ths = [...thead.rows[thead.rows.length - 1].cells];
  let state = {i: -1, dir: 0};
  const original = () => [...tbody.rows];
  let orig = original();
  const obs = new MutationObserver(() => { orig = original(); state = {i: -1, dir: 0}; mark(); });
  obs.observe(tbody, {childList: true});
  const key = (tr, i) => {
    const td = tr.cells[i]; if (!td) return null;
    if (td.dataset.v !== undefined) { const n = parseFloat(td.dataset.v); return isNaN(n) ? null : n; }
    const t = td.textContent.trim(); const n = parseFloat(t.replace(/[%,+<>]/g, "").replace("−", "-"));
    return isNaN(n) || /[a-z]{2,}/i.test(t.replace(/^[<>]/, "")) ? t : n;
  };
  const mark = () => ths.forEach((th, j) => {
    if (j === state.i && state.dir) th.setAttribute("aria-sort", state.dir > 0 ? "ascending" : "descending");
    else th.removeAttribute("aria-sort");
  });
  ths.forEach((th, i) => {
    th.tabIndex = 0; th.style.cursor = "pointer"; th.title = th.title || "Sort";
    const go = () => {
      const numeric = orig.some(tr => !tr.classList.contains("divhead") && typeof key(tr, i) === "number");
      if (state.i !== i) state = {i, dir: numeric ? -1 : 1};
      else if (state.dir === (numeric ? -1 : 1)) state.dir = -state.dir;
      else state = {i: -1, dir: 0};
      if (!state.dir) { tbody.replaceChildren(...orig); }
      else {
        const data = orig.filter(tr => !tr.classList.contains("divhead"));
        data.sort((a, b) => {
          const x = key(a, i), y = key(b, i);
          if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
          return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * state.dir;
        });
        tbody.replaceChildren(...data);
      }
      obs.takeRecords();  // our own reordering is not a redraw
      mark();
    };
    th.addEventListener("click", go);
    th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
}
