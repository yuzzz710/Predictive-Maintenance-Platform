/**
 * Shared Device Grid Component
 * ==============================
 * Core logic for the 10×10 device health matrix — shared between home.html
 * and device-grid.html. Both pages only need their own CSS + HTML shell,
 * then call `initDeviceGrid()` to bootstrap everything.
 *
 * Dependencies: PapaParse, ECharts (CDN), sidebar.css
 * Data files: equipment_health_score.csv, maintenance_work_orders.csv,
 *             baseline_stats.csv, z_scores.csv, shap_dashboard.json,
 *             shap_scatter_data.json
 */

var machineMap = {};
var shapScatterData = null;
var _traceBaseline = {};
var _traceZScores = {};

// ── CSV loader ──
async function loadCSV(path) {
  try {
    var r = await fetch(path);
    if (!r.ok) return [];
    var t = await r.text();
    return Papa.parse(t, { header: true, dynamicTyping: true, skipEmptyLines: true }).data;
  } catch(e) { console.warn('loadCSV failed:', path, e); return []; }
}

// ── Trace data loader ──
function loadTraceData() {
  loadCSV('data/baseline_stats.csv').then(function(bl) {
    bl.forEach(function(r) { var m = r['Equipment.Id'] || r.machine_id; if (m) _traceBaseline[m] = r; });
  }).catch(function(){});
  loadCSV('data/z_scores.csv').then(function(zs) {
    zs.forEach(function(r) { var m = r['Equipment.Id'] || r.machine_id; if (m && !_traceZScores[m]) _traceZScores[m] = r; });
  }).catch(function(){});
}

// ── Init ──
async function initDeviceGrid() {
  try {
    var [healthData, woData, shapJson, _shapScatter] = await Promise.all([
      loadCSV('data/equipment_health_score.csv'),
      loadCSV('data/maintenance_work_orders.csv'),
      fetch('data/shap_dashboard.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),
      fetch('data/shap_scatter_data.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; })
    ]);

    var woMap = {};
    woData.forEach(function(r) { if (r.machine_id) woMap[r.machine_id] = r; });

    var shMap = {};
    if (shapJson && shapJson.machines) {
      Object.keys(shapJson.machines).forEach(function(mid) { shMap[mid] = shapJson.machines[mid]; });
    }
    healthData.forEach(function(r) {
      var mid = r['Equipment.Id'] || r.machine_id;
      if (!mid) return;
      machineMap[mid] = { health: r, workOrder: woMap[mid] || null, shap: shMap[mid] || null };
    });

    shapScatterData = _shapScatter;
    renderGrid();
    loadTraceData();
  } catch(e) {
    console.error('Init failed:', e);
    var grid = document.getElementById('machine-grid');
    if (grid) grid.innerHTML = '<div class="fallback">数据加载失败: ' + (e.message || e) + '<br><br>请确保已运行流水线</div>';
  }
}

// ── Grid rendering ──
function renderGrid() {
  var grid = document.getElementById('machine-grid');
  if (!grid) return;
  grid.innerHTML = '';
  var stats = { healthy: 0, warning: 0, degrading: 0, critical: 0, withWO: 0 };

  for (var i = 1; i <= 100; i++) {
    var mid = 'CNC_' + String(i).padStart(3, '0');
    var m = machineMap[mid];
    if (!m) {
      var cell = document.createElement('div');
      cell.className = 'cell';
      cell.style.opacity = '0.3';
      cell.textContent = mid.replace('CNC_', '');
      grid.appendChild(cell);
      continue;
    }

    var h = m.health;
    var wo = m.workOrder;
    var level = (h.health_level || '').trim();

    var cell = document.createElement('div');
    cell.className = 'cell';
    cell.title = mid + ' | 健康分: ' + (h.health_score || '?') + ' | ' + level;

    if (level === 'Healthy') { cell.classList.add('healthy'); stats.healthy++; }
    else if (level === 'Warning') { cell.classList.add('warning'); stats.warning++; }
    else if (level === 'Degrading') { cell.classList.add('degrading'); stats.degrading++; }
    else { cell.classList.add('critical'); stats.critical++; }

    if (wo) {
      cell.classList.add('has-wo');
      cell.classList.add(wo.alert_level === 'ALARM' ? 'alarm' : 'warning');
      stats.withWO++;
      var badge = document.createElement('span');
      badge.className = 'pri-badge';
      badge.textContent = '#' + (wo.priority || '?');
      cell.appendChild(badge);
    }

    var label = document.createElement('span');
    label.textContent = mid.replace('CNC_', '');
    cell.appendChild(label);

    cell.setAttribute('data-trace', 'health');
    cell.setAttribute('data-trace-mid', mid);
    cell.addEventListener('click', function(mid, m) {
      return function() { openPanel(mid, m); };
    }(mid, m));
    cell.style.cursor = 'pointer';

    grid.appendChild(cell);
  }

  highlightTopRisks();

  var statsBar = document.getElementById('stats-bar');
  if (statsBar) {
    statsBar.innerHTML =
      '<span>总计 <b>100</b> 台</span>' +
      '<span class="st-healthy">健康 <b>' + stats.healthy + '</b></span>' +
      '<span class="st-warning">警告 <b>' + (stats.warning || 0) + '</b></span>' +
      '<span class="st-degrading">退化 <b>' + stats.degrading + '</b></span>' +
      '<span class="st-critical">高危 <b>' + stats.critical + '</b></span>' +
      '<span class="st-wo">开放工单 <b>' + stats.withWO + '</b></span>';
  }
}

function highlightTopRisks() {
  var risks = [];
  for (var mid in machineMap) {
    var m = machineMap[mid];
    if (!m.health || !m.health.cost_at_risk) continue;
    risks.push({ mid: mid, cost: parseFloat(m.health.cost_at_risk) || 0 });
  }
  risks.sort(function(a, b) { return b.cost - a.cost; });
  for (var i = 0; i < Math.min(3, risks.length); i++) {
    var cells = document.querySelectorAll('.cell');
    cells.forEach(function(cell) {
      if (cell.textContent.indexOf(risks[i].mid.replace('CNC_','')) >= 0 &&
          !cell.classList.contains('has-wo')) {
        cell.classList.add('priority-pulse');
      }
    });
  }
}

// ── Detail panel ──
function openPanel(mid, m) {
  var h = m.health;
  var wo = m.workOrder;
  var sh = m.shap;

  var panelMid = document.getElementById('panel-mid');
  if (panelMid) panelMid.textContent = mid;
  var levelColor = {'Healthy':'var(--accent-green)','Warning':'var(--accent-amber)','Degrading':'#b8860b','Critical':'var(--accent-red)'};
  var lc = levelColor[h.health_level] || 'var(--text-secondary)';
  var alertTag = wo ? ('<span style="color:'+(wo.alert_level==='ALARM'?'var(--accent-red)':'var(--accent-amber)')+';font-weight:700;">'+wo.alert_level+'</span>') : '无工单';

  var panelSubtitle = document.getElementById('panel-subtitle');
  if (panelSubtitle) panelSubtitle.innerHTML =
    '健康: <b style="color:'+lc+'">'+h.health_score+'</b> &nbsp;|&nbsp; '+h.health_level+' &nbsp;|&nbsp; 趋势: '+h.trend+' &nbsp;|&nbsp; '+alertTag;

  var html = '';
  html += '<div class="panel-section">';
  html += '<h3><span class="dot" style="background:var(--accent-cyan);"></span>关键指标</h3>';
  html += '<div class="stat-row">';
  html += '<div class="stat-item"><div class="stat-label">健康评分</div><div class="stat-value" style="color:'+lc+'">'+h.health_score+'</div></div>';
  html += '<div class="stat-item"><div class="stat-label">故障率</div><div class="stat-value">'+(h.failure_rate*100).toFixed(1)+'%</div></div>';
  html += '<div class="stat-item"><div class="stat-label">维护超期</div><div class="stat-value">'+h.maintenance_overdue_days+'天</div></div>';
  html += '<div class="stat-item"><div class="stat-label">成本风险</div><div class="stat-value">$'+((h.cost_at_risk||0)/1000).toFixed(1)+'k</div></div>';
  html += '</div></div>';

  if (sh && sh.key_anomaly_signals && sh.key_anomaly_signals.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--accent-amber);"></span>关键异常信号</h3>';
    sh.key_anomaly_signals.forEach(function(s) {
      var badge = (s.severity||0) > 2 ? '\u{1F534}' : (s.severity||0) > 1 ? '\u{1F7E1}' : '\u{1F7E2}';
      html += '<div class="signal-item">';
      html += '<span class="signal-badge">'+badge+'</span>';
      html += '<div><b>'+s.feature_label+'</b> ('+s.value_label+')<br>';
      html += '<span style="color:var(--text-secondary);">'+s.explanation+'</span></div>';
      html += '</div>';
    });
    html += '</div>';
  }

  if (sh && sh.top_contributors && sh.top_contributors.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--accent-purple);"></span>SHAP 归因分析</h3>';
    html += '<div style="font-size:12px;line-height:1.7;margin-bottom:8px;">'+sh.natural_summary+'</div>';
    html += '<button class="shap-explore-btn-open" onclick="event.stopPropagation();openShapExploration();">\u{1F50D} 交互式探索：查看单一特征对所有100台设备的影响</button>';
    sh.top_contributors.slice(0,5).forEach(function(c) {
      var dirColor = c.contribution > 0 ? 'var(--accent-red)' : 'var(--accent-green)';
      var arrow = c.contribution > 0 ? '↑' : '↓';
      html += '<div style="display:flex;justify-content:space-between;font-size:11px;padding:2px 0;">';
      html += '<span>'+c.feature+' <span style="color:var(--text-secondary);">('+c.category_label+')</span></span>';
      html += '<span style="color:'+dirColor+';font-family:monospace;">'+arrow+' '+(c.contribution>0?'+':'')+c.contribution.toFixed(3)+'</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  if (wo) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--accent-red);"></span>维护工单</h3>';
    html += '<div class="stat-row">';
    html += '<div class="stat-item"><div class="stat-label">优先级</div><div class="stat-value">#'+wo.priority+'</div></div>';
    html += '<div class="stat-item"><div class="stat-label">动作</div><div class="stat-value" style="font-size:14px;">'+wo.action_type+'</div></div>';
    html += '<div class="stat-item"><div class="stat-label">紧急度</div><div class="stat-value">'+wo.urgency_score+'</div></div>';
    html += '</div>';
    html += '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;">建议窗口: '+wo.window_days+'天 &nbsp;|&nbsp; 预期节省: $'+wo.expected_savings.toFixed(0)+'</div>';
    if (wo.top_risk_factor_1) {
      html += '<div style="font-size:11px;margin-top:8px;padding:8px;background:var(--bg-card);border-radius:4px;line-height:1.6;">';
      html += '<b>根因:</b> '+wo.top_risk_factor_1+'<br>';
      if (wo.top_risk_factor_2) html += '<b>次要:</b> '+wo.top_risk_factor_2+'<br>';
      if (wo.shap_risk_summary) html += '<b>风险分布:</b> '+wo.shap_risk_summary;
      html += '</div>';
    }
    html += '</div>';
  }

  if (sh && sh.inspection_checklist && sh.inspection_checklist.length > 0) {
    html += '<div class="panel-section">';
    html += '<h3><span class="dot" style="background:var(--accent-cyan);"></span>建议排查清单</h3>';
    sh.inspection_checklist.forEach(function(item, i) {
      html += '<div class="checklist-item"><span class="idx">'+(i+1)+'.</span> '+item+'</div>';
    });
    html += '</div>';
  }

  if (!sh && !wo) {
    html += '<div class="panel-section"><div style="text-align:center;color:var(--text-secondary);padding:20px;font-size:13px;">该设备无活跃工单，SHAP 数据不可用。<br>如需归因分析，请运行 Pipeline 并启用 --shap。</div></div>';
  }

  var strategy = sessionStorage.getItem('current_strategy') || 'production_efficiency';
  var strategyLabels = { cost_efficiency: '成本效率', production_efficiency: '生产效率', quality_first: '质量优先' };
  html += '<div class="panel-section">';
  html += '<button id="btn-add-tracking" style="width:100%;padding:10px;border-radius:10px;font-size:13px;cursor:pointer;border:0.5px solid var(--glass-border);background:rgba(102,217,200,0.08);color:var(--accent-cyan);font-family:var(--font-sans);transition:all 0.2s;" onclick="addToTracking(\''+mid+'\')">+ 加入工单跟踪（'+ (strategyLabels[strategy] || strategy) +'）</button>';
  html += '</div>';

  var panelBody = document.getElementById('panel-body');
  if (panelBody) panelBody.innerHTML = html;

  var detailPanel = document.getElementById('detail-panel');
  var panelOverlay = document.getElementById('panel-overlay');
  if (detailPanel) detailPanel.classList.add('open');
  if (panelOverlay) panelOverlay.classList.add('open');
}

function closePanel() {
  var detailPanel = document.getElementById('detail-panel');
  var panelOverlay = document.getElementById('panel-overlay');
  if (detailPanel) detailPanel.classList.remove('open');
  if (panelOverlay) panelOverlay.classList.remove('open');
}

// ── Work order tracking ──
function addToTracking(machineId) {
  var strategy = sessionStorage.getItem('current_strategy') || 'production_efficiency';
  var strategyLabels = { cost_efficiency: '成本效率', production_efficiency: '生产效率', quality_first: '质量优先' };
  var btn = document.getElementById('btn-add-tracking');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = '... 正在加入 ...';

  function doCreate(force) {
    fetch('/api/work-order/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ machine_id: machineId, strategy: strategy, force: force })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.success) {
        btn.textContent = d.transferred ? '已转移到当前策略' : '已加入工单跟踪';
        btn.style.background = 'rgba(63,185,80,0.1)';
        btn.style.borderColor = 'var(--accent-green)';
        btn.style.color = 'var(--accent-green)';
      } else if (d.same_strategy) {
        btn.textContent = '已在跟踪中';
        btn.style.background = 'rgba(240,160,48,0.1)';
        btn.style.borderColor = 'var(--accent-amber)';
        btn.style.color = 'var(--accent-amber)';
      } else if (d.different_strategy) {
        var oldLabel = strategyLabels[d.old_strategy] || d.old_strategy;
        var newLabel = strategyLabels[strategy] || strategy;
        if (confirm(machineId + ' 已在「' + oldLabel + '」策略下存在工单。\n\n是否转移到「' + newLabel + '」策略？\n（原工单及其分配记录将被清除）')) {
          doCreate(true);
        } else {
          btn.textContent = '+ 加入工单跟踪（' + (strategyLabels[strategy] || strategy) + '）';
          btn.disabled = false;
        }
      } else {
        btn.textContent = '操作失败: ' + (d.detail || '未知错误');
        btn.disabled = false;
      }
    })
    .catch(function() {
      btn.textContent = '网络错误';
      btn.disabled = false;
    });
  }
  doCreate(false);
}

// ── Baseline trace panel ──
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
  var titleEl = document.getElementById('trace-title');
  var bodyEl = document.getElementById('trace-body');
  var panel = document.getElementById('trace-panel');
  var overlay = document.getElementById('trace-overlay');
  if (titleEl) titleEl.textContent = title;
  if (bodyEl) bodyEl.innerHTML = body;
  if (panel) panel.classList.add('open');
  if (overlay) overlay.classList.add('open');
}

function closeTrace() {
  var panel = document.getElementById('trace-panel');
  var overlay = document.getElementById('trace-overlay');
  if (panel) panel.classList.remove('open');
  if (overlay) overlay.classList.remove('open');
}

function buildHealthTrace(mid, h, b) {
  if (!h) return '<p style="color:var(--text-secondary)">健康分数据不可用</p>';
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
  var html = '<p>该设备健康分仅 <b style="color:var(--accent-red)">' + score.toFixed(0) + '</b> 分（满分100），判定为<b>"' + (h.health_level || '--') + '"</b>级别，主要由以下因素驱动：</p>';
  dims.forEach(function(d, i) {
    var contrib = (d.w * d.v).toFixed(2);
    var colors = ['var(--accent-red)', 'var(--accent-red)', 'var(--accent-amber)', 'var(--text-secondary)'];
    html += '<div class="trace-item"><span class="ti-label">' + d.label + '（权重' + (d.w * 100).toFixed(0) + '%）</span><span class="ti-val">' + d.raw + ' → 贡献 ' + contrib + '</span></div>';
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

// ── SHAP interactive exploration ──
function openShapExploration() {
  if (!shapScatterData) return;
  var sel = document.getElementById('shap-feature-select');
  if (!sel) return;
  sel.innerHTML = shapScatterData.meta.features.map(function(f) {
    return '<option value="' + f.feature_id + '">' + f.display_name + ' (' + f.unit + ')</option>';
  }).join('');
  var overlay = document.getElementById('shap-explore-overlay');
  if (overlay) overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
  sel.value = shapScatterData.meta.features[0].feature_id;
  renderShapScatter();
}

function closeShapExploration() {
  var overlay = document.getElementById('shap-explore-overlay');
  if (overlay) overlay.classList.remove('open');
  document.body.style.overflow = '';
}

function renderShapScatter() {
  var sel = document.getElementById('shap-feature-select');
  if (!sel) return;
  var fid = sel.value;
  var featMeta = shapScatterData.meta.features.find(function(f) { return f.feature_id === fid; });
  if (!featMeta) return;

  var scatterData = [];
  var machines = shapScatterData.machines;
  Object.keys(machines).sort().forEach(function(mid) {
    var m = machines[mid];
    var fv = m.features[fid];
    if (!fv) return;
    scatterData.push([fv.value, fv.contribution, mid, m.health_level, m.risk_score]);
  });

  var nonZero = scatterData.filter(function(d) { return Math.abs(d[1]) > 0.0001; }).length;
  var maxContrib = 0, maxMid = '';
  scatterData.forEach(function(d) { if (Math.abs(d[1]) > Math.abs(maxContrib)) { maxContrib = d[1]; maxMid = d[2]; } });
  var tagline = document.getElementById('shap-tagline');
  if (tagline) tagline.innerHTML = '<b>' + nonZero + '</b>/' + scatterData.length + ' 台设备受此特征显著影响 | 最大贡献: <b>' + maxMid + '</b> (' + (maxContrib > 0 ? '+' : '') + maxContrib.toFixed(4) + ')';

  var nTotal = scatterData.length;
  var nPositive = scatterData.filter(function(d) { return d[1] > 0.001; }).length;
  var nNegative = scatterData.filter(function(d) { return d[1] < -0.001; }).length;
  var meanContrib = scatterData.reduce(function(s, d) { return s + d[1]; }, 0) / nTotal;
  var stats = document.getElementById('shap-explore-stats');
  if (stats) stats.innerHTML =
    '<span>设备数: <b>' + nTotal + '</b></span>' +
    '<span style="color:var(--accent-red);">风险↑ <b>' + nPositive + '</b></span>' +
    '<span style="color:var(--accent-green);">风险↓ <b>' + nNegative + '</b></span>' +
    '<span>均值贡献: <b>' + (meanContrib > 0 ? '+' : '') + meanContrib.toFixed(4) + '</b></span>';

  var isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  var textPrimary = isDark ? '#f5f5f7' : '#1d1d1f';
  var textSecondary = isDark ? '#aeaeb2' : '#6e6e73';
  var gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
  var levelColor = { 'Healthy': '#30d158', 'Warning': '#ffb340', 'Degrading': '#ff9500', 'Critical': '#ff453a' };

  var dom = document.getElementById('chart-shap-scatter');
  if (!dom) return;
  var chart = echarts.getInstanceByDom(dom);
  if (!chart) chart = echarts.init(dom, isDark ? null : 'light');

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: isDark ? 'rgba(30,30,32,0.96)' : 'rgba(255,255,255,0.96)',
      borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
      textStyle: { color: textPrimary, fontSize: 12 },
      formatter: function(p) {
        var v = p.value;
        return '<b>' + v[2] + '</b><br/>' + featMeta.display_name + ': <b>' + (typeof v[0] === 'number' ? v[0].toFixed(3) : v[0]) + ' ' + featMeta.unit + '</b><br/>SHAP贡献: <b>' + (v[1] > 0 ? '+' : '') + v[1].toFixed(4) + '</b><br/>健康: <b>' + v[3] + '</b>';
      }
    },
    grid: { left: 60, right: 30, top: 16, bottom: 40 },
    xAxis: {
      type: 'value', name: featMeta.display_name + ' (' + featMeta.unit + ')',
      nameTextStyle: { color: textSecondary, fontSize: 11 },
      axisLabel: { color: textSecondary, fontSize: 10 },
      splitLine: { lineStyle: { color: gridColor } }
    },
    yAxis: {
      type: 'value', name: 'SHAP 贡献值',
      nameTextStyle: { color: textSecondary, fontSize: 11 },
      axisLabel: { color: textSecondary, fontSize: 10 },
      splitLine: { lineStyle: { color: gridColor } }
    },
    series: [{
      type: 'scatter',
      data: scatterData,
      symbolSize: function(v) { return Math.min(14, Math.max(4, Math.abs(v[4]) * 15)); },
      itemStyle: {
        color: function(p) {
          var c = levelColor[p.value[3]] || '#8e9aab';
          return c;
        },
        opacity: 0.75
      },
      emphasis: { itemStyle: { opacity: 1, borderColor: '#fff', borderWidth: 1 } }
    }]
  });
}

// ── Event listeners ──
document.addEventListener('contextmenu', function(e) {
  var el = e.target.closest('[data-trace]');
  if (!el) return;
  e.preventDefault();
  var type = el.getAttribute('data-trace');
  var mid = el.getAttribute('data-trace-mid');
  if (type && mid) showTrace(type, mid);
});
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeTrace(); closeShapExploration(); }
});

// Manual bootstrap — each page calls initDeviceGrid() when ready
// (DOMContentLoaded listener removed to avoid conflict with home.html's init())
