const $ = id => document.getElementById(id);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

const labels = {
  team:"Team", opponent:"Opponent", player:"Player", player_id:"Player ID", season:"Season", season_type:"Phase",
  games:"GP", wins:"W", losses:"L", draws:"D", win_pct:"Win %", points_for:"Points for", points_against:"Points against",
  percentage:"Scoring percentage", points_for_pg:"Points for / game", points_against_pg:"Points against / game", margin_pg:"Margin / game",
  home_wins:"Home wins", away_wins:"Away wins", ladder_position:"Ladder pos.", minor_premier:"Minor premier", premiership:"Premiers",
  finals_wins:"Finals wins", finals_stage:"Finals stage", date:"Date", round:"Round", venue:"Venue", attendance:"Attendance",
  home_away:"Home / away", result:"Result", margin:"Margin", home_team:"Home team", away_team:"Away team", home_score:"Home score", away_score:"Away score",
  age:"Age", career_games:"Career games", brownlow_votes:"Brownlow votes", scoring_accuracy_pct:"Scoring accuracy %",
  kicks:"Kicks", kicks_pg:"Kicks / game", marks:"Marks", marks_pg:"Marks / game", handballs:"Handballs", handballs_pg:"Handballs / game",
  disposals:"Disposals", disposals_pg:"Disposals / game", goals:"Goals", goals_pg:"Goals / game", behinds:"Behinds", behinds_pg:"Behinds / game",
  hitouts:"Hit-outs", hitouts_pg:"Hit-outs / game", tackles:"Tackles", tackles_pg:"Tackles / game", rebound_50s:"Rebound 50s", rebound_50s_pg:"Rebound 50s / game",
  inside_50s:"Inside 50s", inside_50s_pg:"Inside 50s / game", clearances:"Clearances", clearances_pg:"Clearances / game", clangers:"Clangers", clangers_pg:"Clangers / game",
  free_kicks_for:"Free kicks for", free_kicks_for_pg:"Free kicks for / game", free_kicks_against:"Free kicks against", free_kicks_against_pg:"Free kicks against / game",
  contested_possessions:"Contested possessions", contested_possessions_pg:"Contested possessions / game", uncontested_possessions:"Uncontested possessions", uncontested_possessions_pg:"Uncontested possessions / game",
  contested_marks:"Contested marks", contested_marks_pg:"Contested marks / game", marks_inside_50:"Marks inside 50", marks_inside_50_pg:"Marks inside 50 / game",
  one_percenters:"One-percenters", one_percenters_pg:"One-percenters / game", bounces:"Bounces", bounces_pg:"Bounces / game", goal_assists:"Goal assists", goal_assists_pg:"Goal assists / game",
  time_on_ground:"Time on ground (min)", score_involvements:"Score involvements", score_involvements_pg:"Score involvements / game",
  metres_gained:"Metres gained", metres_gained_pg:"Metres gained / game", intercepts:"Intercepts", intercepts_pg:"Intercepts / game",
  turnovers:"Turnovers", turnovers_pg:"Turnovers / game", centre_clearances:"Centre clearances", centre_clearances_pg:"Centre clearances / game",
  stoppage_clearances:"Stoppage clearances", stoppage_clearances_pg:"Stoppage clearances / game", tackles_inside_50:"Tackles inside 50", tackles_inside_50_pg:"Tackles inside 50 / game",
  effective_disposals:"Effective disposals", effective_disposals_pg:"Effective disposals / game", disposal_efficiency_pct:"Disposal efficiency %",
  disposal_efficiency_pct_pg:"Disposal efficiency %", time_on_ground_pct:"Time on ground %", afl_fantasy_points:"AFL Fantasy points", afl_fantasy_points_pg:"AFL Fantasy / game",
  supercoach_points:"SuperCoach points", supercoach_points_pg:"SuperCoach / game", q1_for:"Q1 for", q1_against:"Q1 against", q2_for:"Q2 for", q2_against:"Q2 against",
  q3_for:"Q3 for", q3_against:"Q3 against", q4_for:"Q4 for", q4_against:"Q4 against", points_for:"Score", points_against:"Opp. score", match_id:"Source match ID",
  is_final:"Finals match", award:"Award indicator", value:"Value", unit:"Unit"
};

const views = {
  team_seasons:{label:"Team season profiles",key:"team_seasons",groups:{results:["team","games","wins","losses","draws","win_pct","points_for","points_against","percentage","margin_pg","home_wins","away_wins","ladder_position","minor_premier","finals_wins","finals_stage","premiership"],
    team_stats:["team","games","disposals_pg","kicks_pg","handballs_pg","marks_pg","goals_pg","tackles_pg","inside_50s_pg","clearances_pg","contested_possessions_pg","uncontested_possessions_pg","rebound_50s_pg","goal_assists_pg"],
    advanced:["team","games","score_involvements_pg","metres_gained_pg","intercepts_pg","turnovers_pg","disposal_efficiency_pct_pg","centre_clearances_pg","stoppage_clearances_pg","tackles_inside_50_pg","contested_marks_pg","marks_inside_50_pg"]}},
  team_games:{label:"Team game log",key:"team_games",groups:{results:["date","round","team","opponent","home_away","result","points_for","points_against","margin","venue","q1_for","q1_against","q2_for","q2_against","q3_for","q3_against","q4_for","q4_against"],
    team_stats:["date","round","team","opponent","result","disposals","kicks","handballs","marks","goals","behinds","tackles","inside_50s","clearances","contested_possessions","uncontested_possessions","rebound_50s","goal_assists"],
    advanced:["date","round","team","opponent","result","score_involvements","metres_gained","intercepts","turnovers","disposal_efficiency_pct","centre_clearances","stoppage_clearances","tackles_inside_50","contested_marks","marks_inside_50"]}},
  player_seasons:{label:"Player season totals",key:"player_seasons",groups:{production:["player","team","games","age","career_games","kicks_pg","handballs_pg","disposals_pg","marks_pg","goals_pg","behinds_pg","hitouts_pg","tackles_pg"],
    possession_defence:["player","team","games","contested_possessions_pg","uncontested_possessions_pg","clearances_pg","inside_50s_pg","rebound_50s_pg","clangers_pg","contested_marks_pg","marks_inside_50_pg","one_percenters_pg","goal_assists_pg","free_kicks_for_pg","free_kicks_against_pg"],
    awards:["player","team","games","brownlow_votes","goals","goals_pg","scoring_accuracy_pct","career_games","age"]}},
  advanced_player_seasons:{label:"Advanced player season stats",key:"advanced_player_seasons",groups:{possession:["player","team","games","disposals_pg","contested_possessions_pg","uncontested_possessions_pg","effective_disposals_pg","disposal_efficiency_pct","turnovers_pg","intercepts_pg"],
    territory:["player","team","games","inside_50s_pg","rebound_50s_pg","metres_gained_pg","score_involvements_pg","marks_inside_50_pg","tackles_inside_50_pg"],
    stoppages:["player","team","games","clearances_pg","centre_clearances_pg","stoppage_clearances_pg","hitouts_pg","contested_marks_pg","bounces_pg"],
    scoring_fantasy:["player","team","games","goals_pg","goal_assists_pg","afl_fantasy_points_pg","supercoach_points_pg","time_on_ground_pct"]}},
  player_games:{label:"Player game logs",key:"player_games",groups:{production:["date","round","player","team","opponent","home_away","result","points_for","points_against","margin","disposals","kicks","handballs","marks","goals","behinds","tackles","hitouts"],
    possession_defence:["date","round","player","team","opponent","contested_possessions","uncontested_possessions","clearances","inside_50s","rebound_50s","clangers","contested_marks","marks_inside_50","one_percenters","goal_assists"],
    profile:["date","round","player","team","opponent","age","career_games","brownlow_votes","time_on_ground"]}},
  advanced_team_games:{label:"Advanced team game logs",key:"advanced_team_games",groups:{territory:["date","round","team","opponent","home_away","result","points_for","points_against","margin","inside_50s","rebound_50s","metres_gained","score_involvements"],
    pressure_turnovers:["date","round","team","opponent","result","contested_possessions","uncontested_possessions","tackles","tackles_inside_50","intercepts","turnovers","clangers","disposal_efficiency_pct"],
    stoppages:["date","round","team","opponent","result","clearances","centre_clearances","stoppage_clearances","hitouts","contested_marks","marks_inside_50"]}},
  advanced_player_games:{label:"Advanced player game logs",key:"advanced_player_games",groups:{possession:["date","round","player","team","opponent","disposals","contested_possessions","uncontested_possessions","effective_disposals","disposal_efficiency_pct","turnovers","intercepts"],
    territory:["date","round","player","team","opponent","inside_50s","rebound_50s","metres_gained","score_involvements","marks_inside_50","tackles_inside_50"],
    stoppages:["date","round","player","team","opponent","clearances","centre_clearances","stoppage_clearances","hitouts","contested_marks","bounces"],
    scoring_fantasy:["date","round","player","team","opponent","goals","goal_assists","afl_fantasy_points","supercoach_points","time_on_ground_pct"]}},
  award_leaders:{label:"Award indicators",key:"award_leaders",groups:{leaders:["season","award","player","team","value","unit"]}}
};
const groupNames={results:"Results & futures outcomes",team_stats:"Team profile",advanced:"Advanced team metrics",production:"Production",possession_defence:"Possession & defence",awards:"Award indicators",possession:"Possession & efficiency",territory:"Territory & scoring chains",stoppages:"Stoppages",scoring_fantasy:"Scoring & fantasy",profile:"Player background",pressure_turnovers:"Pressure & turnovers",leaders:"Historical award leaders"};
const textKeys=new Set(["team","opponent","player","round","venue","home_away","result","finals_stage","award","unit"]);
const pctKeys=new Set(["win_pct"]);
let data=null, meta=null, sortKey="", sortDir=-1;

async function getJSON(name){
  const r=await fetch("data/"+name,{cache:"no-cache"});if(!r.ok)throw new Error("Could not load "+name+" ("+r.status+")");
  if(name.endsWith(".gz")){const bytes=await r.arrayBuffer();const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));return JSON.parse(await new Response(stream).text());}
  return r.json();
}
function display(value,key){
  if(value==null||value==="")return "–";
  if(typeof value==="boolean")return value?"Yes":"No";
  if(textKeys.has(key))return esc(value);
  if(typeof value==="number"){
    if(pctKeys.has(key))return (value*100).toFixed(1)+"%";
    if(Number.isInteger(value))return value.toLocaleString();
    return value.toLocaleString(undefined,{minimumFractionDigits:1,maximumFractionDigits:1});
  }
  return esc(value);
}
function currentRows(){
  if(!data)return [];
  const cfg=views[$("view").value], group=cfg.groups[$("group").value]||Object.values(cfg.groups)[0];
  const phase=$("phase").value, q=$("search").value.trim().toLowerCase();
  let rows=(data[cfg.key]||[]).filter(row=>phase==="ALL"||row.season_type===phase);
  if(q)rows=rows.filter(row=>Object.values(row).some(v=>v!=null&&String(v).toLowerCase().includes(q)));
  if(sortKey)rows.sort((a,b)=>{
    const x=a[sortKey],y=b[sortKey];let cmp=0;
    if(x==null)cmp=y==null?0:1;else if(y==null)cmp=-1;
    else cmp=(typeof x==="string"||typeof y==="string")?String(x).localeCompare(String(y)):Number(x)-Number(y);
    return cmp*sortDir;
  });
  else if(cfg.key.includes("player"))rows.sort((a,b)=>(Number(b.goals??b.score_involvements??b.disposals??b.brownlow_votes)||0)-(Number(a.goals??a.score_involvements??a.disposals??a.brownlow_votes)||0));
  else rows.sort((a,b)=>String(b.date||"").localeCompare(String(a.date||""))||String(a.team||"").localeCompare(String(b.team||"")));
  return {rows,group};
}
function render(){
  if(!data)return;
  const cfg=views[$("view").value],{rows,group}=currentRows();
  const head=$("head"),body=$("body");
  head.innerHTML="<tr>"+group.map(key=>'<th scope="col" tabindex="0" aria-sort="'+(sortKey===key?(sortDir>0?"ascending":"descending"):"none")+'" data-key="'+key+'">'+esc(labels[key]||key.replaceAll("_"," "))+"</th>").join("")+"</tr>";
  head.querySelectorAll("th").forEach(th=>{
    const sort=()=>{if(sortKey===th.dataset.key)sortDir*=-1;else{sortKey=th.dataset.key;sortDir=textKeys.has(sortKey)?1:-1;}render();};
    th.addEventListener("click",sort);th.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();sort();}});
  });
  body.innerHTML=rows.map(row=>"<tr>"+group.map(key=>'<td class="'+(textKeys.has(key)?"txt":"")+'">'+display(row[key],key)+"</td>").join("")+"</tr>").join("")||'<tr><td class="txt" colspan="'+group.length+'">No rows match these filters or this field is not available for the selected season.</td></tr>';
  const season=Number($("season").value),phase=$("phase").value;
  const phaseName={ALL:"all phases",REG:"home-and-away",FIN:"finals",PRE:"pre-season"}[phase];
  $("status").textContent=rows.length.toLocaleString()+" rows · "+group.length+" readable fields · "+cfg.label+" · "+season+" "+phaseName+" · archive checked "+(meta.archive_updated||"date unavailable");
}
async function loadSeason(){
  sortKey="";$("status").textContent="Loading AFL season data…";
  try{data=await getJSON("season_"+Number($("season").value)+".json.gz");render();}
  catch(e){console.error(e);data={};$("status").textContent="Season data could not be loaded: "+e.message;$("head").innerHTML="";$("body").innerHTML='<tr><td class="txt">No data available.</td></tr>';}
}
function populateGroups(){
  const cfg=views[$("view").value];$("group").innerHTML=Object.keys(cfg.groups).map(key=>'<option value="'+key+'">'+esc(groupNames[key]||key)+"</option>").join("");
}
async function boot(){
  try{
    const index=await getJSON("stats_index.json");meta=index.meta||{};
    const years=meta.seasons||[];
    if(!years.length){$("status").textContent="AFL source data is not available in the latest build.";return;}
    let stamp=meta.updated_utc;
    try{stamp=new Date(stamp).toLocaleString(undefined,{weekday:"short",day:"numeric",month:"short",hour:"numeric",minute:"2-digit"});}catch(e){}
    $("stamp").textContent="AFL archive · updated "+(stamp||"unknown");
    $("season").innerHTML=years.map(y=>'<option value="'+y+'">'+y+"</option>").join("");
    $("view").innerHTML=Object.entries(views).map(([key,v])=>'<option value="'+key+'">'+esc(v.label)+"</option>").join("");
    $("view").addEventListener("change",()=>{populateGroups();render();});
    $("group").addEventListener("change",()=>{sortKey="";render();});
    $("phase").addEventListener("change",render);$("search").addEventListener("input",render);
    $("season").addEventListener("change",loadSeason);
    populateGroups();await loadSeason();
  }catch(e){console.error(e);$("status").textContent="AFL stats index could not be loaded: "+e.message;}
}
boot();
