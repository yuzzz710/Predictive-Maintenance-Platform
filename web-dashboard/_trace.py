#!/usr/bin/env python3
"""Add baseline traceability — CSS, HTML, JS functions, context menu."""
import re

with open('home.html', 'r', encoding='utf-8') as f:
    c = f.read()
orig = len(c)
changes = []

# ═══════ 1. CSS ═══════
trace_css = '''
/* Baseline Trace Panel */
.trace-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:3000;display:none;opacity:0;transition:opacity 0.25s ease}
.trace-overlay.open{display:block;opacity:1}
.trace-panel{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:560px;max-width:94vw;max-height:80vh;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);z-index:3001;overflow-y:auto;box-shadow:0 16px 48px rgba(0,0,0,0.5)}
.trace-header{position:sticky;top:0;background:var(--bg-card);z-index:10;padding:16px 20px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.trace-close{width:28px;height:28px;border-radius:50%;border:1px solid var(--border);background:var(--bg-card-alt);color:var(--text-secondary);cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center}
.trace-close:hover{background:var(--red);color:#fff;border-color:var(--red)}
.trace-body{padding:16px 20px;font-size:12px;line-height:1.8;color:var(--text-secondary)}
.trace-body h3{font-size:14px;color:var(--text-primary);margin:14px 0 8px}
.trace-body h3:first-child{margin-top:0}
.trace-item{padding:6px 10px;margin:3px 0;background:var(--bg-card-alt);border-radius:4px;display:flex;justify-content:space-between}
.trace-bar-wrap{height:6px;background:var(--bg-card-alt);border-radius:3px;margin:4px 0 8px;overflow:hidden}
.trace-bar-fill{height:100%;border-radius:3px}
.trace-note{font-size:11px;color:var(--text-muted);margin-top:12px;padding:10px 14px;background:var(--bg-card-alt);border-radius:4px;border-left:3px solid var(--teal);line-height:1.7}
.trace-table{width:100%;border-collapse:collapse;font-size:10px;margin:8px 0}
.trace-table th{text-align:left;padding:4px 8px;color:var(--text-muted);border-bottom:1px solid var(--border);font-family:var(--font-mono)}
.trace-table td{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.03)}
.trace-table .hl{color:var(--accent-cyan);font-weight:600}
'''
c = c.replace('</style>', trace_css + '\n</style>', 1)
changes.append('CSS')

# ═══════ 2. HTML ═══════
trace_html = '''
<div class="trace-overlay" id="trace-overlay"></div>
<div class="trace-panel" id="trace-panel" style="display:none">
  <div class="trace-header">
    <div style="font-size:16px;font-weight:700;" id="trace-title">基线溯源</div>
    <button class="trace-close" id="trace-close">&times;</button>
  </div>
  <div class="trace-body" id="trace-body"></div>
</div>
'''
c = c.replace('\n</body>', trace_html + '\n</body>', 1)
changes.append('HTML')

# ═══════ 3. JS — data variables ═══════
old = 'var machineMap = {};      // mid -> {health, workOrder, shap}'
new = 'var machineMap = {};      // mid -> {health, workOrder, shap}\nvar _traceBaseline = null;\nvar _traceZScores = null;'
c = c.replace(old, new)
changes.append('data vars')

# ═══════ 4. JS — load call ═══════
old = '  initOperatorDashboard(healthData, workOrderData);'
new = '  loadTraceData();\n  initOperatorDashboard(healthData, workOrderData);'
c = c.replace(old, new)
changes.append('load call')

# ═══════ 5. JS — trace functions ═══════
trace_js = r'''
// ── Baseline Trace ──
async function loadTraceData() {
  try { var bl=await loadCSV('data/baseline_stats.csv'); _traceBaseline={}; bl.forEach(function(r){var m=r['Equipment.Id']||r.machine_id;if(m)_traceBaseline[m]=r;}); } catch(e){}
  try { var zs=await loadCSV('data/z_scores.csv'); _traceZScores={}; zs.forEach(function(r){var m=r['Equipment.Id']||r.machine_id;if(m&&!_traceZScores[m])_traceZScores[m]=r;}); } catch(e){}
}

function showTrace(type,mid) {
  var b=_traceBaseline?._traceBaseline[mid];
  var z=_traceZScores?._traceZScores[mid];
  var h=machineMap[mid]?.health;
  if(!h&&!b&&!z) return;
  var title='',body='';
  if(type==='health'){title=mid+' 健康分: '+(h?.health_score||'--')+'（'+(h?.health_level||'--')+'）';body=buildHealthTrace(mid,h,b);}
  else if(type==='zscore'){var zc=z?(parseFloat(z.z_composite)||0).toFixed(1):'--';title=mid+' 综合Z-Score: '+zc+'（'+(z?.alert_level||'--')+'）';body=buildZScoreTrace(mid,h,b,z);}
  else if(type==='risk'){var cr=h?((h.cost_at_risk||0)/1000).toFixed(1):'--';title=mid+' 日成本风险: $'+cr+'k';body=buildRiskTrace(mid,h,b);}
  document.getElementById('trace-title').textContent=title;
  document.getElementById('trace-body').innerHTML=body;
  document.getElementById('trace-panel').style.display='block';
  document.getElementById('trace-overlay').classList.add('open');
}

function closeTrace() {
  document.getElementById('trace-panel').style.display='none';
  document.getElementById('trace-overlay').classList.remove('open');
}

function buildHealthTrace(mid,h,b) {
  if(!h) return '<p style="color:var(--text-muted)">健康分数据不可用</p>';
  var score=parseFloat(h.health_score)||0;
  var dims=[
    {label:'故障率',w:0.20,v:parseFloat(h.failure_rate)||0,raw:((parseFloat(h.failure_rate)||0)*100).toFixed(1)+'%'},
    {label:'Z-Score异常',w:0.20,v:parseFloat(h.zscore_risk)||0,raw:(parseFloat(h.zscore_risk)||0).toFixed(1)},
    {label:'温度趋势',w:0.15,v:Math.abs(parseFloat(h.temperature_slope)||0),raw:(parseFloat(h.temperature_slope)||0).toFixed(2)+'°C/步'},
    {label:'电压不稳定',w:0.15,v:parseFloat(h.voltage_instability)||0,raw:(parseFloat(h.voltage_instability)||0).toFixed(1)},
    {label:'维护超期',w:0.10,v:parseFloat(h.maintenance_overdue_days)||0,raw:(parseFloat(h.maintenance_overdue_days)||0).toFixed(0)+'天'},
    {label:'成本风险',w:0.10,v:((parseFloat(h.cost_at_risk)||0)/1000),raw:'$'+((parseFloat(h.cost_at_risk)||0)/1000).toFixed(1)+'k'},
    {label:'质量缺陷率',w:0.05,v:parseFloat(h.quality_failure_rate)||0,raw:((parseFloat(h.quality_failure_rate)||0)*100).toFixed(1)+'%'},
    {label:'超规格率',w:0.05,v:parseFloat(h.spec_violation_rate)||0,raw:((parseFloat(h.spec_violation_rate)||0)*100).toFixed(1)+'%'}
  ];
  dims.sort(function(a,b){return(b.w*b.v)-(a.w*a.v);});
  var html='<p>该设备健康分仅 <b style="color:var(--accent-red)">'+score.toFixed(0)+'</b> 分（满分100），判定为<b>"'+(h.health_level||'--')+'"</b>级别，主要由以下因素驱动：</p>';
  dims.forEach(function(d,i){
    var contrib=(d.w*d.v).toFixed(2);
    var icon=i<3?(i===0?'🔴':i===1?'🟡':'🟡'):'⚪';
    var colors=['var(--red)','var(--amber,#f0a030)','var(--teal)','var(--text-muted)'];
    html+='<div class="trace-item"><span class="ti-label">'+icon+' '+d.label+'（权重'+(d.w*100).toFixed(0)+'%）</span><span class="ti-val">'+d.raw+' → 贡献 '+contrib+'</span></div>';
    html+='<div class="trace-bar-wrap"><div class="trace-bar-fill" style="width:'+Math.min(100,parseFloat(contrib)/10*100)+'%;background:'+colors[Math.min(i,3)]+'"></div></div>';
  });
  if(b){
    var bq={stable:'稳定',sparse:'稀疏',cold_start:'冷启动'};
    html+='<h3>📌 基线说明</h3><p>该设备使用 <b>'+(b.n_normal_total||'--')+'</b> 个正常运行时段的电压/电流/温度数据建立统计基线（μ±σ）。基线来源：<b>'+(b.baseline_source==='self'?'自身数据':b.baseline_source==='hybrid'?'自身+集群混合':'集群均值')+'</b>，基线质量：<b>'+(bq[b.baseline_quality]||b.baseline_quality||'--')+'</b>。</p><p>当前值与基线的偏差越大，Z-Score越高，健康扣分越多。8个维度各自乘以权重后求和，从100分中扣除。</p>';
  }
  html+='<div class="trace-note">💡 <b>自然语言解读：</b>'+nlHealth(h)+'</div>';
  return html;
}

function nlHealth(h){
  var s=parseFloat(h.health_score)||0;
  var tf=h.top_risk_factor_label||'';
  var t=h.trend||'';
  var p=[];
  if(s<40)p.push('设备处于危险状态，需立即关注');
  else if(s<60)p.push('设备处于退化阶段，建议安排检查');
  else p.push('设备运行基本正常');
  if(tf)p.push('主要风险来源于'+tf);
  if(t==='Critical')p.push('趋势持续恶化，存在突发故障可能');
  else if(t==='Degrading')p.push('健康分呈下降趋势，需预防性维护');
  else if(t==='Stable')p.push('健康分趋于稳定，可适当延长检查周期');
  return p.join('。')+'。';
}

function buildZScoreTrace(mid,h,b,z){
  if(!z) return '<p style="color:var(--text-muted)">Z-Score数据不可用</p>';
  var params=[
    {label:'电压',zk:'z_Voltage',mk:'Op.Voltage_mu',sk:'Op.Voltage_sigma'},
    {label:'电流',zk:'z_Amperage',mk:'Op.Amperage_mu',sk:'Op.Amperage_sigma'},
    {label:'温度',zk:'z_Temperature',mk:'Op.Temperature_mu',sk:'Op.Temperature_sigma'}
  ];
  var html='<p>当前参数与自身正常工况基线的偏差：</p>';
  var worstP=null,worstZ=0;
  params.forEach(function(p){
    var zv=parseFloat(z[p.zk])||0;
    var mu=b?(parseFloat(b[p.mk])||0).toFixed(0):'--';
    var sg=b?(parseFloat(b[p.sk])||0).toFixed(1):'--';
    var lv=Math.abs(zv)>2.5?'🔴':Math.abs(zv)>2.0?'🟡':Math.abs(zv)>1.5?'🟢':'⚪';
    html+='<div class="trace-item"><span class="ti-label">'+lv+' '+p.label+'</span><span class="ti-val">Z='+zv.toFixed(1)+'（基线 '+mu+'±'+sg+'）</span></div>';
    if(Math.abs(zv)>worstZ){worstZ=Math.abs(zv);worstP=p.label;}
  });
  var zComp=parseFloat(z.z_composite)||0;
  html+='<p style="margin-top:10px">综合判定：<b>'+worstP+'</b>单项偏离最大（Z='+worstZ.toFixed(1)+'），复合Z-Score='+zComp.toFixed(1)+'（取电压/电流/温度Z值平方和开根）。当前触发：<b style="color:'+(z.alert_level==='ALARM'?'var(--accent-red)':'var(--accent-amber)')+'">'+(z.alert_level||'--')+'</b></p>';
  html+='<h3>📌 阈值选择依据</h3><p>推荐操作点 z>2.0：每5次告警约4次正确，误报率控制在20%以内。阈值基于30步时序回测的精确率/召回率/FPR平衡。</p>';
  html+='<table class="trace-table"><thead><tr><th>阈值</th><th>精确率</th><th>召回率</th><th>F1</th><th>误报率</th><th>场景</th></tr></thead><tbody>';
  var rows=[
    ['z>1.0','73.5%','85.6%','79.0%','80.5%','FPR过高不可用'],
    ['z>1.5','76.0%','62.2%','68.4%','51.2%','初步筛查(Watch)'],
    ['z>2.0 ★','83.9%','39.4%','53.6%','19.7%','运维派单(推荐)'],
    ['z>2.5','92.1%','21.9%','35.4%','4.9%','紧急干预(Alarm)']
  ];
  rows.forEach(function(r,i){
    html+='<tr'+(i===2?' class="hl"':'')+'><td>'+r[0]+'</td><td>'+r[1]+'</td><td>'+r[2]+'</td><td>'+r[3]+'</td><td>'+r[4]+'</td><td>'+r[5]+'</td></tr>';
  });
  html+='</tbody></table>';
  if(b) html+='<div class="trace-note">💡 <b>基线来源：</b>'+(b.baseline_source==='self'?'自身'+b.n_normal_total+'个正常样本':b.baseline_source==='hybrid'?'自身+集群混合':'集群均值')+'，质量：'+(b.baseline_quality||'--')+'。逐设备基线是必需的——设备间差异占总方差的61-73%，全局阈值完全不可用。</div>';
  return html;
}

function buildRiskTrace(mid,h,b){
  if(!h) return '<p style="color:var(--text-muted)">成本风险数据不可用</p>';
  var fr=((parseFloat(h.failure_rate)||0)*100).toFixed(1);
  var cr=parseFloat(h.cost_at_risk)||0;
  var html='<p>风险计算公式：<b>故障概率 × 单件成本 × 日产量</b></p>';
  html+='<div class="trace-item"><span class="ti-label">故障概率</span><span class="ti-val">'+fr+'%</span></div>';
  html+='<div class="trace-item"><span class="ti-label">日成本风险</span><span class="ti-val">$'+cr.toFixed(0)+'/天</span></div>';
  html+='<div class="trace-note">💡 <b>解读：</b>如果该设备发生故障导致停产，每天将损失约 <b>$'+(cr/1000).toFixed(1)+'k</b> 的产值。此数值用于工单优先级排序——成本风险越高的设备，越优先安排维护。</div>';
  var rn=cr>6000?'属于全厂成本风险最高档位，建议优先保障该设备的维护资源。':cr>3000?'处于中等风险档位，按计划维护即可。':'风险较低，可适当延后维护。';
  html+='<p style="margin-top:8px;font-size:11px">📌 '+rn+'</p>';
  return html;
}

// Context menu — right-click on data-trace elements
document.addEventListener('contextmenu',function(e){
  var el=e.target.closest('[data-trace]');
  if(!el) return;
  e.preventDefault();
  var type=el.getAttribute('data-trace');
  var mid=el.getAttribute('data-trace-mid');
  if(type&&mid) showTrace(type,mid);
});
document.getElementById('trace-overlay').addEventListener('click',closeTrace);
document.getElementById('trace-close').addEventListener('click',closeTrace);
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeTrace();});
'''

old_end = '// ── Boot ──\ninit();'
c = c.replace(old_end, trace_js + '\n' + old_end)
changes.append('trace functions')

# ═══════ 6. Tag elements — add data-trace to JS-rendered cards ═══════
# Emergency grid cards
old_grid = "gridHtml += '<div class=\\\"ops-device-card\\\" onclick=\\\"var m=machineMap[\\\\'' + mid + '\\\\'']; if(m)openPanel(\\\\'' + mid + '\\\\'',m);\\\">'"
new_grid = "gridHtml += '<div class=\\\"ops-device-card\\\" data-trace=\\\"health\\\" data-trace-mid=\\\"' + mid + '\\\" onclick=\\\"var m=machineMap[\\\\'' + mid + '\\\\'']; if(m)openPanel(\\\\'' + mid + '\\\\'',m);\\\">'"
if old_grid in c:
    c = c.replace(old_grid, new_grid)
    changes.append('tagged 2x5 cards')

# WO cards
old_wo = "planCards += '<div class=\\\"wo-card ' + priLevel + '\\\" onclick=\\\"var m=machineMap[\\\\'' + mid + '\\\\'']; if(m)openPanel(\\\\'' + mid + '\\\\'',m);\\\">'"
new_wo = "planCards += '<div class=\\\"wo-card ' + priLevel + '\\\" data-trace=\\\"zscore\\\" data-trace-mid=\\\"' + mid + '\\\" onclick=\\\"var m=machineMap[\\\\'' + mid + '\\\\'']; if(m)openPanel(\\\\'' + mid + '\\\\'',m);\\\">'"
if old_wo in c:
    c = c.replace(old_wo, new_wo)
    changes.append('tagged WO cards')

# Stat cards
c = c.replace('id="ops-healthy-pct"', 'id="ops-healthy-pct" data-trace="health"')
c = c.replace('id="ops-critical-count"', 'id="ops-critical-count" data-trace="health"')
changes.append('tagged stat cards')

# 10x10 grid cells — add data-trace in renderGrid
old_cell_click = "cell.addEventListener('click', function(mid, m) {"
new_cell_click = "cell.setAttribute('data-trace','health');cell.setAttribute('data-trace-mid',mid);cell.addEventListener('click', function(mid, m) {"
c = c.replace(old_cell_click, new_cell_click)
changes.append('tagged 10x10 cells')

with open('home.html', 'w', encoding='utf-8') as f:
    f.write(c)
print(f'Size: {orig} -> {len(c)} bytes')
print(f'Changes: {len(changes)} — {", ".join(changes)}')
