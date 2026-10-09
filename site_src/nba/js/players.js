boot(async()=>{const data=await getJSON("players.json"),all=data.rows,body=$("playersBody"),search=$("playerSearch"),team=$("playerTeam");
  const teams=[...new Set(all.map(x=>x.team))].sort();team.innerHTML='<option value="">All teams</option>'+teams.map(t=>'<option>'+t+'</option>').join("");
  const render=()=>{const q=search.value.toLowerCase(),t=team.value;const rows=all.filter(r=>(!t||r.team===t)&&(!q||r.player.toLowerCase().includes(q))).slice(0,250);body.innerHTML=rows.map(r=>'<tr><td><b>'+esc(r.player)+'</b></td><td>'+r.team+'</td><td>'+esc(r.position)+'</td><td>'+r.games+'</td><td>'+r.minutes+'</td><td>'+r.ppg.toFixed(1)+'</td><td>'+r.rpg.toFixed(1)+'</td><td>'+r.apg.toFixed(1)+'</td><td class="'+(r.impact>=0?'l-off':'l-def')+'">'+(r.impact>0?'+':'')+r.impact.toFixed(2)+'</td></tr>').join("");};
  search.addEventListener("input",render);team.addEventListener("change",render);render();
});
