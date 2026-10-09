const configs={
  teams:{title:"Team efficiency",file:"advanced_team_stats.json",fields:[["Team","name","text"],["GP","gp"],["W","wins"],["Win %","win_pct","pct"],["OffRtg","off_rating"],["DefRtg","def_rating"],["NetRtg","net_rating"],["Pace","pace"],["eFG%","efg_pct","pct"],["TS%","ts_pct","pct"],["TOV%","tov_pct","pct"],["ORB%","orb_pct","pct"],["DRB%","dreb_pct","pct"],["AST%","assist_pct","pct"],["AST/TO","assist_to_turnover"],["AST ratio","assist_ratio"],["PIE","pie","pct"]]},
  players:{title:"Player efficiency",file:"advanced_player_stats.json",fields:[["Player","player","text"],["Team","team","text"],["GP","gp"],["MIN","minutes"],["Usage %","usage_pct","pct"],["OffRtg","off_rating"],["DefRtg","def_rating"],["NetRtg","net_rating"],["TS%","ts_pct","pct"],["eFG%","efg_pct","pct"],["AST%","assist_pct","pct"],["AST/TO","assist_to_turnover"],["AST ratio","assist_ratio"],["ORB%","off_rebound_pct","pct"],["DRB%","def_rebound_pct","pct"],["REB%","rebound_pct","pct"],["TOV%","turnover_pct","pct"],["Pace","pace"],["PIE","pie","pct"],["Possessions","possessions"]]},
  shots:{title:"Team shot zones",file:"shot_zones.json",fields:[["Team","name","text"],["Shot zone","zone","text"],["FGA","attempts"],["FGM","makes"],["FG%","fg_pct","pct"]]}
};
boot(async()=>{
  const [teamData,playerData,shotData]=await Promise.all([getJSON(configs.teams.file),getJSON(configs.players.file),getJSON(configs.shots.file)]);
  const rows={teams:teamData.rows||[],players:playerData.rows||[],shots:shotData.rows||[]};
  const season=$("advancedSeason"),type=$("advancedType"),view=$("advancedView"),team=$("advancedTeam"),search=$("advancedSearch"),head=$("advancedHead"),body=$("advancedBody");
  const years=[...new Set([...rows.teams,...rows.players,...rows.shots].map(r=>Number(r.season)))].filter(Number.isFinite).sort((a,b)=>b-a);
  if(!years.length){season.innerHTML='<option value="">No advanced data loaded</option>';season.disabled=true;}
  season.innerHTML=years.map(y=>'<option value="'+y+'">'+(y-1)+'–'+String(y).slice(-2)+'</option>').join("");
  team.innerHTML='<option value="">All teams</option>'+Object.keys(NAMES).sort((a,b)=>NAMES[a].localeCompare(NAMES[b])).map(t=>'<option value="'+esc(t)+'">'+esc(NAMES[t])+'</option>').join("");
  let sortKey="",direction=-1;
  function render(){
    const key=view.value,cfg=configs[key],seasonYear=Number(season.value),seasonType=Number(type.value),teamCode=team.value,q=search.value.trim().toLowerCase();
    let data=rows[key].filter(r=>Number(r.season)===seasonYear&&Number(r.season_type)===seasonType&&(!teamCode||r.team===teamCode));
    if(q)data=data.filter(r=>String(r.player||r.name||r.team||"").toLowerCase().includes(q)||String(NAMES[r.team]||"").toLowerCase().includes(q));
    if(sortKey)data.sort((a,b)=>{const av=a[sortKey],bv=b[sortKey];if(av==null)return 1;if(bv==null)return -1;return (typeof av==="string"?String(av).localeCompare(String(bv)):Number(av)-Number(bv))*direction;});
    else if(key==="players")data.sort((a,b)=>(b.minutes||0)-(a.minutes||0));else data.sort((a,b)=>String(a.name||a.team||"").localeCompare(String(b.name||b.team||"")));
    $("advancedTitle").textContent=cfg.title;$("advancedCount").textContent=data.length.toLocaleString()+" rows";
    $("advancedNote").textContent=key==="shots"?"Shot zones are derived from NBA Stats shot event coordinates and distances. Only two- and three-point attempts are included; corner threes use the published coordinate frame. Small or missing zone counts should be interpreted cautiously.":"Source-provided NBA Stats season dashboard fields. Offensive/defensive/net rating are points per 100 possessions; percentage fields are displayed as percentages. The source may revise definitions or historical values.";
    head.innerHTML="<tr>"+cfg.fields.map(([label,k,kind])=>'<th scope="col" tabindex="0" data-key="'+(k||"")+'" data-kind="'+(kind||"num")+'" aria-sort="'+(sortKey===k?(direction>0?"ascending":"descending"):"none")+'">'+esc(label)+"</th>").join("")+"</tr>";
    head.querySelectorAll("th").forEach(th=>{const sort=()=>{if(!th.dataset.key)return;if(sortKey===th.dataset.key)direction*=-1;else{sortKey=th.dataset.key;direction=th.dataset.kind==="text"?1:-1;}render();};th.addEventListener("click",sort);th.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();sort();}});});
    body.innerHTML=data.map(r=>"<tr>"+cfg.fields.map(([,k,kind])=>{let value=r[k];if(k==="team"&&key==="players")value=NAMES[value]||value;if(kind==="pct"&&value!=null)value=(Number(value)*100).toFixed(1)+"%";else if(value!=null&&typeof value==="number")value=value.toFixed(1);return '<td class="'+(kind==="text"?"txt":"")+'">'+esc(value==null?"–":value)+"</td>";}).join("")+"</tr>").join("")||'<tr><td colspan="'+cfg.fields.length+'" class="txt">No rows are available for these filters.</td></tr>';
  }
  [season,type,view,team].forEach(el=>el.addEventListener("change",()=>{sortKey="";render();}));search.addEventListener("input",render);season.value=String(years[0]||"");view.value=view.value||"teams";render();
});
