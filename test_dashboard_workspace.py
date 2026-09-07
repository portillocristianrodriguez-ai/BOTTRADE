import io
import re
import shutil
import subprocess
import unittest
from unittest.mock import Mock
import dashboard
import dashboard_experience
import iphone_ai_app


class WorkspaceServingTests(unittest.TestCase):
    def test_actual_root_serves_enhanced_page_and_analyst(self):
        handler=object.__new__(iphone_ai_app.AIHandler)
        handler.path='/';handler.send=Mock()
        handler.do_GET()
        status,body,mime=handler.send.call_args.args
        self.assertEqual(status,200)
        self.assertIn(b'positionDrawer',body)
        self.assertIn(b'aiQuestion',body)
        self.assertIn(b'workspace-nav',body)
        self.assertEqual(body,iphone_ai_app.dashboard.HTML.encode())

    def test_no_portfolio_api_response_is_cached_for_offline_use(self):
        self.assertNotIn('cache.addAll',iphone_ai_app.SERVICE_WORKER)
        self.assertIn('event.request.mode !== "navigate"',iphone_ai_app.SERVICE_WORKER)
        self.assertIn('Sin conexión',iphone_ai_app.SERVICE_WORKER)

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_all_published_scripts_parse_together(self):
        scripts=re.findall(r'<script>(.*?)</script>',iphone_ai_app.dashboard.HTML,re.S)
        subprocess.run(['node','--check'],input='\n'.join(scripts),text=True,check=True,capture_output=True)

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_filters_scenarios_exports_and_out_of_order_responses(self):
        base=re.findall(r'<script>(.*?)</script>',dashboard.HTML,re.S)[0]
        extra=dashboard_experience.SCRIPT.removeprefix('<script>').split("document.getElementById('hideDust').checked=",1)[0]
        environment=r'''
const assert=require('node:assert/strict');
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,style:{},className:'',disabled:false,innerHTML:'',textContent:''});return elements.get(id)},querySelectorAll(){return []},dispatchEvent(){}};
const window={};const localStorage={getItem(){return '{}'}};const CustomEvent=function(name,opts){this.detail=opts.detail};
let pending=[];const fetch=()=>new Promise(resolve=>pending.push(resolve));
'''
        checks=r'''
const positions=[{symbol:'NVDA',asset_class:'us_equity',qty:2,avg_entry_price:100,current_price:90},{symbol:'BTCUSD',asset_class:'crypto',qty:.000000001,avg_entry_price:100,current_price:110},{symbol:'ZERO',qty:0,avg_entry_price:1,current_price:1}];
const opt={search:'',market:'all',hideDust:false,sort:'value'};
assert.equal(filteredPositions(positions,opt).length,2);
assert.deepEqual(filteredPositions(positions,{...opt,hideDust:true}).map(x=>x.symbol),['NVDA']);
assert.deepEqual(filteredPositions(positions,{...opt,market:'crypto'}).map(x=>x.symbol),['BTCUSD']);
favorites.add('BTCUSD');assert.equal(filteredPositions(positions,{...opt,market:'favorites'}).length,1);
assert.equal(filteredPositions(positions,{...opt,search:'nv'}).length,1);
const short={qty:-2,avg_entry_price:100,current_price:90};
assert.equal(scenarioResult(short,10).delta,-18);
assert.equal(scenarioResult(short,10).pnl,2);
assert(csvCell('=HYPERLINK("x")').startsWith('"\''));
assert.equal(csvCell(-2),'"-2"');
const d={mode:'PAPER',health:true,timestamp:'2026-09-07T10:00:00Z',account:{equity:100,cash:-10,buying_power:50,day_pnl:0},positions,orders:[],fills:[],open_orders:0,risk:{invested:180,unrealized:-20,largest_symbol:'NVDA',concentration:180,stop_risk_status:'incomplete',stockpct:180,cryptopct:0,cashpct:10},execution:{status:'OK',fills:0,buys:0,sells:0,filled_orders:0,window:'test'},clock:{status:'CLOSED',is_open:false},history:{status:'OK',points:[{equity:100,label:'a'},{equity:110,label:'b'}],return_pct:10,max_drawdown_pct:0,peak:110}};
document.getElementById('assetFilter').value='all';document.getElementById('positionSort').value='value';document.getElementById('activitySide').value='all';
(async()=>{const first=window.load(),second=window.load();pending[1]({ok:true,json:async()=>({...d,account:{...d.account,equity:200}})});await second;pending[0]({ok:true,json:async()=>d});await first;assert.equal(latestState.account.equity,200);assert.equal(document.getElementById('cashpct').textContent,'-5.0%');assert(document.getElementById('workspaceAlerts').innerHTML.includes('Cobertura'));const failed=window.load();pending[2]({ok:false,json:async()=>({error:'down'})});await failed;assert.equal(latestState.account.equity,200);assert.equal(document.getElementById('error').style.display,'block');assert.equal(document.getElementById('broker').textContent,'Alpaca: sin conexión');assert.equal(document.getElementById('refreshButton').disabled,false)})().catch(e=>{console.error(e);process.exitCode=1});
'''
        subprocess.run(['node','-e',environment+base+extra+checks],text=True,capture_output=True,check=True)
