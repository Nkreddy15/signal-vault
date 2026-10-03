// Limited DOM harness for the trade inspector; no visual-browser claim.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
const el = id => {
  if (!elements.has(id)) elements.set(id, {innerHTML:'',textContent:'',style:{},dataset:{},
    classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(){}});
  return elements.get(id);
};
const document = {
  getElementById:el,querySelectorAll:()=>[],querySelector:()=>null,
  documentElement:{style:{setProperty(){}}}
};
let source = fs.readFileSync(path.join(__dirname,'dashboard/static/dashboard.js'),'utf8');
source = source.slice(0, source.lastIndexOf("\ndocument.querySelectorAll('.segment')"));
const context = {document,console,Date,Math,Number,String,Array,URLSearchParams,location:{search:''}};
vm.createContext(context);
vm.runInContext(source,context);
context.trade = {trade_id:'test',pair:'BTC/USD',open_rate:100,current_rate:99,close_rate:99,
  open_date:'2026-10-03T04:00:00Z',close_date:'2026-10-03T05:00:00Z',is_open:false,
  is_short:true,stake_amount:15,amount:.15,target_price:88,stop_price:104};
context.candles = [
  {time:'2026-10-03T04:00:00Z',open:100,high:101,low:98,close:99},
  {time:'2026-10-03T05:00:00Z',open:99,high:100,low:98,close:99}];
vm.runInContext("renderInspector(trade,false);switchTab('overview');drawCandles(candles,trade)",context);
const chart = el('candleChart').innerHTML;
if (!chart.includes('SELL SHORT') || !chart.includes('BUY TO COVER') || chart.includes('NaN'))
  throw Error('Chart labels or geometry failed');
if (el('detailSide').textContent !== 'Short · $15.00 stake') throw Error('Inspector side failed');
context.snapshot = {
  generated_at:'2026-10-03T05:00:00Z',
  system:{dashboard:'ONLINE',crypto_engine:'RUNNING',stock_broker:'ONLINE'},
  safety:{live_trading:false,crypto_max_open_trades:3},
  crypto:{bot_state:'RUNNING',config:{exchange:'Kraken public data',runmode:'SYNTHETIC PAPER',strategy:'V9',timeframe:'1h'},
    profit:{closed_trade_count:0},open_pnl_usd:0,closed_pnl_usd:0,open_exposure_usd:0,
    open_trade_count:0,closed_trade_count:0,open_trades:[],closed_trades:[],errors:[]},
  stocks:{account:{status:'ACTIVE',equity:100,cash:90},clock:{is_open:false},managed_positions:[],
    other_positions:[],recent_orders:[],managed_unrealized_pnl_usd:0,managed_exposure_usd:0,errors:[]},
  legacy_crypto:{open_trade_count:1,closed_pnl_usd:-0.32},
  paper_final:{status:'RUNNING',ends_at:'2026-10-03T13:00:00Z',note:'Synthetic paper only',
    diagnostics:[{pair:'BTC/USD',reason:'BTC regime not bearish'}]}
};
vm.runInContext('renderSnapshot(snapshot)', context);
if (el('paperReleaseBar').hidden !== false) throw Error('Compact paper status was not shown');
if (el('paperReleaseTitle').textContent !== 'V9 · RUNNING') throw Error('V9 status did not render');
if (!el('paperReleaseDiagnostics').innerHTML.includes('BTC regime not bearish')) throw Error('Diagnostics did not render');
const template = fs.readFileSync(path.join(__dirname,'dashboard/templates/index.html'),'utf8');
if (template.indexOf('paperReleaseBar') < template.indexOf('engine-meta')) throw Error('Paper status escaped the crypto panel');
if (source.includes('paperReleaseBanner') || source.includes('.prepend(banner)')) throw Error('Old layout-breaking banner remains');
console.log('PASS: compact V9 status, inspector, tabs, and short trade chart (DOM harness).');
