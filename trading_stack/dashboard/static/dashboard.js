const state = {
  snapshot: null,
  tradeFilter: 'open',
  selectedTrade: null,
  pnlHistory: [],
  candles: [],
};

const $ = (id) => document.getElementById(id);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function n(value, fallback = 0) {
  const v = Number(value);
  return Number.isFinite(v) ? v : fallback;
}
function money(value, digits = 2) {
  const v = n(value);
  return `${v < 0 ? '-' : ''}$${Math.abs(v).toFixed(digits)}`;
}
function pct(value, digits = 2) {
  const v = n(value) * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
}
function price(value) {
  const v = n(value);
  if (!v) return '—';
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, {maximumFractionDigits: 2});
  if (Math.abs(v) >= 1) return v.toLocaleString(undefined, {maximumFractionDigits: 5});
  return v.toLocaleString(undefined, {maximumFractionDigits: 8});
}
function qty(value) {
  const v = n(value);
  if (!v) return '—';
  if (Math.abs(v) >= 10) return v.toLocaleString(undefined, {maximumFractionDigits: 4});
  return v.toLocaleString(undefined, {maximumFractionDigits: 8});
}
function cssPnL(value) {
  return n(value) > 0 ? 'positive' : n(value) < 0 ? 'negative' : 'neutral';
}
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (m) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[m]));
}
function shortTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString([], {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'});
}
function tradeId(trade) {
  return String(trade?.trade_id ?? trade?.id ?? '');
}
function sideText(trade) {
  return trade?.is_short ? 'Short' : 'Long';
}

function initializeStarfield() {
  const canvas = $('starfield');
  const ctx = canvas.getContext('2d');
  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  let stars = [];

  function resize() {
    canvas.width = innerWidth * DPR;
    canvas.height = innerHeight * DPR;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    stars = Array.from({length: Math.min(120, Math.floor(innerWidth / 10))}, () => ({
      x: Math.random() * innerWidth,
      y: Math.random() * innerHeight,
      r: Math.random() * 1.1 + .2,
      a: Math.random() * .35 + .08,
      s: Math.random() * .08 + .02,
    }));
  }

  function frame() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (const star of stars) {
      star.y += star.s;
      if (star.y > innerHeight + 3) star.y = -3;
      ctx.beginPath();
      ctx.fillStyle = `rgba(126,205,255,${star.a})`;
      ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  resize();
  addEventListener('resize', resize);
  requestAnimationFrame(frame);
}

function setStatus(el, label, ok) {
  el.innerHTML = `<i class="light ${ok ? 'good' : 'bad'}"></i>${esc(label)}`;
}

function renderKPIs(d) {
  const c = d.crypto;
  const s = d.stocks;
  const openPnl = n(c.open_pnl_usd);
  const exposure = n(c.open_exposure_usd);
  const totalSlots = n(d.safety.crypto_max_open_trades, 4);
  const openCount = n(c.open_trade_count);
  const openPct = exposure ? openPnl / exposure : 0;

  $('cryptoPnl').textContent = money(openPnl);
  $('cryptoPnl').className = `kpi-number ${cssPnL(openPnl)}`;
  $('cryptoPnlPct').textContent = `${pct(openPct)} · ${openCount} open`;
  $('cryptoPnlPct').className = `kpi-foot ${cssPnL(openPnl)}`;
  $('cryptoExposure').textContent = money(exposure);
  $('cryptoSlots').textContent = `${openCount} / ${totalSlots} positions used`;
  const used = totalSlots ? Math.min(openCount / totalSlots, 1) : 0;
  document.documentElement.style.setProperty('--ring', `${used * 360}deg`);
  $('cryptoRingText').textContent = `${Math.round(used * 100)}%`;

  $('stockEquity').textContent = money(s.account?.equity);
  $('stockCash').textContent = `Available ${money(s.account?.cash)}`;
  $('stockPnl').textContent = money(s.managed_unrealized_pnl_usd);
  $('stockPnl').className = `kpi-number ${cssPnL(s.managed_unrealized_pnl_usd)}`;
  $('stockPnlSub').textContent = s.managed_positions?.length ? `${s.managed_positions.length} managed position(s)` : 'No open positions';

  const closed = Number(c.profit?.closed_trade_count ?? c.closed_trade_count ?? 0);
  $('closedTrades').textContent = String(closed);
  $('closedTradesSub').textContent = `${openCount} open · ${closed} closed · ${money(c.closed_pnl_usd)} realized`;

  const marketOpen = !!s.clock?.is_open;
  $('marketState').textContent = marketOpen ? 'OPEN' : 'CLOSED';
  $('marketState').className = `kpi-number ${marketOpen ? 'positive' : 'neutral'}`;
  $('marketNext').textContent = marketOpen ? `Next close ${shortTime(s.clock?.next_close)}` : `Next open ${shortTime(s.clock?.next_open)}`;

  state.pnlHistory.push(openPnl);
  if (state.pnlHistory.length > 80) state.pnlHistory.shift();
  drawMicroChart();
  drawPerformanceChart();
}

function drawMicroChart() {
  const points = state.pnlHistory;
  if (!points.length) return;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const xy = points.map((v, i) => {
    const x = points.length === 1 ? 80 : i / (points.length - 1) * 160;
    const y = 29 - ((v - min) / span) * 22;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  $('kpiPnlLine').setAttribute('points', xy);
}

function drawPerformanceChart() {
  const svg = $('performanceChart');
  const values = state.pnlHistory;
  if (!values.length) return;
  const W = 520, H = 220, left = 34, right = 12, top = 15, bottom = 24;
  let min = Math.min(...values, 0), max = Math.max(...values, 0);
  const pad = Math.max((max - min) * .25, .05);
  min -= pad; max += pad;
  const span = max - min || 1;
  const x = (i) => left + (values.length === 1 ? (W-left-right)/2 : i/(values.length-1)*(W-left-right));
  const y = (v) => top + (max-v)/span*(H-top-bottom);

  let grid = '';
  for (let i=0;i<5;i++) {
    const yy = top + i*(H-top-bottom)/4;
    const val = max - i*span/4;
    grid += `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="rgba(80,150,205,.10)"/>`;
    grid += `<text x="2" y="${yy+3}" fill="#526d88" font-size="8">${val.toFixed(2)}</text>`;
  }
  const pts = values.map((v,i)=>`${x(i)},${y(v)}`).join(' ');
  const last = values.at(-1);
  const color = last >= 0 ? '#2ce390' : '#ff506c';
  const area = `${left},${y(0)} ${pts} ${x(values.length-1)},${y(0)}`;
  svg.innerHTML = `${grid}<polygon points="${area}" fill="${last>=0?'rgba(44,227,144,.06)':'rgba(255,80,108,.07)'}"/><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/><circle cx="${x(values.length-1)}" cy="${y(last)}" r="3.5" fill="${color}"/>`;
  $('performanceNow').textContent = money(last);
  $('performanceNow').className = `chart-current ${cssPnL(last)}`;
}

function renderEngine(d) {
  const c = d.crypto;
  const running = String(c.bot_state || '').toUpperCase() === 'RUNNING';
  $('cryptoSubtitle').textContent = `Automated crypto trading (PAPER) · ${c.open_trade_count} open position${c.open_trade_count === 1 ? '' : 's'}`;
  setStatus($('cryptoStatusChip'), running ? 'RUNNING' : String(c.bot_state || 'UNKNOWN').toUpperCase(), running);
  $('metaExchange').textContent = c.config?.exchange || '—';
  $('metaMode').textContent = c.config?.runmode || '—';
  $('metaStrategy').textContent = c.config?.strategy || '—';
  $('metaTimeframe').textContent = c.config?.timeframe || '—';
  $('cryptoTopMeta').textContent = `${c.config?.exchange || 'Kraken'} · ${c.config?.runmode || 'Dry Run'}`;
  setStatus($('cryptoTopStatus'), running ? 'Running' : 'Degraded', running);

  const cards = c.open_trades || [];
  $('cryptoCards').innerHTML = cards.length ? cards.map((trade) => {
    const pnl = n(trade.profit_abs);
    const symbol = esc(trade.pair);
    const tag = esc(trade.enter_tag || 'signal');
    return `<article class="trade-card" tabindex="0" role="button" data-trade-id="${esc(tradeId(trade))}">
      <div class="trade-card-top"><div class="trade-symbol-wrap"><div class="coin-badge">${symbol.startsWith('BTC')?'₿':symbol.startsWith('DOGE')?'Ð':symbol.startsWith('XRP')?'X':'●'}</div><div><div class="trade-symbol">${symbol}</div><div class="trade-side">${sideText(trade)} · ${money(trade.stake_amount)} stake</div></div></div><span class="signal-tag">${tag}</span></div>
      <div class="trade-metrics">
        <div><div class="metric-label">Entry</div><div class="metric-value">${price(trade.open_rate)}</div></div>
        <div><div class="metric-label">Current</div><div class="metric-value">${price(trade.current_rate)}</div></div>
        <div><div class="metric-label">Open P&amp;L</div><div class="metric-value ${cssPnL(pnl)}">${money(pnl)}</div></div>
        <div><div class="metric-label">Return</div><div class="metric-value ${cssPnL(trade.profit_ratio)}">${pct(trade.profit_ratio)}</div></div>
      </div>
      <div class="trade-mini"><svg viewBox="0 0 180 25"><polyline points="0,16 18,13 36,15 54,10 72,14 90,9 108,12 126,8 144,12 162,7 180,10" fill="none" stroke="${pnl>=0?'#2ce390':'#ff506c'}" stroke-width="1.5"/></svg></div>
      <button class="view-trade" type="button">◉ View Trade &nbsp;→</button>
    </article>`;
  }).join('') : `<div class="empty">No open crypto positions. The engine remains active and scanning.</div>`;

  $$('.trade-card').forEach((card) => {
    const open = () => openTrade(card.dataset.tradeId);
    card.addEventListener('click', open);
    card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
}

function renderStocks(d) {
  const s = d.stocks;
  const active = s.account?.status === 'ACTIVE';
  setStatus($('stockStatusChip'), active ? 'ACTIVE' : (s.account?.status || 'UNKNOWN'), active);
  setStatus($('stockTopStatus'), active ? 'Active' : 'Degraded', active);

  const accountFields = [
    ['Account Blocked', String(s.account?.account_blocked ?? '—')],
    ['Buying Power', money(s.account?.buying_power)],
    ['Cash', money(s.account?.cash)],
    ['Equity', money(s.account?.equity)],
    ['Trading Blocked', String(s.account?.trading_blocked ?? '—')],
    ['Status', s.account?.status || '—'],
  ];
  $('stockAccount').innerHTML = accountFields.map(([k,v]) => `<div class="account-line"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');

  const managed = s.managed_positions || [];
  $('managedStockPositions').innerHTML = managed.length ? managed.map((p) => `<div class="other-row"><div><span>Symbol</span><strong>${esc(p.symbol)}</strong></div><div><span>Market Value</span><strong>${money(p.market_value)}</strong></div><div><span>Unrealized</span><strong class="${cssPnL(p.unrealized_pl)}">${money(p.unrealized_pl)}</strong></div></div>`).join('') : `<div class="empty">No managed stock positions. The stock bot is waiting for the regular U.S. session.</div>`;

  const other = s.other_positions || [];
  $('otherPositionCount').textContent = String(other.length);
  $('otherPositions').innerHTML = other.length ? other.map((p) => `<div class="other-row"><div><span>Symbol</span><strong>${esc(p.symbol)}</strong></div><div><span>Class</span><strong>${esc(p.asset_class)}</strong></div><div><span>Market Value</span><strong>${money(p.market_value)}</strong></div></div>`).join('') : `<div class="empty">No other PAPER positions.</div>`;
}

function tradeOutcome(trade) {
  if (trade?.is_open) return {label: 'OPEN', cls: 'open'};
  const pnl = n(trade?.profit_abs);
  const ratio = n(trade?.profit_ratio);
  if (pnl > 0 || (pnl === 0 && ratio > 0)) return {label: 'PROFIT', cls: 'win'};
  if (pnl < 0 || (pnl === 0 && ratio < 0)) return {label: 'LOSS', cls: 'loss'};
  return {label: 'FLAT', cls: 'flat'};
}

function setTradeFilter(filter, {scroll = false} = {}) {
  state.tradeFilter = filter;
  $('.segment').forEach((b) => b.classList.toggle('active', b.dataset.filter === filter));
  renderTradeTable();
  if (scroll) {
    const target = $('performance');
    target?.scrollIntoView({behavior: 'smooth', block: 'start'});
    target?.classList.remove('history-focus');
    requestAnimationFrame(() => target?.classList.add('history-focus'));
    setTimeout(() => target?.classList.remove('history-focus'), 1400);
  }
}

function renderTradeTable() {
  const c = state.snapshot?.crypto;
  if (!c) return;
  const openTrades = c.open_trades || [];
  const closedTrades = c.closed_trades || [];
  let rows = [];
  if (state.tradeFilter === 'open') rows = openTrades;
  else if (state.tradeFilter === 'closed') rows = closedTrades;
  else if (state.tradeFilter === 'winners') rows = closedTrades.filter((t) => tradeOutcome(t).cls === 'win');
  else if (state.tradeFilter === 'losers') rows = closedTrades.filter((t) => tradeOutcome(t).cls === 'loss');
  else rows = [...openTrades, ...closedTrades];

  const wins = closedTrades.filter((t) => tradeOutcome(t).cls === 'win').length;
  const losses = closedTrades.filter((t) => tradeOutcome(t).cls === 'loss').length;
  const flats = closedTrades.filter((t) => tradeOutcome(t).cls === 'flat').length;
  const decided = wins + losses;
  const winRate = decided ? wins / decided : 0;
  const realized = closedTrades.reduce((sum, t) => sum + n(t.profit_abs), 0);

  $('openCount').textContent = String(c.open_trade_count || 0);
  $('closedCount').textContent = String(c.profit?.closed_trade_count ?? c.closed_trade_count ?? 0);
  $('tradeSummary').innerHTML = [
    ['Closed', closedTrades.length],
    ['Profits', wins],
    ['Losses', losses],
    ['Flat', flats],
    ['Win rate', decided ? `${(winRate * 100).toFixed(1)}%` : '—'],
    ['Realized', money(realized)],
  ].map(([label, value]) => `<div><span>${esc(label)}</span><strong class="${label === 'Realized' ? cssPnL(realized) : ''}">${esc(value)}</strong></div>`).join('');

  if (!rows.length) {
    const label = state.tradeFilter === 'open' ? 'open' : state.tradeFilter === 'closed' ? 'closed' : state.tradeFilter;
    $('cryptoTradeTable').innerHTML = `<div class="empty">No ${esc(label)} crypto trades to show.</div>`;
    return;
  }
  $('cryptoTradeTable').innerHTML = `<table><thead><tr><th>#</th><th>Result</th><th>Market</th><th>Side</th><th>Stake</th><th>Entry</th><th>Current / Exit</th><th>P&amp;L</th><th>Return</th><th>Opened</th><th>Closed</th><th>Exit Reason</th></tr></thead><tbody>${rows.map((t, i) => {
    const outcome = tradeOutcome(t);
    return `<tr class="trade-row" data-trade-id="${esc(tradeId(t))}"><td>${i+1}</td><td><span class="result-badge ${outcome.cls}">${outcome.label}</span></td><td><strong>CRYPTO · ${esc(t.pair)}</strong></td><td class="positive">${sideText(t)}</td><td>${money(t.stake_amount)}</td><td>${price(t.open_rate)}</td><td>${price(t.is_open ? t.current_rate : t.close_rate)}</td><td class="${cssPnL(t.profit_abs)}">${money(t.profit_abs)}</td><td class="${cssPnL(t.profit_ratio)}">${pct(t.profit_ratio)}</td><td>${shortTime(t.open_date)}</td><td>${t.is_open ? '—' : shortTime(t.close_date)}</td><td>${esc(t.is_open ? 'Still open' : (t.exit_reason || '—'))}</td></tr>`;
  }).join('')}</tbody></table>`;
  $('.trade-row').forEach((row) => row.addEventListener('click', () => openTrade(row.dataset.tradeId)));
}

function renderOrders() {
  const rows = state.snapshot?.stocks?.recent_orders || [];
  if (!rows.length) {
    $('stockOrders').innerHTML = `<div class="empty">No recent stock orders. The broker connection is active; nothing is being invented here.</div>`;
    return;
  }
  $('stockOrders').innerHTML = `<table><thead><tr><th>#</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Type</th><th>Status</th><th>Fill</th><th>Created</th></tr></thead><tbody>${rows.map((o,i)=>`<tr><td>${i+1}</td><td><strong>${esc(o.symbol)}</strong></td><td>${esc(o.side)}</td><td>${qty(o.qty || o.filled_qty)}</td><td>${esc(o.type)}</td><td>${esc(o.status)}</td><td>${price(o.filled_avg_price)}</td><td>${shortTime(o.created_at)}</td></tr>`).join('')}</tbody></table>`;
}

function renderHealth(d) {
  const values = [
    ['Dashboard', d.system.dashboard],
    ['Crypto Engine', d.system.crypto_engine],
    ['Stock Broker', d.system.stock_broker],
    ['Live Trading', d.safety.live_trading ? 'ENABLED' : 'DISABLED'],
  ];
  $('healthGrid').innerHTML = values.map(([k,v]) => `<div class="health-item"><span>${esc(k)}</span><strong class="${String(v).includes('ONLINE') || String(v).includes('DISABLED') ? 'positive' : ''}">${esc(v)}</strong></div>`).join('');
  $('safetyConfig').innerHTML = `<div class="safety-list">${Object.entries(d.safety || {}).map(([k,v]) => `<div class="safety-line"><span>${esc(k.replaceAll('_',' '))}</span><strong>${esc(v)}</strong></div>`).join('')}</div>`;
  const errors = [...(d.crypto.errors || []), ...(d.stocks.errors || [])];
  $('runtimeErrors').innerHTML = errors.length ? `<details open><summary class="negative">Runtime warnings (${errors.length})</summary><pre>${esc(errors.join('\n'))}</pre></details>` : '';
}

function renderSnapshot(d) {
  state.snapshot = d;
  $('updatedAt').textContent = new Date(d.generated_at).toLocaleTimeString();
  renderKPIs(d);
  renderEngine(d);
  renderStocks(d);
  renderTradeTable();
  renderOrders();
  renderHealth(d);

  if (state.selectedTrade) {
    const found = findTrade(tradeId(state.selectedTrade));
    if (found) {
      state.selectedTrade = found;
      renderInspector(found, false);
    }
  }
}

function findTrade(id) {
  const c = state.snapshot?.crypto;
  if (!c) return null;
  return [...(c.open_trades || []), ...(c.closed_trades || [])].find((t) => tradeId(t) === String(id)) || null;
}

function metric(label, value, cls='') {
  return `<div class="detail-item"><span>${esc(label)}</span><strong class="${cls}">${value}</strong></div>`;
}

function renderInspector(trade, openChart = true) {
  if (!trade) return;
  state.selectedTrade = trade;
  $('tradeModalTitle').textContent = `Trade Detail // ${trade.pair}`;
  $('modalCoin').textContent = trade.pair?.startsWith('BTC') ? '₿' : trade.pair?.startsWith('DOGE') ? 'Ð' : trade.pair?.startsWith('XRP') ? 'X' : '●';
  setStatus($('modalStatus'), trade.is_open ? 'OPEN' : 'CLOSED', !!trade.is_open);
  $('detailPair').textContent = trade.pair || '—';
  $('detailSide').textContent = `${sideText(trade)} · ${money(trade.stake_amount)} stake`;
  $('detailPnlLabel').textContent = trade.is_open ? 'OPEN P&L' : 'REALIZED P&L';
  $('detailPnl').textContent = money(trade.profit_abs);
  $('detailPnl').className = cssPnL(trade.profit_abs);
  $('detailPnlPct').textContent = pct(trade.profit_ratio);
  $('detailPnlPct').className = cssPnL(trade.profit_ratio);
  $('signalTag').textContent = trade.enter_tag || 'signal';
  $('signalReason').textContent = trade.signal_reason || '—';
  $('riskReward').textContent = trade.risk_reward ? `${n(trade.risk_reward).toFixed(2)} : 1` : '—';
  $('riskTarget').textContent = price(trade.target_price);
  $('riskEntry').textContent = price(trade.open_rate);
  $('riskStop').textContent = price(trade.stop_price);
  $('exitLogic').textContent = trade.exit_logic || '—';
  $('chartPair').textContent = trade.pair || '—';
  $('chartSide').textContent = sideText(trade);

  $('overviewMetrics').innerHTML = [
    metric('Entry Price', price(trade.open_rate)),
    metric(trade.is_open ? 'Current Price' : 'Exit Price', price(trade.is_open ? trade.current_rate : trade.close_rate)),
    metric('ROI Target', price(trade.target_price), 'positive'),
    metric('Stop Loss', price(trade.stop_price), 'negative'),
    metric('Position Size', `${qty(trade.amount)} · ${money(trade.stake_amount)}`),
    metric('Opened', shortTime(trade.open_date)),
  ].join('');

  $('executionMetrics').innerHTML = [
    metric('Trade ID', esc(tradeId(trade))),
    metric('Pair', esc(trade.pair)),
    metric('Status', trade.is_open ? 'OPEN' : 'CLOSED', trade.is_open ? 'positive' : 'neutral'),
    metric('Direction', sideText(trade), 'positive'),
    metric('Entry', price(trade.open_rate)),
    metric('Current / Exit', price(trade.is_open ? trade.current_rate : trade.close_rate)),
    metric('Target Rule', esc(trade.target_rule || '+0.40% ROI reference')),
    metric('Stop', price(trade.stop_price), 'negative'),
    metric('Signal Tag', esc(trade.enter_tag || '—')),
    metric('Open Time', shortTime(trade.open_date)),
    metric('Close Time', shortTime(trade.close_date)),
    metric('Exit Reason', esc(trade.exit_reason || 'Still open')),
  ].join('');

  const events = [
    ['Position opened', `${shortTime(trade.open_date)} · ${sideText(trade)} at ${price(trade.open_rate)}`],
    ['Signal', `${trade.enter_tag || 'signal'} · ${trade.signal_reason || 'No signal text available.'}`],
  ];
  if (trade.is_open) {
    events.push(['Position active', `Current ${price(trade.current_rate)} · P&L ${money(trade.profit_abs)} (${pct(trade.profit_ratio)})`]);
    events.push(['Exit conditions', trade.exit_logic || '—']);
  } else {
    events.push(['Position closed', `${shortTime(trade.close_date)} · ${price(trade.close_rate)} · ${trade.exit_reason || 'exit'}`]);
  }
  $('historyTimeline').innerHTML = events.map(([title, desc]) => `<div class="timeline-event"><strong>${esc(title)}</strong><span>${esc(desc)}</span></div>`).join('');

  if (openChart) {
    switchTab('chart');
    fetchCandles(trade);
  }
}

function openTrade(id) {
  const trade = findTrade(id);
  if (!trade) return;
  renderInspector(trade, true);
  $('tradeModal').classList.add('open');
  $('tradeModal').setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}
function closeTradeModal() {
  $('tradeModal').classList.remove('open');
  $('tradeModal').setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}
function switchTab(name) {
  $$('.tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
  if (name === 'chart' && state.selectedTrade && !state.candles.length) fetchCandles(state.selectedTrade);
}

async function fetchCandles(trade) {
  state.candles = [];
  $('candleState').textContent = 'Loading real 5m candles from the running Freqtrade engine…';
  $('candleChart').innerHTML = '';
  try {
    const url = `/api/candles?pair=${encodeURIComponent(trade.pair)}&timeframe=5m&limit=300`;
    const r = await fetch(url, {cache: 'no-store'});
    const data = await r.json();
    if (!r.ok || data.error && !data.candles?.length) throw new Error(data.error || `HTTP ${r.status}`);
    state.candles = data.candles || [];
    $('candleState').textContent = state.candles.length ? `${state.candles.length} live 5m candles · real engine data` : 'No candle rows returned by Freqtrade.';
    drawCandles(state.candles, trade);
  } catch (e) {
    $('candleState').textContent = `Candles unavailable: ${e.message}`;
    drawCandles([], trade);
  }
}

function candleTimeMs(value) {
  if (value == null) return NaN;
  if (typeof value === 'number') return value > 1e12 ? value : value * 1000;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return numeric > 1e12 ? numeric : numeric * 1000;
  return new Date(value).getTime();
}

function drawCandles(candles, trade) {
  const svg = $('candleChart');
  const W = 900, H = 430, left = 18, right = 78, top = 20, bottom = 45;
  if (!candles.length) {
    svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#58718b" font-size="13">No candle data returned. The dashboard will not fabricate a chart.</text>`;
    return;
  }

  const source = candles;
  const nearestIndex = (when) => {
    const target = new Date(when || 0).getTime();
    if (!Number.isFinite(target)) return -1;
    let best = -1, distance = Infinity;
    source.forEach((c, i) => {
      const t = candleTimeMs(c.time);
      if (Number.isFinite(t) && Math.abs(t - target) < distance) {
        best = i;
        distance = Math.abs(t - target);
      }
    });
    return best;
  };

  let visible = source.slice(-100);
  const openIndex = nearestIndex(trade.open_date);
  const closeIndex = trade.is_open ? source.length - 1 : nearestIndex(trade.close_date);
  if (openIndex >= 0 && closeIndex >= 0) {
    let start = Math.max(0, Math.min(openIndex, closeIndex) - 18);
    let end = Math.min(source.length, Math.max(openIndex, closeIndex) + 19);
    if (end - start > 120) {
      start = Math.max(0, end - 120);
    }
    visible = source.slice(start, end);
  }

  const special = [trade.open_rate, trade.current_rate, trade.target_price, trade.stop_price, trade.close_rate].map(n).filter((v) => v > 0);
  let low = Math.min(...visible.map(c => n(c.low)), ...special);
  let high = Math.max(...visible.map(c => n(c.high)), ...special);
  const pad = Math.max((high - low) * .08, Math.abs(high) * .0003);
  low -= pad; high += pad;
  const span = high - low || 1;
  const plotW = W - left - right, plotH = H - top - bottom;
  const y = (v) => top + (high - n(v)) / span * plotH;
  const x = (i) => left + (i + .5) / visible.length * plotW;
  const candleW = Math.max(2, Math.min(8, plotW / visible.length * .62));

  let out = '';
  for (let i=0;i<6;i++) {
    const yy = top + i * plotH / 5;
    const val = high - i * span / 5;
    out += `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="rgba(84,151,200,.10)"/>`;
    out += `<text x="${W-right+7}" y="${yy+3}" fill="#5b7590" font-size="9">${price(val)}</text>`;
  }
  for (let i=0;i<6;i++) {
    const xx = left + i * plotW / 5;
    out += `<line x1="${xx}" y1="${top}" x2="${xx}" y2="${H-bottom}" stroke="rgba(84,151,200,.06)"/>`;
  }

  visible.forEach((c, i) => {
    const xx = x(i), yo = y(c.open), yc = y(c.close), yh = y(c.high), yl = y(c.low);
    const up = n(c.close) >= n(c.open);
    const color = up ? '#2ce390' : '#ff506c';
    const bodyY = Math.min(yo, yc), bodyH = Math.max(1.5, Math.abs(yc - yo));
    out += `<line x1="${xx}" y1="${yh}" x2="${xx}" y2="${yl}" stroke="${color}" stroke-width="1"/>`;
    out += `<rect x="${xx-candleW/2}" y="${bodyY}" width="${candleW}" height="${bodyH}" rx=".6" fill="${color}"/>`;
  });

  function level(value, color, label, dash='5 4') {
    if (!value) return '';
    const yy = y(value);
    return `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/><rect x="${W-right-2}" y="${yy-10}" width="76" height="18" rx="4" fill="${color}" opacity=".14" stroke="${color}"/><text x="${W-right+3}" y="${yy+3}" fill="${color}" font-size="8">${esc(label)} ${price(value)}</text>`;
  }
  out += level(trade.target_price, '#2ce390', 'ROI');
  out += level(trade.current_rate || trade.close_rate, '#208dff', trade.is_open ? 'Current' : 'Exit', '2 3');
  out += level(trade.stop_price, '#ff506c', 'Stop');
  out += level(trade.open_rate, '#2ad8ff', 'Entry', '2 4');

  const openMs = new Date(trade.open_date || 0).getTime();
  if (Number.isFinite(openMs)) {
    let nearest = 0, dist = Infinity;
    visible.forEach((c, i) => { const t = candleTimeMs(c.time); if (Number.isFinite(t) && Math.abs(t-openMs) < dist) { dist = Math.abs(t-openMs); nearest = i; } });
    const xx = x(nearest), yy = y(trade.open_rate);
    out += `<circle cx="${xx}" cy="${yy}" r="5" fill="#2ce390" stroke="#dffff1" stroke-width="1.5"/><text x="${xx+8}" y="${yy-7}" fill="#8ef3c0" font-size="9">BUY ${price(trade.open_rate)}</text>`;
  }
  if (!trade.is_open && trade.close_date && trade.close_rate) {
    const closeMs = new Date(trade.close_date).getTime();
    let nearest = visible.length-1, dist = Infinity;
    visible.forEach((c, i) => { const t = candleTimeMs(c.time); if (Number.isFinite(t) && Math.abs(t-closeMs) < dist) { dist = Math.abs(t-closeMs); nearest = i; } });
    const xx = x(nearest), yy = y(trade.close_rate);
    out += `<circle cx="${xx}" cy="${yy}" r="5" fill="#ff506c" stroke="#ffe3e8" stroke-width="1.5"/><text x="${Math.max(left,xx-75)}" y="${yy-7}" fill="#ff94a5" font-size="9">SELL ${price(trade.close_rate)}</text>`;
  }

  const labels = [0, Math.floor((visible.length-1)/2), visible.length-1];
  for (const i of labels) {
    const t = candleTimeMs(visible[i]?.time);
    if (!Number.isFinite(t)) continue;
    const label = new Date(t).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
    out += `<text x="${x(i)}" y="${H-14}" text-anchor="middle" fill="#506c86" font-size="8">${label}</text>`;
  }
  svg.innerHTML = out;
}

async function refresh() {
  try {
    const r = await fetch('/api/snapshot', {cache: 'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    renderSnapshot(await r.json());
  } catch (e) {
    $('updatedAt').textContent = 'Dashboard error';
    $('runtimeErrors').innerHTML = `<details open><summary class="negative">Dashboard connection error</summary><pre>${esc(e.message)}</pre></details>`;
  }
}

$('.segment').forEach((button) => button.addEventListener('click', () => {
  setTradeFilter(button.dataset.filter);
}));
const completedCryptoKpi = $('completedCryptoKpi');
if (completedCryptoKpi) {
  const showCompleted = () => setTradeFilter('closed', {scroll: true});
  completedCryptoKpi.addEventListener('click', showCompleted);
  completedCryptoKpi.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      showCompleted();
    }
  });
}
$('.tab').forEach((button) => button.addEventListener('click', () => switchTab(button.dataset.tab)));
$$('[data-close-modal]').forEach((el) => el.addEventListener('click', closeTradeModal));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeTradeModal(); });

initializeStarfield();
refresh();
setInterval(refresh, 10000);
