"""Add right-click trace panel to device-grid.html"""
with open('device-grid.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add trace panel CSS after the detail panel CSS
trace_css = '''
/* ── Trace Panel ── */
.trace-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 3000; display: none; opacity: 0; transition: opacity 0.25s ease; }
.trace-overlay.open { display: block; opacity: 1; }
.trace-panel { position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 560px; max-width: 94vw; max-height: 80vh; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); z-index: 3001; overflow-y: auto; box-shadow: 0 16px 48px rgba(0,0,0,0.5); display: none; }
.trace-panel.open { display: block; }
.trace-header { position: sticky; top: 0; background: var(--bg-card); z-index: 10; padding: 16px 20px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.trace-close { width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--border); background: var(--bg-card-alt); color: var(--text-secondary); cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
.trace-close:hover { background: var(--red); color: #fff; border-color: var(--red); }
.trace-body { padding: 16px 20px; font-size: 12px; line-height: 1.8; color: var(--text-secondary); }
.trace-body h3 { font-size: 14px; color: var(--text-primary); margin: 14px 0 8px; }
.trace-body h3:first-child { margin-top: 0; }
.trace-item { padding: 6px 10px; margin: 3px 0; background: var(--bg-card-alt); border-radius: 4px; display: flex; justify-content: space-between; }
.ti-label { flex: 1; }
.ti-val { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.trace-bar-wrap { height: 6px; background: var(--bg-card-alt); border-radius: 3px; margin: 4px 0 8px; overflow: hidden; }
.trace-bar-fill { height: 100%; border-radius: 3px; }
.trace-note { font-size: 11px; color: var(--text-muted); margin-top: 12px; padding: 10px 14px; background: var(--bg-card-alt); border-radius: 4px; border-left: 3px solid var(--cyan); line-height: 1.7; }
.trace-table { width: 100%; border-collapse: collapse; font-size: 10px; margin: 8px 0; }
.trace-table th { text-align: left; padding: 4px 8px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-family: var(--font-mono); }
.trace-table td { padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }
'''

old_marker = '.detail-panel.open { transform: translateX(0); }'
content = content.replace(old_marker, old_marker + trace_css)

# 2. Add trace panel HTML before the closing </body>
trace_html = '''
<div class="trace-overlay" id="trace-overlay" onclick="closeTrace()"></div>
<div class="trace-panel" id="trace-panel">
  <div class="trace-header">
    <div style="font-size:16px;font-weight:700;" id="trace-title">基线溯源</div>
    <button class="trace-close" onclick="closeTrace()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
  </div>
  <div class="trace-body" id="trace-body"></div>
</div>
'''

old_body_end = '</body>'
content = content.replace(old_body_end, trace_html + '\n' + old_body_end)

# 3. Add data-trace attributes to cells + contextmenu handler
old_click = "(function(mid, m) {\n      cell.addEventListener('click', function() { openPanel(mid, m); });\n      cell.style.cursor = 'pointer';\n    })(mid, m);"

new_click = "cell.setAttribute('data-trace', 'health'); cell.setAttribute('data-trace-mid', mid);\n    cell.addEventListener('click', function() { openPanel(mid, m); });\n    cell.style.cursor = 'pointer';"

if old_click in content:
    content = content.replace(old_click, new_click)
else:
    print("WARNING: click handler pattern not found")

# 4. Add trace functions before DOMContentLoaded
old_dom = "document.addEventListener('DOMContentLoaded', init);"

trace_js = '''
var _traceBaseline = {};
var _traceZScores = {};

function loadTraceData() {
  loadCSV('data/baseline_stats.csv').then(function(bl) {
    bl.forEach(function(r) { var m = r['Equipment.Id'] || r.machine_id; if (m) _traceBaseline[m] = r; });
  }).catch(function(){});
  loadCSV('data/z_scores.csv').then(function(zs) {
    zs.forEach(function(r) { var m = r['Equipment.Id'] || r.machine_id; if (m && !_traceZScores[m]) _traceZScores[m] = r; });
  }).catch(function(){});
}

function showTrace(type, mid) {
  var b = _traceBaseline[mid];
  var z = _traceZScores[mid];
  var h = machineMap[mid] && machineMap[mid].health;
  if (!h && !b && !z) return;
  var title = '', body = '';
  if (type === 'health') {
    title = mid + ' 健康分: ' + ((h && h.health_score) || '--') + '（' + ((h && h.health_level) || '--') + '）';
    body = buildHealthTrace(mid, h, b);
  }
  document.getElementById('trace-title').textContent = title;
  document.getElementById('trace-body').innerHTML = body;
  document.getElementById('trace-panel').classList.add('open');
  document.getElementById('trace-overlay').classList.add('open');
}

function closeTrace() {
  document.getElementById('trace-panel').classList.remove('open');
  document.getElementById('trace-overlay').classList.remove('open');
}

function buildHealthTrace(mid, h, b) {
  if (!h) return '<p style="color:var(--text-muted)">健康分数据不可用</p>';
  var score = parseFloat(h.health_score) || 0;
  var dims = [
    { label: '故障率', w: 0.20, v: parseFloat(h.failure_rate) || 0, raw: ((parseFloat(h.failure_rate) || 0) * 100).toFixed(1) + '%' },
    { label: 'Z-Score异常', w: 0.20, v: parseFloat(h.zscore_risk) || 0, raw: (parseFloat(h.zscore_risk) || 0).toFixed(1) },
    { label: '温度趋势', w: 0.15, v: Math.abs(parseFloat(h.temperature_slope) || 0), raw: (parseFloat(h.temperature_slope) || 0).toFixed(2) + '°C/步' },
    { label: '电压不稳定', w: 0.15, v: parseFloat(h.voltage_instability) || 0, raw: (parseFloat(h.voltage_instability) || 0).toFixed(1) },
    { label: '维护超期', w: 0.10, v: parseFloat(h.maintenance_overdue_days) || 0, raw: (parseFloat(h.maintenance_overdue_days) || 0).toFixed(0) + '天' },
    { label: '成本风险', w: 0.10, v: ((parseFloat(h.cost_at_risk) || 0) / 1000), raw: '$' + ((parseFloat(h.cost_at_risk) || 0) / 1000).toFixed(1) + 'k' },
    { label: '质量缺陷率', w: 0.05, v: parseFloat(h.quality_failure_rate) || 0, raw: ((parseFloat(h.quality_failure_rate) || 0) * 100).toFixed(1) + '%' },
    { label: '超规格率', w: 0.05, v: parseFloat(h.spec_violation_rate) || 0, raw: ((parseFloat(h.spec_violation_rate) || 0) * 100).toFixed(1) + '%' }
  ];
  dims.sort(function(a, b) { return (b.w * b.v) - (a.w * a.v); });
  var html = '<p>该设备健康分仅 <b style="color:var(--red)">' + score.toFixed(0) + '</b> 分（满分100），判定为<b>"' + (h.health_level || '--') + '"</b>级别，主要由以下因素驱动：</p>';
  dims.forEach(function(d, i) {
    var contrib = (d.w * d.v).toFixed(2);
    var icon = i < 2 ? '&#128308;' : i < 4 ? '&#128993;' : '&#9898;';
    var colors = ['var(--red)', 'var(--red)', 'var(--amber)', 'var(--text-muted)'];
    html += '<div class="trace-item"><span class="ti-label">' + icon + ' ' + d.label + '（权重' + (d.w * 100).toFixed(0) + '%）</span><span class="ti-val">' + d.raw + ' → 贡献 ' + contrib + '</span></div>';
    html += '<div class="trace-bar-wrap"><div class="trace-bar-fill" style="width:' + Math.min(100, parseFloat(contrib) / 10 * 100) + '%;background:' + colors[Math.min(i, 3)] + '"></div></div>';
  });
  if (b) {
    var bq = { stable: '稳定', sparse: '稀疏', cold_start: '冷启动' };
    html += '<h3>基线说明</h3><p>该设备使用 <b>' + (b.n_normal_total || '--') + '</b> 个正常运行时段的电压/电流/温度数据建立统计基线（μ±σ）。基线来源：<b>' + (b.baseline_source === 'self' ? '自身数据' : b.baseline_source === 'hybrid' ? '自身+集群混合' : '集群均值') + '</b>，基线质量：<b>' + (bq[b.baseline_quality] || b.baseline_quality || '--') + '</b>。</p><p>当前值与基线的偏差越大，Z-Score越高，健康扣分越多。8个维度各自乘以权重后求和，从100分中扣除。</p>';
  }
  html += '<div class="trace-note">' + nlHealth(h) + '</div>';
  return html;
}

function nlHealth(h) {
  var s = parseFloat(h.health_score) || 0;
  var tf = h.top_risk_factor_label || '';
  var t = h.trend || '';
  var p = [];
  if (s < 40) p.push('设备处于危险状态，需立即关注');
  else if (s < 60) p.push('设备处于退化阶段，建议安排检查');
  else p.push('设备运行基本正常');
  if (tf) p.push('主要风险来源于' + tf);
  if (t === 'Critical') p.push('趋势持续恶化，存在突发故障可能');
  else if (t === 'Degrading') p.push('指标持续下降趋势，需要在近期内安排维护');
  else if (t === 'Warning') p.push('个别指标有轻微恶化迹象，建议增加监测频率');
  return '自然语言解读：' + p.join('。') + '。';
}

// Right-click context menu — baseline analysis
document.addEventListener('contextmenu', function(e) {
  var el = e.target.closest('[data-trace]');
  if (!el) return;
  e.preventDefault();
  var type = el.getAttribute('data-trace');
  var mid = el.getAttribute('data-trace-mid');
  if (type && mid) showTrace(type, mid);
});
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeTrace(); });

'''

content = content.replace(old_dom, trace_js + '\n' + old_dom)

# 5. Add loadTraceData call in init()
old_init = '    renderGrid();'
new_init = '    renderGrid();\n    loadTraceData();'
content = content.replace(old_init, new_init)

with open('device-grid.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Trace panel added to device-grid.html')
print(f'New size: {len(content)} bytes')
