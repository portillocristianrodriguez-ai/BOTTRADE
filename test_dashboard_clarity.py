"""Execute the actual browser formatting and P&L functions without broker access."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js needed to verify browser calculations')
class DashboardClarityTests(unittest.TestCase):
    def test_residuals_returns_shorts_and_missing_values(self):
        source = Path(__file__).with_name('dashboard.py').read_text()
        script = source.split('<script>', 1)[1].split('function drawChart(', 1)[0]
        checks = r'''
const assert = require('node:assert/strict');
assert.equal(cls(0), 'neutral');
assert.equal(cls(null), 'neutral');
assert.equal(cls(-0), 'neutral');
assert.equal(money(-0), '$0.00');
assert.equal(money(-0.000001), '-<$0.01');
assert.equal(money(0.00249), '<$0.01');
assert.equal(money(NaN), '—');
assert.equal(pct(0), '0.00%');
assert.equal(pct(null), '—');
assert.equal(pct(-0.001), '-<0.01%');
assert.notEqual(precise(0.000003), '$0.00');
assert.notEqual(num(1e-15), '0');
const eth = positionResult({qty:'0.000001', avg_entry_price:'2467.30', current_price:'2492.69', unrealized_plpc:'0'});
assert(Math.abs(eth.pnl-0.00002539)<1e-12);
assert(eth.ret>1 && eth.ret<1.1);
const avax = positionResult({qty:'0.000001',avg_entry_price:'7.62',current_price:'7.87',unrealized_plpc:'0'});
assert(avax.ret>3.28 && avax.ret<3.29);
const short = positionResult({qty:'-2',avg_entry_price:'100',current_price:'90'});
assert.equal(short.pnl,20);
assert.equal(short.move,-1.8);
assert.equal(positionResult({qty:2,avg_entry_price:null,current_price:90}).pnl,null);
const rendered=renderPositions([{symbol:'ETH',qty:1e-6,avg_entry_price:2467.30,current_price:2492.69},{symbol:'NVDA',qty:443,avg_entry_price:233.66,current_price:230.36}]);
assert(rendered.indexOf('NVDA')<rendered.indexOf('ETH'));
assert(rendered.includes('Residuo &lt; $0.01'));
assert(rendered.includes('hipotético'));
assert(renderPositions([{symbol:'<script>',qty:1,avg_entry_price:1,current_price:2}]).includes('&lt;script&gt;'));
assert(renderFills([{side:'sell',qty:2,price:100}]).includes('$200.00 recibidos'));
assert(renderFills([{side:'sell',qty:2,price:100}]).includes('No verificable'));
'''
        subprocess.run(['node', '-e', script + checks], check=True, capture_output=True, text=True)
