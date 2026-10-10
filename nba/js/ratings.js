boot(async()=>{const data=await getJSON("ratings.json"),rows=data.rows,tb=$("ratingsTable"),body=$("ratingsBody");
  const render=()=>{body.innerHTML=rows.map((r,i)=>'<tr><td><b>'+r.team+'</b> <small>'+esc(r.name)+'</small></td><td>'+(i+1)+'</td><td>'+r.projected_wins.toFixed(1)+'</td><td>'+r.off_rating.toFixed(1)+'</td><td>'+r.def_rating.toFixed(1)+'</td><td class="'+(r.net_rating>=0?'l-off':'l-def')+'">'+(r.net_rating>0?'+':'')+r.net_rating.toFixed(1)+'</td><td>'+(r.roster_adj>0?'+':'')+r.roster_adj.toFixed(1)+'</td><td class="'+(r.model_rating>=0?'l-off':'l-def')+'">'+(r.model_rating>0?'+':'')+r.model_rating.toFixed(1)+'</td><td>'+r.pace.toFixed(1)+'</td></tr>').join("");};
  render();setupSort(tb,rows,render);
});
