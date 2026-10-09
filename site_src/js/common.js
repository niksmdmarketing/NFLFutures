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
