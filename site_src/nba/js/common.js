const NAMES = {ATL:"Atlanta Hawks",BKN:"Brooklyn Nets",BOS:"Boston Celtics",CHA:"Charlotte Hornets",CHI:"Chicago Bulls",CLE:"Cleveland Cavaliers",DAL:"Dallas Mavericks",DEN:"Denver Nuggets",DET:"Detroit Pistons",GS:"Golden State Warriors",HOU:"Houston Rockets",IND:"Indiana Pacers",LAC:"LA Clippers",LAL:"Los Angeles Lakers",MEM:"Memphis Grizzlies",MIA:"Miami Heat",MIL:"Milwaukee Bucks",MIN:"Minnesota Timberwolves",NO:"New Orleans Pelicans",NY:"New York Knicks",OKC:"Oklahoma City Thunder",ORL:"Orlando Magic",PHI:"Philadelphia 76ers",PHX:"Phoenix Suns",POR:"Portland Trail Blazers",SA:"San Antonio Spurs",SAC:"Sacramento Kings",TOR:"Toronto Raptors",UTAH:"Utah Jazz",WSH:"Washington Wizards"};
document.querySelectorAll(".nav-simple").forEach(nav=>{if(!nav.querySelector('a[href="stats.html"]')){const link=document.createElement("a");link.href="stats.html";link.textContent="Stats";nav.insertBefore(link,nav.querySelector('a[href="ratings.html"]'));}});
document.querySelectorAll(".sportbar").forEach(bar=>{if(!bar.querySelector('a[href="../nbl/"]')){const link=document.createElement("a");link.href="../nbl/";link.textContent="NBL";bar.appendChild(link);}});
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = p => p == null ? "–" : p < .005 ? "<1%" : p > .995 ? ">99%" : Math.round(p * 100) + "%";
async function getJSON(name) {
  const r = await fetch("data/" + name, {cache:"no-cache"});
  if (!r.ok) throw new Error("Could not load " + name + " (" + r.status + ")");
  return r.json();
}
function stamp(meta) {
  let when = meta.updated_utc;
  try { when = new Date(meta.updated_utc).toLocaleString(undefined, {weekday:"short",day:"numeric",month:"short",hour:"numeric",minute:"2-digit"}); } catch(e) {}
  $("stamp").textContent = meta.season + " season · " + meta.games_played + " of " + meta.games_scheduled + " games played · updated " + when;
}
async function boot(fn) {
  try { const meta = await getJSON("meta.json"); stamp(meta); await fn(meta); }
  catch(e) { console.error(e); const p=document.createElement("p"); p.className="err"; p.textContent="Something went wrong loading this page: "+e.message; $("main").prepend(p); }
}
function pcell(p) { return '<td class="pc"><span class="bar" style="width:calc('+(Math.min(1,p)*100).toFixed(1)+'% - 8px)"></span><b>'+pct(p)+'</b></td>'; }
function setupSort(table, rows, render) {
  table.querySelectorAll("th[data-key]").forEach(th => th.addEventListener("click", () => {
    const key=th.dataset.key, numeric=th.dataset.type!=="text", current=th.getAttribute("aria-sort");
    table.querySelectorAll("th").forEach(x=>x.removeAttribute("aria-sort"));
    const dir=current==="descending"?1:-1; th.setAttribute("aria-sort",dir<0?"descending":"ascending");
    rows.sort((a,b)=>{const x=a[key],y=b[key]; return (numeric?(Number(x)-Number(y)):String(x).localeCompare(String(y)))*dir;}); render();
  }));
}
