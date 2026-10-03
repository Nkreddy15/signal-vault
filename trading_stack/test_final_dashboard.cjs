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
const document = {getElementById:el,querySelectorAll:()=>[],querySelector:()=>null};
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
console.log('PASS: inspector, tab switch, short-entry and cover labels (DOM harness).');
