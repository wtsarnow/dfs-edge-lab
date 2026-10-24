'use strict';
const $=s=>document.querySelector(s), app=$('#app');
const FILES=['players','patterns','entries','bots','lineups','stacks','weeks','wiki_daily'];
const D={}; const charts=[];
const fmt=(v,d=2)=>v==null||v===''||(typeof v==='number'&&isNaN(v))?'<span class="mut">n/a</span>':(typeof v==='number'?(Number.isInteger(v)?v.toLocaleString():v.toFixed(d)):esc(v));
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const mean=a=>{a=a.filter(x=>x!=null&&!isNaN(x));return a.length?a.reduce((s,x)=>s+x,0)/a.length:null};
function csv(rows,name){if(!rows.length)return;const ks=Object.keys(rows[0]);const q=v=>v==null?'':(/[",\n]/.test(String(v))?'"'+String(v).replace(/"/g,'""')+'"':v);
 const t=[ks.join(',')].concat(rows.map(r=>ks.map(k=>q(typeof r[k]==='object'&&r[k]!==null?JSON.stringify(r[k]):r[k])).join(','))).join('\n');
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'text/csv'}));a.download=name+'.csv';a.click()}
let TID=0;
function table(rows,opts={}){const id='t'+(TID++);const cols=opts.cols||(rows[0]?Object.keys(rows[0]):[]);const st={rows,sort:null,dir:1,q:'',page:0,ps:opts.ps||25};
 const el=document.createElement('div');el.className='tblc';
 el.innerHTML=`<div class="tools"><input placeholder="Filter…" class="f"> <span class="mut cnt"></span><span style="flex:1"></span><button class="b x">⬇ CSV</button></div><div class="tbl-wrap"><table><thead><tr>${cols.map(c=>`<th data-c="${c}">${esc(opts.labels?.[c]||c)}</th>`).join('')}</tr></thead><tbody></tbody></table></div><div class="pager"></div>`;
 const draw=()=>{let r=st.rows;if(st.q){const q=st.q.toLowerCase();r=r.filter(x=>cols.some(c=>String(x[c]??'').toLowerCase().includes(q)))}
  if(st.sort){const c=st.sort;r=[...r].sort((a,b)=>{const x=a[c],y=b[c];if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*st.dir})}
  st.cur=r;const pages=Math.max(1,Math.ceil(r.length/st.ps));st.page=Math.min(st.page,pages-1);
  el.querySelector('tbody').innerHTML=r.slice(st.page*st.ps,(st.page+1)*st.ps).map(x=>`<tr>${cols.map(c=>{const v=x[c];const isn=typeof v==='number';const cell=opts.render?.[c]?opts.render[c](v,x):fmt(typeof v==='object'&&v?JSON.stringify(v):v);return `<td class="${isn?'n':''}">${cell}</td>`}).join('')}</tr>`).join('')||`<tr><td colspan="${cols.length}" class="mut">No rows</td></tr>`;
  el.querySelector('.cnt').textContent=r.length.toLocaleString()+' rows';
  el.querySelector('.pager').innerHTML=pages>1?`<button class="b pv">‹</button> Page ${st.page+1} / ${pages} <button class="b nx">›</button>`:'';
  el.querySelector('.pv')?.addEventListener('click',()=>{st.page=Math.max(0,st.page-1);draw()});el.querySelector('.nx')?.addEventListener('click',()=>{st.page++;draw()})};
 el.querySelector('.f').addEventListener('input',e=>{st.q=e.target.value;st.page=0;draw()});
 el.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{const c=th.dataset.c;st.dir=st.sort===c?-st.dir:-1;st.sort=c;draw()}));
 el.querySelector('.x').addEventListener('click',()=>csv(st.cur.map(x=>Object.fromEntries(cols.map(c=>[c,x[c]]))),opts.name||'table'));
 draw();return el}
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function chart(el,opt,data,name){const c=echarts.init(el,null,{renderer:'canvas'});const ink=css('--ink'),mut=css('--mut'),line=css('--line');
 const base={animation:false,textStyle:{fontFamily:'Inter',color:ink},color:['#2563eb','#7c3aed','#059669','#f59e0b','#dc2626','#0891b2','#db2777'],grid:{left:48,right:16,top:36,bottom:40,containLabel:true},tooltip:{trigger:'axis'},legend:{textStyle:{color:mut},top:0}};
 const ax=a=>a&&(Array.isArray(a)?a:[a]).forEach(x=>{x.axisLine={lineStyle:{color:line}};x.splitLine={lineStyle:{color:line}};x.axisLabel=Object.assign({color:mut},x.axisLabel||{});x.nameTextStyle={color:mut}});
 ax(opt.xAxis);ax(opt.yAxis);c.setOption(Object.assign(base,opt));charts.push(c);
 if(data){const b=document.createElement('button');b.className='b';b.style.cssText='float:right;margin-top:-4px';b.textContent='⬇ CSV';b.onclick=()=>csv(data,name||'chart');el.parentNode.querySelector('h2')?.prepend(b)}return c}
addEventListener('resize',()=>charts.forEach(c=>c.resize()));
function card(h,body,cls=''){return `<div class="card ${cls}">${h?`<h2>${h}</h2>`:''}${body}</div>`}
function kpi(l,v,d=''){return `<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d}</div></div>`}
function put(sel,el){$(sel).appendChild(el)}
// ---------------- sections
const S={};
S.overview=()=>{const E=D.entries.entries,P=D.players.rows,graded=E.filter(e=>e.pct!=null);const fees=E.reduce((s,e)=>s+((e.fee||0)*(e.count||1)),0),won=E.reduce((s,e)=>s+(e.winnings||0),0);
 const pt=D.patterns;const at=D.entries.autotune.at(-1);const L=D.lineups;
 app.innerHTML=`<h1>Executive overview</h1><p class="sub">Season 2026 · ${P.length.toLocaleString()} player-games · ${new Set(P.map(r=>r.game_id)).size} NFL games · ${pt.signals.length} signals × ${pt.outcomes.length} outcomes · ${pt.all.length.toLocaleString()} statistical tests</p>
 <div class="grid g4">${kpi('Graded entries',graded.length,`${E.length} entries tracked (real + mock)`)}${kpi('Avg percentile',fmt(mean(graded.map(e=>e.pct)),1),'beat this share of the field')}${kpi('BEAT_80 hits',graded.filter(e=>e.pct>=80).length,'graded entries ≥ 80th pct')}${kpi('Auto-tune',at.status,esc(at.why))}
 ${kpi('Fees (known)','$'+fees.toFixed(2),'entries with a known fee')}${kpi('Winnings (known)','$'+won.toFixed(2),'entries with known winnings')}${kpi('Significant patterns',pt.all.filter(x=>x.q<0.1&&x.novelty==='pre-game (predictive)').length,'pre-game, FDR q < 0.10')}${kpi('W8 top projection',fmt(L.top[0].proj,1),'Edge Lab model, Top #1')}</div>
 <div class="grid g2"><div class="card"><h2>Percentile by entry</h2><div class="chart" id="c1"></div></div><div class="card"><h2>Top unusual pre-game signals</h2><div class="chart" id="c2"></div></div></div>
 <div class="card"><h2>Key takeaways</h2><ul id="tk"></ul></div>`;
 const g=graded.map((e,i)=>({i:i+1,week:e.week,contest:e.contest,pct:e.pct,type:e.type}));
 chart($('#c1'),{xAxis:{type:'category',data:g.map(x=>'W'+x.week+' '+x.contest.slice(0,14)),axisLabel:{rotate:40,fontSize:10}},yAxis:{type:'value',max:100,name:'pct'},series:[{type:'bar',data:g.map(x=>({value:x.pct,itemStyle:{color:x.pct>=80?css('--pos'):x.type==='Showdown'?'#7c3aed':'#2563eb'}})),markLine:{data:[{yAxis:80}],lineStyle:{color:css('--neg')},label:{formatter:'BEAT_80'}}}]},g,'entry_percentiles');
 const u=pt.unusual.slice(0,10);chart($('#c2'),{grid:{left:150,right:20,top:20,bottom:30},xAxis:{type:'value',name:'r'},yAxis:{type:'category',data:u.map(x=>`${x.pos} ${x.signal}→${x.outcome}`).reverse(),axisLabel:{fontSize:11}},tooltip:{},series:[{type:'bar',data:u.map(x=>x.r).reverse(),itemStyle:{color:p=>p.value>0?css('--pos'):css('--neg')}}]},u,'unusual_signals');
 const tops=pt.unusual.slice(0,4).map(x=>`<li><b>${x.pos} · ${x.signal}</b> vs ${x.outcome}: r = ${x.r} (n=${x.n}, p=${x.p}, q=${x.q})${x.small_n?' <span class="chip warn">small n</span>':''}</li>`).join('');
 const sk=D.stacks.stacks.map(s=>`${s.pair} r=${s.r}`).join(' · ');
 $('#tk').innerHTML=tops+`<li><b>Stack correlations</b> (FD pts, ${D.stacks.stacks[0]?.n} team-games): ${sk}</li><li>Classic vs Showdown avg percentile: ${['Classic','Showdown'].map(t=>t+' '+fmt(mean(graded.filter(e=>e.type===t).map(e=>e.pct)),1)).join(' · ')}</li>`};
S.myfd=()=>{const E=D.entries.entries;app.innerHTML=`<h1>My FanDuel</h1><p class="sub">Every real and mock entry (mocks count toward actual). ROI only where fee and winnings are known.</p>
 <div class="grid g2"><div class="card"><h2>Percentile trend</h2><div class="chart" id="m1"></div></div><div class="card"><h2>Contest type & fee tier</h2><div class="chart" id="m2"></div></div></div>
 <div class="grid g2"><div class="card"><h2>Auto-tune timeline</h2><div class="chart sm" id="m3"></div></div><div class="card"><h2>Picks that helped / hurt (pts vs salary expectation)</h2><div class="chart sm" id="m4"></div><p class="note">Residual = FD points minus a per-position fit on implied team total. Only lineups with saved player lists are counted.</p></div></div>
 <div class="card"><h2>All entries</h2><div id="mt"></div></div>`;
 const g=E.filter(e=>e.pct!=null);chart($('#m1'),{xAxis:{type:'category',data:g.map(e=>'W'+e.week+' '+e.slate)},yAxis:{type:'value',max:100},series:[{type:'line',smooth:true,areaStyle:{opacity:.08},data:g.map(e=>e.pct),name:'percentile'},{type:'line',data:g.map(()=>80),name:'BEAT_80',lineStyle:{type:'dashed'},symbol:'none'}]},g,'percentile_trend');
 const grp={};g.forEach(e=>{[e.type,'fee '+e.fee_tier].forEach(k=>{(grp[k]=grp[k]||[]).push(e.pct)})});const gr=Object.entries(grp).map(([k,v])=>({group:k,n:v.length,avg_pct:+mean(v).toFixed(1)}));
 chart($('#m2'),{xAxis:{type:'category',data:gr.map(x=>x.group+` (n=${x.n})`)},yAxis:{type:'value',max:100},series:[{type:'bar',data:gr.map(x=>x.avg_pct),label:{show:true,position:'top'}}]},gr,'type_fee_tier');
 const at=D.entries.autotune;chart($('#m3'),{tooltip:{trigger:'item',formatter:p=>at[p.dataIndex].date+': '+at[p.dataIndex].status+'<br>'+at[p.dataIndex].why},xAxis:{type:'category',data:at.map(a=>a.date)},yAxis:{type:'category',data:['ACTIVE','FROZEN']},series:[{type:'line',step:'end',data:at.map(a=>a.status),symbolSize:12}]},at,'autotune');
 const pk=D.players.rows.filter(r=>r.our_lineups>0&&r.fd_resid!=null).sort((a,b)=>b.fd_resid-a.fd_resid);const sel=pk.slice(0,8).concat(pk.slice(-8));
 chart($('#m4'),{grid:{left:120,right:20,top:10,bottom:30},xAxis:{type:'value'},yAxis:{type:'category',data:sel.map(r=>`W${r.week} ${r.player}`).reverse(),axisLabel:{fontSize:10}},series:[{type:'bar',data:sel.map(r=>+r.fd_resid.toFixed(2)).reverse(),itemStyle:{color:p=>p.value>0?css('--pos'):css('--neg')}}]},pk.map(r=>({week:r.week,player:r.player,pos:r.pos,fd_pts:r.fd_pts,resid:r.fd_resid,lineups:r.our_lineups})),'pick_impact');
 put('#mt',table(E,{name:'entries',cols:['week','slate','contest','type','fee_tier','fee','score','rank','field','pct','winnings','roi','beat80','mock','lineup'],render:{beat80:v=>v==null?fmt(null):v?'<span class="chip good">YES</span>':'<span class="chip bad">NO</span>',lineup:v=>v?`<span title="${esc(v)}">${esc(String(v).slice(0,40))}…</span>`:fmt(null)}}))};
S.lab=()=>{const P=D.players.rows,pt=D.patterns;app.innerHTML=`<h1>Pattern Lab</h1><p class="sub">Pick any signal against any outcome. ${pt.notes.join(' ')}</p>
 <div class="card"><h2>Correlation explorer</h2><div class="tools"><select id="ls">${pt.signals.map(s=>`<option>${s}</option>`).join('')}</select><select id="lo">${pt.outcomes.map(s=>`<option>${s}</option>`).join('')}</select><select id="lp">${['ALL','QB','RB','WR','TE','DST','K'].map(s=>`<option>${s}</option>`).join('')}</select><span id="lstat" class="chip"></span></div><div class="chart" id="l1"></div></div>
 <div class="grid g2"><div class="card"><h2>Position splits (selected signal)</h2><div class="chart sm" id="l2"></div></div><div class="card"><h2>Categorical factors (ANOVA on residual)</h2><div id="lc"></div></div></div>
 <div class="card"><h2>Unusual signals <span class="chip">pre-game, non-obvious, p &lt; 0.05</span></h2><div id="lu"></div></div>
 <div class="card"><h2>Ranked pattern list</h2><div id="lr"></div></div><div class="card"><h2>Signal buckets (mean residual)</h2><div id="lb"></div></div>`;
 $('#ls').value='wiki_z';$('#lo').value='fd_resid';let c1,c2;
 const run=()=>{const s=$('#ls').value,o=$('#lo').value,p=$('#lp').value;const rows=P.filter(r=>(p==='ALL'||r.pos===p)&&r[s]!=null&&r[o]!=null);const nms=rows.map(r=>r.player+' W'+r.week);const xy=rows.map(r=>[+r[s],+r[o]]);
  const t=pt.all.find(x=>x.signal===s&&x.outcome===o&&x.pos===p);$('#lstat').innerHTML=t?`n=${t.n} · r=${t.r} · ρ=${t.rho} · p=${t.p} · q=${t.q}${t.small_n?' · small n':''}`:`n=${xy.length} · not enough data for a test`;
  c1&&c1.dispose();c1=chart($('#l1'),{tooltip:{trigger:'item',formatter:x=>`${esc(nms[x.dataIndex])}<br>${s}: ${x.value[0]}<br>${o}: ${x.value[1]}`},xAxis:{type:'value',name:s,scale:true},yAxis:{type:'value',name:o,scale:true},series:[{type:'scatter',symbolSize:6,itemStyle:{opacity:.55},data:xy}]},null);
  const pr=['QB','RB','WR','TE','DST'].map(q=>({pos:q,...(pt.all.find(x=>x.signal===s&&x.outcome===o&&x.pos===q)||{})}));
  c2&&c2.dispose();c2=chart($('#l2'),{xAxis:{type:'category',data:pr.map(x=>x.pos+(x.n?` (${x.n})`:''))},yAxis:{type:'value',min:-1,max:1,name:'r'},series:[{type:'bar',data:pr.map(x=>x.r??null),label:{show:true,position:'top'}}]},null)};
 ['#ls','#lo','#lp'].forEach(x=>$(x).addEventListener('change',run));run();
 const b1=document.createElement('button');b1.className='b';b1.textContent='⬇ CSV (scatter)';b1.style.float='right';b1.onclick=()=>{const s=$('#ls').value,o=$('#lo').value,p=$('#lp').value;csv(P.filter(r=>(p==='ALL'||r.pos===p)&&r[s]!=null&&r[o]!=null).map(r=>({player:r.player,week:r.week,pos:r.pos,[s]:r[s],[o]:r[o]})),'explorer_'+s+'_'+o)};$('#l1').parentNode.querySelector('h2').prepend(b1);
 const cols=['pos','signal','outcome','n','r','rho','p','q','small_n','novelty'];const rr={p:v=>v==null?fmt(null):(v<0.001?v.toExponential(1):v.toFixed(3)),small_n:v=>v?'<span class="chip warn">small n</span>':'',q:v=>v<0.1?`<b>${v}</b>`:fmt(v,4)};
 put('#lu',table(pt.unusual,{name:'unusual_signals',cols,render:rr,ps:10}));put('#lr',table(pt.ranked,{name:'ranked_patterns',cols,render:rr,ps:15}));
 put('#lc',table(pt.categorical.flatMap(c=>c.levels.map(l=>({factor:c.factor,anova_p:c.p,level:l.level,n:l.n,mean_resid:l.mean_resid}))),{name:'categorical',ps:10}));
 put('#lb',table(pt.buckets,{name:'buckets',ps:12}))};
function luTable(l){return `<div class="tbl-wrap"><table class="lu"><tr><th>Pos</th><th>Player</th><th>Team</th><th>Salary</th><th>Proj</th><th>Ceil</th><th>Own</th></tr>${l.players.map(p=>`<tr><td>${p.pos==='D'?'DEF':p.pos}</td><td>${esc(p.name)}${p.inj?` <span class="chip warn">${p.inj}</span>`:''}</td><td>${p.team} v ${p.opp||''}</td><td class="n">$${p.salary.toLocaleString()}</td><td class="n">${p.proj.toFixed(1)}</td><td class="n">${p.ceil.toFixed(1)}</td><td class="n">${p.own==null?'<span class="mut">n/a</span>':p.own+'%'}</td></tr>`).join('')}<tr><td></td><td><b>Total</b></td><td></td><td class="n"><b>$${l.salary.toLocaleString()}</b></td><td class="n"><b>${l.proj}</b></td><td class="n">${l.ceil}</td><td></td></tr></table></div>`}
S.week=()=>{const L=D.lineups;const flat=[...L.top,L.cash,L.gpp,L.stack].flatMap(l=>l.players.map(p=>({build:l.label,...p})));
 app.innerHTML=`<h1>Current week · ${esc(L.label)}</h1><p class="sub"><b>Projection source:</b> ${esc(L.projection_source)}. Classic, $60K cap, QB · 2 RB · 3 WR · TE · FLEX · DEF, max 4 per team.</p>
 <div class="card"><h2>Official picks from the fanduel bot</h2>${L.official?luTable(L.official):'<p class="mut">Slot reserved. The fanduel bot\'s official lineups go in <code>lineups.json → official</code> and show here.</p>'}</div>
 <div class="grid lug">${[L.cash,L.gpp,L.stack].map(l=>card(esc(l.label)+` <span class="chip">${esc(l.objective)}</span>`,luTable(l))).join('')}</div>
 <div class="card"><h2>Top 10 by projected median</h2><div class="chart sm" id="w1"></div><div id="w2"></div></div>
 <div class="card"><h2>Player exposure across all builds</h2><div class="chart" id="w3"></div></div>`;
 chart($('#w1'),{xAxis:{type:'category',data:L.top.map(l=>l.label)},yAxis:{type:'value',scale:true},series:[{name:'median',type:'bar',data:L.top.map(l=>l.proj)},{name:'ceiling',type:'line',data:L.top.map(l=>l.ceil)},{name:'floor',type:'line',data:L.top.map(l=>l.floor)}]},L.top.map(l=>({label:l.label,proj:l.proj,ceil:l.ceil,floor:l.floor,salary:l.salary,players:l.players.map(p=>p.name).join('; ')})),'week8_top10');
 put('#w2',table(L.top.map(l=>({build:l.label,proj:l.proj,salary:l.salary,lineup:l.players.map(p=>p.name).join(', ')})),{name:'week8_lineups',ps:10}));
 const ex={};flat.forEach(p=>ex[p.name]=(ex[p.name]||0)+1);const e=Object.entries(ex).sort((a,b)=>b[1]-a[1]).slice(0,20);
 chart($('#w3'),{grid:{left:140,right:20,top:10,bottom:30},xAxis:{type:'value'},yAxis:{type:'category',data:e.map(x=>x[0]).reverse()},series:[{type:'bar',data:e.map(x=>x[1]).reverse()}]},flat,'week8_all_build_players')};
S.bots=()=>{const B=D.bots.bots,A=B.flatMap(b=>b.ablation);app.innerHTML=`<h1>Bot Impact</h1><p class="sub">What each FanDuel bot contributes, ablation on the Week 8 optimizer (re-run without that bot's input; delta = full-model projection of the ablated lineup minus the full-model best), and historical accuracy from saved records only.</p>
 <div class="card"><h2>Ablation: projected-points delta</h2><div class="chart" id="b1"></div></div>
 <div class="card"><h2>Ablation detail</h2><div id="b2"></div></div><div class="card"><h2>Bots, roles and track record</h2><div id="b3"></div></div>
 <div class="grid g2"><div class="card"><h2>offense-overall: EPA calls vs actual</h2><div class="chart sm" id="b4"></div></div><div class="card"><h2>Projection accuracy by position</h2><div class="chart sm" id="b5"></div></div></div>
 <div class="card"><h2>Patch log (fanduel-review)</h2><div id="b6"></div></div>`;
 const bots=[...new Set(A.map(a=>a.bot))];const builds=[...new Set(A.map(a=>a.build))];
 chart($('#b1'),{xAxis:{type:'category',data:bots.map(b=>b.replace('fanduel-','')),axisLabel:{rotate:30}},yAxis:{type:'value',name:'Δ pts'},series:builds.map(bd=>({name:bd,type:'bar',data:bots.map(b=>A.find(a=>a.bot===b&&a.build===bd)?.delta_proj_full_model??null)}))},A,'bot_ablation');
 put('#b2',table(A,{name:'bot_ablation_detail',cols:['build','bot','players_changed','delta_proj_full_model','players_out','players_in'],ps:14}));
 put('#b3',table(B.map(b=>({bot:b.bot,role:b.role,ablation:b.ablation_input?'yes':'no saved W8 input / n/a',records:b.history?.records,accuracy:b.history?.hit})),{name:'bots',ps:20,render:{accuracy:v=>v?esc(v):'<span class="mut">no graded record</span>',role:v=>`<span style="white-space:normal">${esc(v)}</span>`,records:v=>`<span style="white-space:normal">${esc(v||'')}</span>`}}));
 const e=D.bots.epa;chart($('#b4'),{tooltip:{trigger:'item'},xAxis:{type:'category',data:e.map(r=>r.team+' '+r.date.slice(5))},yAxis:{type:'value'},series:[{name:'band',type:'bar',stack:'b',data:e.map(r=>+r.low),itemStyle:{opacity:0}},{name:'band',type:'bar',stack:'b',data:e.map(r=>(+r.high-+r.low).toFixed(2)),itemStyle:{opacity:.25}},{name:'actual',type:'scatter',data:e.map(r=>+r.actual),symbolSize:10}]},e,'epa_calibration');
 const pa=Object.entries(D.bots.proj_accuracy).map(([k,v])=>({pos:k,...v}));chart($('#b5'),{xAxis:{type:'category',data:pa.map(x=>x.pos+` (${x.n})`)},yAxis:[{type:'value',name:'MAE'},{type:'value',name:'r',max:1}],series:[{name:'MAE',type:'bar',data:pa.map(x=>x.mae)},{name:'r',type:'line',yAxisIndex:1,data:pa.map(x=>x.r)}]},pa,'projection_accuracy');
 const pl=(B.find(b=>b.bot==='fanduel-review')?.patches||[]).map(l=>{const c=l.split('|').map(x=>x.trim());return {date:c[0],patch:c[1],anchors:c[2],confidence:c[3],applied:c[4],result:c[5]}});put('#b6',table(pl,{name:'patch_log',ps:20}))};
S.players=()=>{const P=D.players.rows;const by={};P.forEach(r=>(by[r.player+'|'+r.team]=by[r.player+'|'+r.team]||[]).push(r));const keys=Object.keys(by).sort();
 app.innerHTML=`<h1>Player explorer</h1><p class="sub">${keys.length} players. Search and pick one for a game log, charts and Wikipedia attention.</p><div class="grid pgrid"><div class="card"><input id="ps" placeholder="Search player or team…" style="width:100%;margin-bottom:8px"><div class="plist" id="pl"></div></div><div id="pd"></div></div>`;
 const list=q=>{$('#pl').innerHTML=keys.filter(k=>k.toLowerCase().includes(q.toLowerCase())).slice(0,300).map(k=>`<div data-k="${esc(k)}">${esc(k.split('|')[0])} <span class="mut">${k.split('|')[1]} · ${by[k][0].pos}</span></div>`).join('')};
 const show=k=>{const g=by[k].sort((a,b)=>a.week-b.week);const r0=g[0];const wd=D.wiki_daily[r0.wiki_title]||{};
  $('#pd').innerHTML=`<div class="grid g4">${kpi(esc(r0.player),r0.pos+' · '+r0.team,g.length+' games')}${kpi('Avg FD pts',fmt(mean(g.map(x=>x.fd_pts)),1))}${kpi('Avg target share',fmt(mean(g.map(x=>x.target_share)),3))}${kpi('Avg snap %',fmt(mean(g.map(x=>x.snap_pct)),2))}</div>
  <div class="card"><h2>FD points & usage by week</h2><div class="chart sm" id="p1"></div></div><div class="card"><h2>Wikipedia daily views (attention)</h2><div class="chart sm" id="p2"></div></div><div class="card"><h2>Game log</h2><div id="p3"></div></div>`;
  chart($('#p1'),{xAxis:{type:'category',data:g.map(x=>'W'+x.week+' v '+x.opp)},yAxis:[{type:'value',name:'FD pts'},{type:'value',name:'touches'}],series:[{name:'FD pts',type:'bar',data:g.map(x=>x.fd_pts)},{name:'targets',type:'line',yAxisIndex:1,data:g.map(x=>x.targets)},{name:'carries',type:'line',yAxisIndex:1,data:g.map(x=>x.carries)},{name:'proj',type:'line',data:g.map(x=>x.proj),lineStyle:{type:'dashed'}}]},g,'player_'+r0.player);
  const ds=Object.keys(wd).sort();chart($('#p2'),{xAxis:{type:'category',data:ds.map(d=>d.slice(4,6)+'/'+d.slice(6))},yAxis:{type:'value'},dataZoom:[{type:'inside'}],series:[{type:'line',symbol:'none',areaStyle:{opacity:.1},data:ds.map(d=>wd[d]),markPoint:{data:g.filter(x=>wd[x.gameday.replace(/-/g,'')]).map(x=>({coord:[ds.indexOf(x.gameday.replace(/-/g,'')),wd[x.gameday.replace(/-/g,'')]],value:'G'}))}}]},ds.map(d=>({date:d,views:wd[d]})),'wiki_'+r0.player);
  put('#p3',table(g,{name:'gamelog_'+r0.player,cols:['week','opp','home','salary','proj','fd_pts','pts_per_1k','snap_pct','targets','target_share','air_yards','wopr','carries','rz_touches','epa_total','implied_total','wiki_z','box'],ps:20}));
  document.querySelectorAll('#pl div').forEach(d=>d.classList.toggle('on',d.dataset.k===k))};
 $('#ps').addEventListener('input',e=>list(e.target.value));$('#pl').addEventListener('click',e=>{const d=e.target.closest('div[data-k]');if(d)show(d.dataset.k)});list('');
 const top=keys.sort((a,b)=>mean(by[b].map(x=>x.fd_pts))-mean(by[a].map(x=>x.fd_pts)))[0];keys.sort();show(top)};
S.raw=()=>{const P=D.players.rows;app.innerHTML=`<h1>Raw data</h1><p class="sub">Every table sorts (click a header), filters and exports to CSV. Full downloads below.</p>
 <div class="card"><h2>Full-dataset downloads</h2><div class="tools">${['player_games.csv','pattern_tests.csv','entries.csv','pick_impact.csv'].map(f=>`<a class="b" href="data/${f}" download>${f}</a>`).join('')}<a class="b" href="bot_ablation.csv" download>bot_ablation.csv</a>${['players.json','patterns.json','lineups.json','bots.json','stacks.json','teams.json','wiki_daily.json','weeks.json'].map(f=>`<a class="b" href="${f}" download>${f}</a>`).join('')}</div></div>
 <div class="card"><h2>Coverage (non-null rows per field)</h2><div class="chart" id="r0"></div></div>
 <div class="card"><h2>Player-games by week</h2><div class="tools"><select id="rw"><option value="">All weeks</option>${[...new Set(P.map(r=>r.week))].map(w=>`<option>${w}</option>`).join('')}</select></div><div id="r1"></div></div>
 <div class="card"><h2>Stack pairs (team-games)</h2><div id="r2"></div></div>`;
 const ks=Object.keys(P[0]).filter(k=>!['key','box'].includes(k));const cov=ks.map(k=>({field:k,non_null:P.filter(r=>r[k]!=null).length})).sort((a,b)=>a.non_null-b.non_null);
 chart($('#r0'),{grid:{left:130,right:20,top:10,bottom:30},tooltip:{},xAxis:{type:'value',max:P.length},yAxis:{type:'category',data:cov.map(c=>c.field),axisLabel:{fontSize:9}},series:[{type:'bar',data:cov.map(c=>c.non_null)}]},cov,'coverage');$('#r0').style.height=(cov.length*14+60)+'px';charts.at(-1).resize();
 const draw=()=>{const w=$('#rw').value;$('#r1').innerHTML='';put('#r1',table(w?P.filter(r=>String(r.week)===w):P,{name:'player_games'+(w?'_w'+w:''),cols:['week','game_id','player','team','opp','pos',...ks.filter(k=>!['week','game_id','player','team','opp','pos'].includes(k))],ps:25}))};$('#rw').addEventListener('change',draw);draw();
 put('#r2',table(D.stacks.pairs,{name:'stack_pairs',ps:15}))};
// ---------------- router
function route(){const h=(location.hash||'#overview').slice(1).split('?')[0];const k=S[h]?h:'overview';charts.splice(0).forEach(c=>c.dispose());TID=0;
 document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+k));try{S[k]()}catch(e){app.innerHTML=`<div class="card">Error: ${esc(e.message)}</div>`;console.error(e)}scrollTo(0,0)}
$('#theme').onclick=()=>{const t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;localStorage.theme=t;route()};
if(localStorage.theme)document.documentElement.dataset.theme=localStorage.theme;
Promise.all(FILES.map(f=>fetch(f+'.json?v='+Date.now()).then(r=>r.json()).then(j=>D[f]=j))).then(()=>{$('#upd').textContent='Updated '+(D.players.updated||'');addEventListener('hashchange',route);route()}).catch(e=>app.innerHTML=`<div class="card">Could not load data: ${esc(e.message)}</div>`);
