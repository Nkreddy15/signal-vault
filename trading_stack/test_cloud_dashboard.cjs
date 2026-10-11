// Functional DOM/API harness only; does not claim desktop/mobile visual QA.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const api=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',`
import json
from unittest.mock import patch
from trading_stack.test_cloud_paper import CampaignTests,order,NOW
from trading_stack.cloud_paper.engine import load_config
from trading_stack.cloud_paper.web import snapshot
c=CampaignTests()
with patch('trading_stack.test_cloud_paper.load_config',return_value=load_config('trading_stack/cloud_paper/campaign.integrated.json')):c.setUp()
try:
 for market,symbol in [('crypto','BTC/USD'),('stocks','SPY'),('kalshi','TEST')]:
  c.fill(order(market,market=market,symbol=symbol,quantity=1 if market=='kalshi' else .5,price=.4 if market=='kalshi' else 100))
 s=c.store.read();s['heartbeat']=NOW;s['providers']={m:{'status':'FIXTURE','mode':'ISOLATED FIXTURE'} for m in ('crypto','stocks','kalshi')};c.store.save(s)
 s['providers']['polymarket']={'status':'FIXTURE','mode':'READ-ONLY FIXTURE'};c.store.save(s)
 c.store.db.execute('INSERT INTO arbitrage_observations(at,payload) VALUES(?,?)',(NOW,json.dumps({'slug':'ISOLATED <script> fixture','direction':'buy_complete_set','net_edge':'.023','status':'QUALIFIED_RESEARCH_ONLY'})))
 d=snapshot(c.store,NOW);d['cloud']['csrf_token']='isolated-csrf-fixture';print(json.dumps(d))
finally:c.tearDown()
`],{cwd:root,encoding:'utf8'}));
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',style:{},dataset:{},
 classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(){},querySelectorAll(){return[];}});return elements.get(id);}
const document={getElementById:el,querySelectorAll:()=>[],querySelector:el,documentElement:{style:{setProperty(){}}}};
let source=fs.readFileSync(path.join(__dirname,'dashboard/static/dashboard.js'),'utf8');
source=source.slice(0,source.lastIndexOf("\ndocument.querySelectorAll('.segment')"));
let calls=[];
const context={document,console,Date,Math,Number,String,Array,URLSearchParams,location:{search:''},
 crypto:{randomUUID:()=> 'isolated-request-id'},confirm:()=>true,snapshot:api,
 fetch:async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>url==='/api/control'?{command_id:1}:api};}};
vm.createContext(context);vm.runInContext(source,context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'dashboard/static/cloud.js'),'utf8'),context);
vm.runInContext('renderSnapshot(snapshot)',context);
assert.equal(el('paperReleaseTitle').textContent,'CLOUD PAPER · RUNNING');
assert.match(el('stockEquity').textContent,/\$/);
assert.match(el('managedStockPositions').innerHTML,/SPY/);assert.match(el('kalshiPositions').innerHTML,/TEST/);
assert.match(el('healthGrid').innerHTML,/OmniQuant regime.*PINNED REGIME DETECTOR/);
assert.match(el('healthGrid').innerHTML,/PredictArb research.*FIXTURE/);
assert.match(el('paperReleaseDiagnostics').innerHTML,/&lt;script&gt; fixture.*research only/);
assert.doesNotMatch(el('paperReleaseDiagnostics').innerHTML,/<script>/);
assert.equal(vm.runInContext("findTrade('stocks').market",context),'stocks');
assert.equal(vm.runInContext("findTrade('kalshi').market",context),'kalshi');
context.trade={...api.cloud.open_trades[0],fills:[{action:'buy',quantity:1,price:100,at:100},{action:'sell',quantity:1,price:101,at:90000}]};
context.rows=[{time:0,open:99,high:101,low:98,close:100,volume:1}];
vm.runInContext('renderInspector(trade,false);drawCandles(rows,trade)',context);
assert.match(el('.tf-group').innerHTML,/tf active[^>]+data-cloud-tf="4h"/);
assert.match(el('candleChart').innerHTML,/data-fill-marker="buy"/);
vm.runInContext("state.snapshot.crypto.config.timeframe='15m';cloudChart.timeframe='1h';trade.market='crypto';trade.fills=[{action:'buy',quantity:1,price:100,at:100},{action:'sell',quantity:1,price:101,at:1000},{action:'buy',quantity:1,price:100,at:4000}];renderInspector(trade,false);drawCandles([{time:0,open:99,high:102,low:98,close:100,volume:1},{time:900,open:100,high:102,low:99,close:101,volume:1}],trade)",context);
assert.match(el('.tf-group').innerHTML,/tf active[^>]+data-cloud-tf="15m"/);
assert.equal((el('candleChart').innerHTML.match(/data-fill-marker=/g)||[]).length,2);
assert.doesNotMatch(el('candleChart').innerHTML,/NaN/);
vm.runInContext("trade.market='stocks';renderInspector(trade,false)",context);
assert.doesNotMatch(el('.tf-group').innerHTML,/data-cloud-tf="15m"/);
vm.runInContext("trade.market='dex';state.contractQuotes=[{at:50,bid:.000001,ask:.0000011},{at:100,bid:.0000012,ask:.0000013}];trade.fills=[{action:'buy',at:80,price:.0000011}];drawCandles([],trade)",context);
assert.match(el('candleChart').innerHTML,/simulated fills/);
assert.doesNotMatch(el('candleChart').innerHTML,/YES bid|data-contract-quote="ask"|NaN/);
assert.match(el('candleChart').innerHTML,/data-fill-marker="buy"/);
assert.doesNotMatch(el('candleChart').innerHTML,/data-fill-marker="sell"|NaN/);
assert.match(el('executionMetrics').innerHTML,/Signal timestamp|Execution mode/);
assert.match(el('orderEvidence').textContent,/filled/);
vm.runInContext("trade.market='kalshi';state.contractQuotes=[{at:50,bid:.4,ask:.42},{at:100,bid:.41,ask:.43}];trade.fills=[{action:'buy',at:80,price:.42}];drawCandles([],trade)",context);
assert.match(el('candleChart').innerHTML,/data-contract-quote="bid"/);
assert.match(el('candleChart').innerHTML,/data-fill-marker="buy"/);
(async()=>{
 await vm.runInContext("paperControl('pause')",context);
 const control=calls.find(c=>c.url==='/api/control');assert.equal(control.options.method,'POST');
 assert.equal(control.options.headers['X-CSRF-Token'],'isolated-csrf-fixture');
 assert.deepEqual(JSON.parse(control.options.body),{action:'pause',trade_id:null});
 assert.match(el('controlMessage').textContent,/queued/);
 console.log('PASS: cloud API snapshot, all-market selection, order evidence, honest fill markers, contract quotes and durable control request (DOM harness).');
})().catch(e=>{console.error(e);process.exitCode=1;});
