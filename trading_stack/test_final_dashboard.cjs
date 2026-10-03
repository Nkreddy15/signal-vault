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
context.snapshot.paper_final = {...context.snapshot.paper_final,
  version:'V10-PAPER-1',next_evaluation_at:'2026-10-03T12:15:00Z',
  cycles:12,intervals_evaluated:2,
  diagnostics:[{pair:'ETH/USD',side:'LONG',regime:'UPTREND',reason:'Own-asset trend confirmed',execution:'OPENED'}]};
context.snapshot.crypto.config.timeframe = '15m';
vm.runInContext('renderSnapshot(snapshot)',context);
if (el('paperReleaseTitle').textContent !== 'V10 · RUNNING') throw Error('V10 status did not render');
if (!el('paperScanStats').textContent.includes('2 evaluated intervals')) throw Error('V10 scan counts failed');
if (!el('paperReleaseDiagnostics').innerHTML.includes('OPENED')) throw Error('V10 entry diagnostics failed');
context.snapshot.paper_final={...context.snapshot.paper_final,version:'V11-PAPER-500-1'};
context.snapshot.crypto={...context.snapshot.crypto,starting_balance:500,marked_equity:499.98};
context.snapshot.crypto.config.timeframe='1d';
vm.runInContext('renderSnapshot(snapshot)',context);
if(el('paperReleaseTitle').textContent!=='V11 · RUNNING')throw Error('V11 selection label failed');
if(!el('paperReleaseMeta').textContent.includes('$500.00 start / $499.98 equity'))throw Error('V11 account balance not shown');
context.trade={...context.trade,is_short:false,target_price:102.7,stop_price:99.2,
  fee_usd:.24,slippage_allowance_usd:.03};
vm.runInContext('renderInspector(trade,false);drawCandles(candles,trade)',context);
if (el('detailSide').textContent !== 'Long · $15.00 stake') throw Error('Long inspector failed');
if (!el('executionMetrics').innerHTML.includes('Modeled Round-trip Fees')) throw Error('Cost breakdown missing');
if (el('candleChart').innerHTML.includes('SELL SHORT') || !el('candleChart').innerHTML.includes('BUY 100')) throw Error('Long chart labels failed');
if (!vm.runInContext('tradeSparkline({price_history:[100,101,100.5],profit_abs:1})',context).includes('180.00')) throw Error('Observed quote sparkline failed');
vm.runInContext('snapshot.crypto.open_pnl_usd=null;renderSnapshot(snapshot)',context);
if(el('cryptoPnl').textContent !== '—') throw Error('Missing marks were shown as zero profit');
let fetchedURL='';
context.location.search='?engine=v9';
context.fetch=async url=>{fetchedURL=url;return {ok:true,json:async()=>context.snapshot}};
(async()=>{
  await vm.runInContext('refresh()',context);
  if(fetchedURL !== '/api/snapshot?engine=v9') throw Error('V9 view refresh lost engine selection');
  console.log('PASS: V9/V10 status, entry diagnostics, missing marks, fees, long/short charts and view selection (DOM harness).');
})().catch(err=>{console.error(err);process.exitCode=1});
