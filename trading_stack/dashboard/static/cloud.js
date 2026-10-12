/* API integration only: the approved visual design remains in dashboard.css. */
const legacyRender = renderSnapshot;
const legacyFind = findTrade;
const legacyTable = renderTradeTable;
const legacyInspector = renderInspector;
const cloudChart = { timeframe:'1h', count:80, end:null, request:0 };
findTrade = function(id) {
  const c=state.snapshot?.cloud;
  return c ? [...c.open_trades,...c.closed_trades].find(t=>tradeId(t)===String(id)) : legacyFind(id);
};
renderTradeTable = function() {
  const d=state.snapshot;
  if(!d?.cloud) return legacyTable();
  const original=d.crypto;
  d.crypto={...original,open_trades:d.cloud.open_trades,closed_trades:d.cloud.closed_trades};
  legacyTable(); d.crypto=original;
  document.querySelectorAll('#cryptoTradeTable .trade-row').forEach(row=>{
    const t=findTrade(row.dataset.tradeId); const cell=row.querySelector('td:nth-child(3) strong');
    if(t&&cell) cell.textContent=`${t.market.toUpperCase()} · ${t.pair}`;
    row.tabIndex=0; row.setAttribute('role','button');
    row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openTrade(row.dataset.tradeId);}});
  });
};
renderSnapshot = function(d) {
  legacyRender(d); if(!d.cloud)return;
  const c=d.cloud,p=c.portfolio;
  $('stockPnl').textContent=p.marks_stale?'—':money(p.net_pnl);
  $('stockPnl').className=`kpi-number ${cssPnL(p.net_pnl)}`;
  $('stockPnlSub').textContent=`${money(p.realized)} realized · ${money(p.unrealized)} unrealized${p.marks_stale?' · stale marks':''}`;
  $('stockEquity').textContent=p.marks_stale?`${money(p.equity)}*`:money(p.equity);
  $('stockCash').textContent=`Cash ${money(p.cash)} · Reserved ${money(p.reserved)}${p.marks_stale?' · last-known marks':''}`;
  $('closedTrades').textContent=c.closed_trades.length;
  $('closedTradesSub').textContent=`${c.open_trades.length} open · ${money(p.realized)} realized`;
  $('marketState').textContent=c.providers.stocks?.clock ? (d.stocks.clock.is_open?'OPEN':'CLOSED') : 'UNKNOWN';
  $('stockAccount').innerHTML=[['Broker',c.providers.stocks?.mode||'ALPACA PAPER'],['State',c.providers.stocks?.status||'BLOCKED'],
    ['Broker buying power',money(d.stocks.account?.buying_power)],['Shared virtual capital','$500.00'],['Shared free cash',money(p.available_cash)],['Blocker',c.providers.stocks?.reason||'None']]
    .map(([k,v])=>`<div class="account-line"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
  $('managedStockPositions').innerHTML=c.open_trades.filter(t=>t.market==='stocks').map(t=>tradeButton(t)).join('') || `<div class="empty">${esc(c.providers.stocks?.reason||c.providers.stocks?.status||'Awaiting broker connection')}</div>`;
  $('paperReleaseBar').hidden=false;
  $('paperReleaseTitle').textContent=`CLOUD PAPER · ${c.status}`;
  $('paperReleaseMeta').textContent=`Started ${shortTime(c.started_at)} · ${(c.elapsed_seconds/3600).toFixed(1)}h elapsed · ends ${shortTime(c.deadline)} · ${d.crypto.config.timeframe} candles · ${(c.config_revisions||[]).length} revisions · config ${c.config_hash.slice(0,12)}`;
  $('paperLegacyTitle').textContent='EXPERIMENTAL';$('paperLegacyMeta').textContent='No demonstrated edge · separate V11 ledger preserved';
  $('paperScanStats').textContent=`${c.cycles} cycles · last cycle ${shortTime(c.last_cycle)} · ${c.evidence}`;
  $('paperReleaseDiagnostics').innerHTML=c.diagnostics.map(v=>`<div><strong>${esc(v.market.toUpperCase())} · ${esc(v.pair)}</strong><span>${esc(v.reason||v.execution)}</span></div>`).join('')+(c.opportunities||[]).map(o=>`<details class="cloud-details"><summary>${esc(o.slug)} · ${esc(o.direction)} · ${pct(Number(o.net_edge))} modeled edge · research only</summary><pre class="cloud-evidence">${esc(JSON.stringify(o,null,2))}</pre></details>`).join('');
  document.querySelector('.paper-release-links').innerHTML='<a href="/api/export">Export campaign</a><a href="#kalshi">Kalshi</a><a href="#system">Controls</a>';
  $('healthGrid').innerHTML=[['Worker',c.status],['Heartbeat',shortTime(c.heartbeat)],['Crypto',c.providers.crypto?.status],['Stocks',c.providers.stocks?.status],['Kalshi',c.providers.kalshi?.status],...(c.providers.dex?[['New-token scanner',c.providers.dex.status]]:[]),['Last backup',c.backup_error||(c.last_backup?shortTime(c.last_backup*1000):'Pending')],['Maximum drawdown',pct(Math.max(0,...c.equity_curve.map(v=>v.drawdown)))],['Costs booked',money(p.fees)]]
    .map(([k,v])=>`<div class="health-item"><span>${esc(k)}</span><strong>${esc(v||'UNKNOWN')}</strong></div>`).join('');
  $('kalshiMode').textContent=c.providers.kalshi?.mode||'PUBLIC DATA / EXECUTION BLOCKED';
  $('kalshiStatus').textContent=c.providers.kalshi?.status||'BLOCKED';
  if(c.providers.polymarket)$('healthGrid').innerHTML+=`<div class="health-item"><span>PredictArb research</span><strong>${esc(c.providers.polymarket.status)}</strong></div>`;
  if(c.integrations?.omniquant)$('healthGrid').innerHTML+=`<div class="health-item"><span>OmniQuant regime</span><strong>${esc(c.integrations.omniquant)}</strong></div>`;
  $('kalshiPositions').innerHTML=c.open_trades.filter(t=>t.market==='kalshi').map(tradeButton).join('')||'<div class="empty">No open prediction contracts.</div>';
  $('kalshiDiscovery').textContent=[c.providers.kalshi?.reason||'',...c.diagnostics.filter(d=>d.market==='kalshi').map(d=>d.reason),...(c.providers.kalshi?.discovery||[]).map(m=>`${m.ticker}: ${m.title} · ${m.status} · closes ${shortTime(m.close_time)}`)].join(' | ');
  document.querySelectorAll('[data-cloud-trade]').forEach(el=>el.addEventListener('click',()=>openTrade(el.dataset.cloudTrade)));
  const resume=document.querySelector('[data-control="resume"]');resume.disabled=!!(c.halt||c.emergency);
  drawCloudEquity(c.equity_curve);
};
function tradeButton(t) {
  return `<button class="other-row cloud-trade-button" data-cloud-trade="${esc(tradeId(t))}"><div><span>${esc(t.mode)}</span><strong>${esc(t.pair)}</strong></div><div><span>Quantity</span><strong>${qty(t.amount)}</strong></div><div><span>Net P&amp;L</span><strong class="${cssPnL(t.profit_abs)}">${money(t.profit_abs)}</strong></div></button>`;
}
function drawCloudEquity(rows) {
  const svg=$('performanceChart');if(!rows.length){svg.innerHTML='';$('performanceNow').textContent='No recorded cycle yet';return;}
  const lo=Math.min(...rows.map(r=>r.equity)),hi=Math.max(...rows.map(r=>r.equity));const span=Math.max(hi-lo,1);
  const points=rows.map((r,i)=>`${20+i/Math.max(rows.length-1,1)*480},${190-(r.equity-lo)/span*160}`).join(' ');
  svg.innerHTML=`<polyline points="${points}" fill="none" stroke="#2ad8ff" stroke-width="2"/><text x="20" y="18" fill="#8299b0" font-size="12">${money(hi)}</text><text x="20" y="215" fill="#8299b0" font-size="12">${money(lo)} · ${esc(shortTime(rows[0].at*1000))}</text>`;
  $('performanceNow').textContent=money(rows.at(-1).equity);
}
renderInspector = function(t,openChart=true) {
  if(!state.snapshot?.cloud)return legacyInspector(t,openChart);
  const native=state.snapshot.crypto?.config?.timeframe;
  if(t.market==='crypto'&&['15m','4h'].includes(native)&&cloudChart.timeframe==='1h')cloudChart.timeframe=native;
  if(t.market==='stocks'&&cloudChart.timeframe==='15m')cloudChart.timeframe='1h';
  legacyInspector(t,false);
  $('detailSide').textContent=`${t.market==='kalshi'?'YES contract':'Long'} · ${t.mode}`;
  $('executionMetrics').innerHTML += [metric('Execution mode',esc(t.mode)),metric('Signal timestamp',shortTime(t.signal_time)),
    metric('Fee source',esc(t.fee_basis)),metric('Booked fees',money(t.paid_fees)),metric('Estimated exit fee',money(t.estimated_exit_fee)),
    metric('Slippage assumption',pct(t.slippage_fraction)),metric('Trailing stop',price(t.trailing_stop)),
    ...(t.time_exit_at?[metric('Time exit at',shortTime(t.time_exit_at)),metric('Exit rule',esc(t.exit_logic)),metric('Net profit exit threshold',pct(t.net_take_profit_fraction))]:[])].join('');
  $('closePaperPosition').hidden=!t.is_open;
  $('orderEvidence').textContent=JSON.stringify({orders:t.orders,fills:t.fills,settlement:t.settlement,probability_evidence:t.contract?.estimate},null,2);
  $('historyTimeline').innerHTML=(t.fills||[]).map(f=>`<div class="timeline-event"><strong>${esc(f.action.toUpperCase())} · ${qty(f.quantity)} @ ${price(f.price)}</strong><span>${shortTime(f.at*1000)} · ${esc(f.time_basis||"recorded execution")} · order ${esc(f.order_id)} · fee ${money(f.fee)}</span></div>`).join('');
  if(t.settlement)$('historyTimeline').innerHTML+=`<div class="timeline-event"><strong>Exchange settlement</strong><span>${esc(JSON.stringify(t.settlement))}</span></div>`;
  const timeframes=t.market==='crypto'&&native==='15m'?['15m','1h','4h','1d']:['1h','4h','1d'];
  const group=document.querySelector('.tf-group');group.innerHTML=timeframes.map(tf=>`<button class="tf ${tf===cloudChart.timeframe?'active':''}" data-cloud-tf="${tf}">${tf}</button>`).join('')+'<span class="cloud-chart-nav"><button data-pan="-1" aria-label="Earlier candles">←</button><button data-zoom="-1" aria-label="Zoom in">＋</button><button data-zoom="1" aria-label="Zoom out">−</button><button data-pan="1" aria-label="Later candles">→</button></span>';
  group.querySelectorAll('[data-cloud-tf]').forEach(b=>b.addEventListener('click',()=>{cloudChart.timeframe=b.dataset.cloudTf;cloudChart.end=null;group.querySelectorAll('[data-cloud-tf]').forEach(x=>x.classList.toggle('active',x===b));fetchCandles(t);}));
  group.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{cloudChart.count=Math.max(15,Math.min(300,cloudChart.count+Number(b.dataset.zoom)*20));drawCandles(state.candles,t);}));
  group.querySelectorAll('[data-pan]').forEach(b=>b.addEventListener('click',()=>{cloudChart.end=Math.max(Math.min(cloudChart.count,state.candles.length),Math.min(state.candles.length,(cloudChart.end??state.candles.length)+Number(b.dataset.pan)*20));drawCandles(state.candles,t);}));
  if(openChart){cloudChart.end=null;switchTab('chart');fetchCandles(t);}
};
fetchCandles = async function(t) {
  const seq=++cloudChart.request;const tf=cloudChart.timeframe;
  $('candleState').textContent='Loading recorded market data…';state.candles=[];
  try{
    const params=new URLSearchParams({market:t.market,pair:t.pair,timeframe:tf,trade_id:tradeId(t)});
    const response=await fetch(`/api/candles?${params}`,{cache:'no-store'});const data=await response.json();
    if(seq!==cloudChart.request||tradeId(state.selectedTrade)!==tradeId(t))return;
    if(!response.ok)throw Error(data.error||'Market data unavailable');
    state.candles=data.candles||[];
    state.contractQuotes=data.quotes||[];
    $('candleState').textContent=t.market==='dex'?'Observed DEX exit quotes · simulated fill markers · no fabricated candlesticks':t.market==='kalshi'?`Contract price / settlement · ${t.contract?.market?.title||t.pair} · closes ${shortTime(t.contract?.market?.close_time)} · ${t.settlement?'SETTLED':'Payout pending until exchange settlement'}`:`${state.candles.length} stored ${tf} bars · hover for OHLC · markers are recorded fills; off-chart fills remain in History`;
    drawCandles(state.candles,t);
  }catch(e){if(seq===cloudChart.request){$('candleState').textContent=e.message;drawCandles([],t);}}
};
drawCandles = function(rows,t) {
  if(t.market==='kalshi'||t.market==='dex'){
    const fills=t.fills||[],quotes=state.contractQuotes||[],times=[...fills,...quotes].map(v=>v.at);
    if(!times.length){$('candleChart').innerHTML='<text x="40" y="210" fill="#8299b0">No observed contract quotes or executions</text>';return;}
    const first=Math.min(...times),last=Math.max(...times),x=at=>40+(at-first)/Math.max(1,last-first)*730;
    const prices=[...fills.map(f=>f.price),...quotes.flatMap(q=>[q.bid,q.ask])];
    const floor=t.market==='dex'?Math.min(...prices)*.95:0,ceiling=t.market==='dex'?Math.max(...prices)*1.05:1;
    const y=p=>370-(p-floor)/Math.max(1e-12,ceiling-floor)*320;
    const line=field=>quotes.map(q=>`${x(q.at)},${y(q[field])}`).join(' ');
    $('candleChart').innerHTML=(t.market==='dex'?['bid']:['bid','ask']).map((field,i)=>`<polyline data-contract-quote="${field}" points="${line(field)}" fill="none" stroke="${i?'#8299b0':'#2ad8ff'}" stroke-width="1.5"/>`).join('')+
      fills.map(f=>`<circle data-fill-marker="${esc(f.action)}" cx="${x(f.at)}" cy="${y(f.price)}" r="5" fill="${f.action==='buy'?'#2ce390':'#ff506c'}"><title>${esc(f.action)} ${price(f.price)} · ${esc(shortTime(f.at*1000))}</title></circle>`).join('')+
      `<text x="20" y="20" fill="#8299b0">${t.market==='dex'?'Observed exit quotes and simulated fills · USDC valued at $1':'Observed YES bid (blue), ask (gray), executions · $0 to $1'}</text><text x="30" y="410" fill="#8299b0" font-size="10">${esc(shortTime(first*1000))} — ${esc(shortTime(last*1000))}</text>`;
    return;
  }
  if(!rows.length){$('candleChart').innerHTML='<text x="40" y="210" fill="#8299b0">No recorded bars in this range. No chart is fabricated.</text>';return;}
  const end=Math.min(cloudChart.end??rows.length,rows.length);const visible=rows.slice(Math.max(0,end-cloudChart.count),end);
  const bounds=[...visible.flatMap(r=>[r.low,r.high]),t.stop_price,t.target_price,t.open_rate].filter(v=>v!=null&&Number.isFinite(Number(v)));
  const min=Math.min(...bounds),max=Math.max(...bounds),span=Math.max(max-min,max*.002);const lo=min-span*.08,hi=max+span*.08;
  const x=i=>24+(i+.5)/visible.length*760;const y=v=>20+(hi-v)/(hi-lo)*350;const width=Math.max(1,Math.min(10,700/visible.length));
  let out='';for(let i=0;i<=5;i++){const yy=20+i*70;out+=`<line x1="24" x2="788" y1="${yy}" y2="${yy}" stroke="#16304a"/><text x="797" y="${yy+4}" fill="#8299b0" font-size="10">${price(hi-i*(hi-lo)/5)}</text>`;}
  visible.forEach((r,i)=>{const c=r.close>=r.open?'#2ce390':'#ff506c';out+=`<g><title>${esc(shortTime(r.time*1000))} O ${price(r.open)} H ${price(r.high)} L ${price(r.low)} C ${price(r.close)} V ${qty(r.volume)}</title><line x1="${x(i)}" x2="${x(i)}" y1="${y(r.high)}" y2="${y(r.low)}" stroke="${c}"/><rect x="${x(i)-width/2}" y="${Math.min(y(r.open),y(r.close))}" width="${width}" height="${Math.max(1,Math.abs(y(r.open)-y(r.close)))}" fill="${c}"/></g>`;});
  [[t.open_rate,'Entry','#2ad8ff'],[t.stop_price,'Stop','#ff506c'],[t.target_price,'Target','#2ce390']].forEach(([v,label,color])=>{if(v!=null)out+=`<line x1="24" x2="788" y1="${y(v)}" y2="${y(v)}" stroke="${color}" stroke-dasharray="4 4"/><text x="710" y="${y(v)-4}" fill="${color}" font-size="10">${label}</text>`;});
  const seconds={'15m':900,'1h':3600,'4h':14400,'1d':86400}[cloudChart.timeframe];
  (t.fills||[]).forEach(f=>{const i=visible.findIndex(r=>r.time<=f.at&&f.at<r.time+seconds);if(i<0)return;out+=`<circle data-fill-marker="${esc(f.action)}" cx="${x(i)}" cy="${y(f.price)}" r="5" fill="${f.action==='buy'?'#2ce390':'#ff506c'}" stroke="#fff"><title>${esc(f.action.toUpperCase())} ${qty(f.quantity)} @ ${price(f.price)} · ${esc(shortTime(f.at*1000))}</title></circle>`;});
  out+=`<text x="24" y="410" fill="#8299b0" font-size="10">${esc(shortTime(visible[0].time*1000))}</text><text x="590" y="410" fill="#8299b0" font-size="10">${esc(shortTime(visible.at(-1).time*1000))}</text>`;
  $('candleChart').innerHTML=out;
};
async function paperControl(action,trade_id=null) {
  if(action==='flatten'&&!confirm('Pause entries, cancel pending entries, and queue closure of every campaign paper/demo position? Exits wait for fresh data and an open venue.'))return;
  if(action==='close'&&!confirm('Queue closure of this paper/demo position at the next executable price?'))return;
  try{
    const r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.snapshot.cloud.csrf_token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({action,trade_id})});
    const result=await r.json();if(!r.ok)throw Error(result.error||'Control failed');
    $('controlMessage').textContent=`${action} queued (#${result.command_id}). Waiting for worker acknowledgement.`;
    if(action==='close')closeTradeModal();await refresh();
  }catch(e){$('controlMessage').textContent=e.message;}
}
document.querySelectorAll('[data-control]').forEach(b=>b.addEventListener('click',()=>paperControl(b.dataset.control)));
$('closePaperPosition').addEventListener('click',()=>paperControl('close',tradeId(state.selectedTrade)));
