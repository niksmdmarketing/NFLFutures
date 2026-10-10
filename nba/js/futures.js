let FT={}, DIVS={};
function renderTable(){
  let h="";
  Object.entries(DIVS).forEach(([division,teams])=>{
    h+='<tr class="divhead"><td colspan="8">'+division+'</td></tr>';
    [...teams].sort((a,b)=>FT[b].p_title-FT[a].p_title||FT[b].mean_wins-FT[a].mean_wins).forEach(t=>{
      const v=FT[t];
      h+='<tr><td><b>'+t+'</b> <span class="muted">'+NAMES[t]+'</span></td><td class="num">'+v.mean_wins.toFixed(1)+'</td>'+pcell(v.p_div)+pcell(v.p_top6)+pcell(v.p_playoff)+pcell(v.p_seed1)+pcell(v.p_conf)+pcell(v.p_title)+'</tr>';
    });
  });
  $("fbody").innerHTML=h;
}
function renderWT(){
  const t=$("wtTeam").value,L=+$("wtLine").value,d=FT[t].win_dist;
  let over=0,under=0,push=0; d.forEach((p,w)=>{if(w>L)over+=p;else if(w<L)under+=p;else push+=p;});
  $("ou").innerHTML='<div><small>Over '+L+'</small><span class="big l-off">'+pct(over)+'</span></div><div><small>Under '+L+'</small><span class="big l-def">'+pct(under)+'</span></div><div><small>Push</small><span class="big">'+(Number.isInteger(L)?pct(push):"–")+'</span></div>';
  let lo=0,hi=82,acc=0; for(let w=0;w<d.length;w++){acc+=d[w];if(acc>=.1){lo=w;break;}} acc=0; for(let w=0;w<d.length;w++){acc+=d[w];if(acc>=.9){hi=w;break;}}
  $("wtNote").textContent=NAMES[t]+" project to "+FT[t].mean_wins.toFixed(1)+" wins. The middle 80% of simulations finish between "+lo+" and "+hi+" wins.";
  $("distTitle").textContent="Win distribution · "+t;
  const W=600,H=170,Lp=32,Rp=6,Tp=10,Bp=24,bw=(W-Lp-Rp)/d.length,mx=Math.max(.04,Math.ceil(Math.max(...d)*20)/20),y=p=>Tp+(1-p/mx)*(H-Tp-Bp); let g="";
  for(let v=0;v<=mx+1e-9;v+=.05)g+='<line x1="'+Lp+'" x2="'+(W-Rp)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="var(--line)"/><text x="'+(Lp-4)+'" y="'+(y(v)+3)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+Math.round(v*100)+'%</text>';
  d.forEach((p,w)=>{const col=w>L?"var(--off)":w<L?"var(--def)":"var(--even)",x=Lp+w*bw+.5;g+='<rect x="'+x.toFixed(1)+'" y="'+y(p).toFixed(1)+'" width="'+Math.max(1,bw-1).toFixed(1)+'" height="'+(y(0)-y(p)).toFixed(1)+'" fill="'+col+'"><title>'+w+' wins: '+(p*100).toFixed(1)+'%</title></rect>';if(w%10===0)g+='<text x="'+(x+bw/2).toFixed(1)+'" y="'+(H-7)+'" text-anchor="middle" font-size="9" fill="var(--muted)">'+w+'</text>';});
  $("dist").innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Final win distribution for '+esc(NAMES[t])+'">'+g+'</svg>';
}
function initWT(){
  const teams=Object.keys(FT).sort((a,b)=>NAMES[a].localeCompare(NAMES[b])),top=[...teams].sort((a,b)=>FT[b].p_title-FT[a].p_title)[0];
  $("wtTeam").innerHTML=teams.map(t=>'<option value="'+t+'"'+(t===top?' selected':'')+'>'+NAMES[t]+'</option>').join("");
  const lines=[];for(let v=10.5;v<=70.5;v+=.5)lines.push(v);$("wtLine").innerHTML=lines.map(v=>'<option value="'+v+'">'+v+'</option>').join("");
  const setDefault=()=>{$("wtLine").value=String(Math.min(70.5,Math.max(10.5,Math.floor(FT[$("wtTeam").value].mean_wins)+.5)));};
  setDefault();$("wtTeam").addEventListener("change",()=>{setDefault();renderWT();});$("wtLine").addEventListener("change",renderWT);renderWT();
}
boot(async meta=>{const data=await getJSON("futures.json");FT=data.teams;DIVS=data.divisions;document.querySelectorAll("[data-nsims]").forEach(x=>x.textContent=meta.n_sims.toLocaleString());renderTable();initWT();});
