"""Align device-grid openPanel with home.html exactly"""
with open('device-grid.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Add missing CSS ──
panel_css = '''
.panel-header {
  position: sticky; top: 0; background: var(--bg-card); z-index: 10;
  padding: 18px 20px 12px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.panel-close {
  width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg-card-alt); color: var(--text-secondary); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.panel-close:hover { background: var(--border); color: var(--text-primary); }
.panel-body { padding: 16px 20px; }
.panel-section { margin-bottom: 20px; }
.panel-section h3 {
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
}
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat-item { padding: 10px; background: var(--bg-card-alt); border-radius: 6px; }
.stat-label { font-size: 10px; color: var(--text-muted); margin-bottom: 2px; }
.stat-value { font-size: 15px; font-weight: 700; font-family: var(--font-mono); }
.signal-item { padding: 8px 10px; margin: 4px 0; background: var(--bg-card-alt); border-radius: 4px; display: flex; gap: 10px; align-items: flex-start; font-size: 12px; line-height: 1.5; }
.signal-badge { font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.checklist-item { font-size: 12px; padding: 5px 0; color: var(--text-secondary); line-height: 1.6; }
.checklist-item .idx { color: var(--cyan); font-weight: 600; margin-right: 6px; }
.shap-explore-btn-open {
  display: block; width: 100%; padding: 10px; margin-bottom: 10px;
  border-radius: 6px; cursor: pointer; font-size: 12px; font-family: var(--font-sans);
  border: 1px solid rgba(163,113,247,0.25); background: rgba(163,113,247,0.08);
  color: var(--purple); transition: all 0.2s;
}
.shap-explore-btn-open:hover { background: rgba(163,113,247,0.15); border-color: var(--purple); }
'''

old_css_marker = '.detail-panel.open { transform: translateX(0); }'
# Only add panel CSS if not already present
if '.panel-header {' not in content:
    content = content.replace(old_css_marker, old_css_marker + panel_css)

# ── 2. Remove old duplicate panel CSS if present (panel-header etc. might be in CSS already as part of detail panel section)
# Remove duplicate definitions
dup_patterns = [
    '.panel-header {\n  position: sticky; top: 0; background: var(--bg-card); z-index: 10;\n  padding: 18px 20px 12px; border-bottom: 1px solid var(--border);\n  display: flex; align-items: center; justify-content: space-between;\n}',
]
for dup in dup_patterns:
    while content.count(dup) > 1:
        idx = content.rfind(dup)
        content = content[:idx] + content[idx+len(dup):]

# ── 3. Add shap_dashboard.json loading in init ──
old_init_load = "var [healthData, woData] = await Promise.all([\n      loadCSV('data/equipment_health_score.csv'),\n      loadCSV('data/maintenance_work_orders.csv')\n    ]);"

new_init_load = "var [healthData, woData, shapJson] = await Promise.all([\n      loadCSV('data/equipment_health_score.csv'),\n      loadCSV('data/maintenance_work_orders.csv'),\n      fetch('data/shap_dashboard.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; })\n    ]);"

content = content.replace(old_init_load, new_init_load)

# ── 4. Add shap to machineMap ──
old_map = "machineMap[mid] = { health: r, workOrder: woMap[mid] || null };"
new_map = "var shMap = {}; if (shapJson && shapJson.machines) { shapJson.machines.forEach(function(s) { shMap[s.machine_id] = s; }); }\n      machineMap[mid] = { health: r, workOrder: woMap[mid] || null, shap: shMap[mid] || null };"

content = content.replace(old_map, new_map)

# ── 5. Replace the entire openPanel function ──
old_openPanel = "function openPanel(mid, m) {"

# Find where openPanel ends and closePanel begins
open_start = content.find('function openPanel(mid, m) {')
close_start = content.find('\nfunction closePanel() {', open_start)

if open_start > 0 and close_start > open_start:
    new_openPanel = '''function openPanel(mid, m) {
  var h = m.health;
  var wo = m.workOrder;
  var sh = m.shap;

  document.getElementById('panel-mid').textContent = mid;
  var levelColor = {'Healthy':'var(--green)','Warning':'var(--amber)','Degrading':'#b8860b','Critical':'var(--red)'};
  var lc = levelColor[h.health_level] || 'var(--text-muted)';
  var alertTag = wo ? ('<span style="color:'+(wo.alert_level==='ALARM'?'var(--red)':'var(--amber)')+';font-weight:700;">'+wo.alert_level+'</span>') : '无工单';
  document.getElementById('panel-subtitle').innerHTML =
    '健康: <b style="color:'+lc+'">'+h.health_score+'</b> &nbsp;|&nbsp; '+h.health_level+' &nbsp;|&nbsp; 趋势: '+h.trend+' &nbsp;|&nbsp; '+alertTag;

  var html = '';

  // ── Section: Key metrics ──
  html += '<div class="panel-section">';
  html += '<h3><span class="dot" style="background:var(--cyan);"></span>关键指标</h3>';
  html += '<div class="stat-row">';
  html += '<div class="stat-item"><div class="stat-label">健康评分</div><div class="stat-value" style="color:'+lc+'">'+h.health_score+'</div></div>';
  html += '<div class="stat-item"><div class="stat-label">故障率</div><div class="stat-value">'+(h.failure_rate*100).toFixed(1)+'%</div></div>';
  html += '<div class="stat-item"><div class="stat-label">维护超期</div><div class="stat-value">'+h.maintenance_overdue_days+'天</div></div>';
  html += '<div class="stat-item"><div class="stat-label">成本风险</div><div class="stat-value">$'+((h.cost_at_risk||0)/1000).toFixed(1)+'k</div></div>';
  html += '</div></div>';

  // ── Section: Key anomaly signals ──
  if (sh && sh.key_anomaly_signals && sh.key_anomaly_signals.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--amber);"></span>关键异常信号</h3>';
    sh.key_anomaly_signals.forEach(function(s) {
      var badge = (s.severity||0) > 2 ? '\\u{1F534}' : (s.severity||0) > 1 ? '\\u{1F7E1}' : '\\u{1F7E2}';
      html += '<div class="signal-item">';
      html += '<span class="signal-badge">'+badge+'</span>';
      html += '<div><b>'+s.feature_label+'</b> ('+s.value_label+')<br>';
      html += '<span style="color:var(--text-muted);">'+s.explanation+'</span></div>';
      html += '</div>';
    });
    html += '</div>';
  }

  // ── Section: SHAP attribution ──
  if (sh && sh.top_contributors && sh.top_contributors.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--purple);"></span>SHAP 归因分析</h3>';
    html += '<div style="font-size:12px;line-height:1.7;margin-bottom:8px;">'+sh.natural_summary+'</div>';
    html += '<button class="shap-explore-btn-open" onclick="event.stopPropagation();">\\u{1F50D} 交互式探索：查看单一特征对所有100台设备的影响</button>';
    sh.top_contributors.slice(0,5).forEach(function(c) {
      var dirColor = c.contribution > 0 ? 'var(--red)' : 'var(--green)';
      var arrow = c.contribution > 0 ? '\\u2191' : '\\u2193';
      html += '<div style="display:flex;justify-content:space-between;font-size:11px;padding:2px 0;">';
      html += '<span>'+c.feature+' <span style="color:var(--text-muted);">('+c.category_label+')</span></span>';
      html += '<span style="color:'+dirColor+';font-family:monospace;">'+arrow+' '+(c.contribution>0?'+':'')+c.contribution.toFixed(3)+'</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  // ── Section: Work order ──
  if (wo) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--red);"></span>维护工单</h3>';
    html += '<div class="stat-row">';
    html += '<div class="stat-item"><div class="stat-label">优先级</div><div class="stat-value">#'+wo.priority+'</div></div>';
    html += '<div class="stat-item"><div class="stat-label">动作</div><div class="stat-value" style="font-size:14px;">'+wo.action_type+'</div></div>';
    html += '<div class="stat-item"><div class="stat-label">紧急度</div><div class="stat-value">'+wo.urgency_score+'</div></div>';
    html += '</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">建议窗口: '+wo.window_days+'天 &nbsp;|&nbsp; 预期节省: $'+wo.expected_savings.toFixed(0)+'</div>';
    if (wo.top_risk_factor_1) {
      html += '<div style="font-size:11px;margin-top:8px;padding:8px;background:var(--bg-card);border-radius:4px;line-height:1.6;">';
      html += '<b>根因:</b> '+wo.top_risk_factor_1+'<br>';
      if (wo.top_risk_factor_2) html += '<b>次要:</b> '+wo.top_risk_factor_2+'<br>';
      if (wo.shap_risk_summary) html += '<b>风险分布:</b> '+wo.shap_risk_summary;
      html += '</div>';
    }
    html += '</div>';
  }

  // ── Section: Inspection checklist ──
  if (sh && sh.inspection_checklist && sh.inspection_checklist.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--cyan);"></span>建议排查清单</h3>';
    sh.inspection_checklist.forEach(function(item, i) {
      html += '<div class="checklist-item"><span class="idx">'+(i+1)+'.</span> '+item+'</div>';
    });
    html += '</div>';
  }

  // No data fallback
  if (!sh && !wo) {
    html += '<div class="panel-section"><div style="text-align:center;color:var(--text-muted);padding:20px;font-size:13px;">该设备无活跃工单，SHAP 数据不可用。<br>如需归因分析，请运行 Pipeline 并启用 --shap。</div></div>';
  }

  // ── Add to Work Order Tracking button ──
  var strategy = sessionStorage.getItem('current_strategy') || 'production_efficiency';
  var strategyLabels = { cost_efficiency: '成本效率', production_efficiency: '生产效率', quality_first: '质量优先' };
  html += '<div class="panel-section">';
  html += '<button id="btn-add-tracking" style="width:100%;padding:10px;border-radius:6px;font-size:13px;cursor:pointer;border:1px solid var(--cyan);background:rgba(0,201,160,0.1);color:var(--cyan);font-family:var(--font-sans);transition:all 0.2s;" onclick="addToTracking(\\''+mid+'\\')">+ 加入工单跟踪（'+ (strategyLabels[strategy] || strategy) +'）</button>';
  html += '</div>';

  document.getElementById('panel-body').innerHTML = html;
  document.getElementById('detail-panel').classList.add('open');
  document.getElementById('panel-overlay').classList.add('open');
}'''

    content = content[:open_start] + new_openPanel + '\n' + content[close_start:]
    print('openPanel replaced')
else:
    print(f'ERROR: openPanel at {open_start}, closePanel at {close_start}')

# ── 6. Add addToTracking function before closePanel ──
add_tracking = '''
function addToTracking(machineId) {
  var strategy = sessionStorage.getItem('current_strategy') || 'production_efficiency';
  var btn = document.getElementById('btn-add-tracking');
  if (!btn) return;

  var m = machineMap[machineId];
  if (!m) return;

  fetch('/api/work-order/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      machine_id: machineId,
      priority: m.workOrder ? m.workOrder.priority : 99,
      strategy: strategy
    })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.success) {
      btn.textContent = '\\u2705 已加入工单跟踪';
      btn.style.background = 'rgba(63,185,80,0.15)';
      btn.style.borderColor = 'var(--green)';
      btn.style.color = 'var(--green)';
      btn.disabled = true;
    } else {
      btn.textContent = '\\u26A0 ' + (d.detail || '操作失败');
    }
  }).catch(function() {
    btn.textContent = '\\u26A0 网络错误';
  });
}

'''

close_panel_idx = content.find('\nfunction closePanel() {')
if close_panel_idx > 0:
    content = content[:close_panel_idx] + add_tracking + '\n' + content[close_panel_idx:]

with open('device-grid.html', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Done. File size: {len(content)} bytes')
