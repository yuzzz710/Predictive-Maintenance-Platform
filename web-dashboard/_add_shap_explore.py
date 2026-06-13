"""Add SHAP interactive exploration to device-grid.html"""
with open('device-grid.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add echarts CDN after papaparse
old_cdn = '<script src="https://cdn.jsdelivr.net/npm/papaparse@5.4.1/papaparse.min.js"></script>'
new_cdn = '<script src="https://cdn.jsdelivr.net/npm/papaparse@5.4.1/papaparse.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>'
content = content.replace(old_cdn, new_cdn)

# 2. Add SHAP explore CSS
shap_css = '''
/* ── SHAP Interactive Exploration ── */
.shap-explore-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 3000; display: none; opacity: 0;
  transition: opacity 0.25s ease;
  backdrop-filter: blur(2px);
}
.shap-explore-overlay.open { display: flex; align-items: center; justify-content: center; opacity: 1; }
.shap-explore-modal {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; width: 920px; max-width: 95vw; max-height: 90vh;
  overflow-y: auto; box-shadow: 0 16px 64px rgba(0,0,0,0.4);
  display: flex; flex-direction: column;
}
.shap-explore-header {
  position: sticky; top: 0; z-index: 10; background: var(--bg-card);
  padding: 20px 24px 14px; border-bottom: 1px solid var(--border);
  display: flex; align-items: flex-start; justify-content: space-between;
}
.shap-explore-title { font-size: 18px; font-weight: 700; color: var(--purple); }
.shap-explore-subtitle { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.shap-explore-close {
  background: none; border: none; color: var(--text-muted);
  font-size: 22px; cursor: pointer; padding: 4px 8px;
  border-radius: 4px; transition: all 0.2s;
}
.shap-explore-close:hover { background: var(--red); color: #fff; }
.shap-explore-body { padding: 16px 24px 24px; }
.shap-explore-controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.shap-explore-label { font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.shap-explore-select {
  padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg-input); color: var(--text-primary); font-size: 13px;
  cursor: pointer; min-width: 200px;
}
.shap-explore-select:focus { outline: none; border-color: var(--purple); }
.shap-explore-tagline { font-size: 12px; color: var(--text-muted); width: 100%; margin-top: 4px; }
.shap-explore-chart { width: 100%; }
.shap-explore-stats { display: flex; gap: 20px; padding: 8px 0; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; }
.shap-explore-stats b { color: var(--text-primary); }
'''

trace_marker = '/* ── Trace Panel ── */'
content = content.replace(trace_marker, shap_css + '\n' + trace_marker)

# 3. Add SHAP modal HTML before trace overlay
shap_html = '''
<div class="shap-explore-overlay" id="shap-explore-overlay">
  <div class="shap-explore-modal">
    <div class="shap-explore-header">
      <div>
        <div class="shap-explore-title">SHAP 归因交互式探索</div>
        <div class="shap-explore-subtitle" id="shap-explore-subtitle">选择一个特征，查看其对所有100台设备风险评分的影响</div>
      </div>
      <button class="shap-explore-close" onclick="closeShapExploration()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
    </div>
    <div class="shap-explore-body">
      <div class="shap-explore-controls">
        <label class="shap-explore-label">选择特征:</label>
        <select class="shap-explore-select" id="shap-feature-select" onchange="renderShapScatter()"></select>
        <div class="shap-explore-tagline" id="shap-tagline"></div>
      </div>
      <div class="shap-explore-chart" id="chart-shap-scatter" style="height:460px;"></div>
      <div class="shap-explore-stats" id="shap-explore-stats"></div>
    </div>
  </div>
</div>
'''

old_trace_html = '<div class="trace-overlay" id="trace-overlay"'
content = content.replace(old_trace_html, shap_html + '\n' + old_trace_html)

# 4. Add shapScatterData loading in init
old_shap_load = "fetch('data/shap_dashboard.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; })"
new_shap_load = "fetch('data/shap_dashboard.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),\n      fetch('data/shap_scatter_data.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; })"
content = content.replace(old_shap_load, new_shap_load)

# Update the destructuring to capture shapScatterData
old_destructure = "var [healthData, woData, shapJson] = await Promise.all(["
new_destructure = "var [healthData, woData, shapJson, shapScatterData] = await Promise.all(["
content = content.replace(old_destructure, new_destructure)

# 5. Add SHAP exploration functions before DOMContentLoaded
old_dom = "document.addEventListener('DOMContentLoaded', init);"

shap_js = '''
var shapScatterData = null;

function openShapExploration() {
  if (!shapScatterData) return;
  var sel = document.getElementById('shap-feature-select');
  sel.innerHTML = shapScatterData.meta.features.map(function(f) {
    return '<option value="' + f.feature_id + '">' + f.display_name + ' (' + f.unit + ')</option>';
  }).join('');
  document.getElementById('shap-explore-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  sel.value = shapScatterData.meta.features[0].feature_id;
  renderShapScatter();
}

function closeShapExploration() {
  document.getElementById('shap-explore-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

function renderShapScatter() {
  var sel = document.getElementById('shap-feature-select');
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
  document.getElementById('shap-tagline').innerHTML =
    '<b>' + nonZero + '</b>/' + scatterData.length + ' 台设备受此特征显著影响 | 最大贡献: <b>' + maxMid + '</b> (' + (maxContrib > 0 ? '+' : '') + maxContrib.toFixed(4) + ')';

  var nTotal = scatterData.length;
  var nPositive = scatterData.filter(function(d) { return d[1] > 0.001; }).length;
  var nNegative = scatterData.filter(function(d) { return d[1] < -0.001; }).length;
  var meanContrib = scatterData.reduce(function(s, d) { return s + d[1]; }, 0) / nTotal;
  document.getElementById('shap-explore-stats').innerHTML =
    '<span>设备数: <b>' + nTotal + '</b></span>' +
    '<span style="color:var(--red);">风险↑ <b>' + nPositive + '</b></span>' +
    '<span style="color:var(--green);">风险↓ <b>' + nNegative + '</b></span>' +
    '<span>均值贡献: <b>' + (meanContrib > 0 ? '+' : '') + meanContrib.toFixed(4) + '</b></span>';

  var isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  var textPrimary = isDark ? '#e6ebf2' : '#1a1d26';
  var levelColor = { 'Healthy': '#3fb950', 'Warning': '#f0a030', 'Degrading': '#f0883e', 'Critical': '#f04444' };

  var dom = document.getElementById('chart-shap-scatter');
  var chart = echarts.getInstanceByDom(dom);
  if (!chart) chart = echarts.init(dom, isDark ? null : 'light');

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: isDark ? 'rgba(20,24,32,0.95)' : 'rgba(255,255,255,0.95)',
      borderColor: isDark ? '#2a3a50' : '#d0d7de',
      textStyle: { color: textPrimary, fontSize: 12 },
      formatter: function(p) {
        var v = p.value;
        return '<b>' + v[2] + '</b><br/>' + featMeta.display_name + ': <b>' + (typeof v[0] === 'number' ? v[0].toFixed(3) : v[0]) + ' ' + featMeta.unit + '</b><br/>SHAP贡献: <b>' + (v[1] > 0 ? '+' : '') + v[1].toFixed(4) + '</b><br/>健康: <b>' + v[3] + '</b>';
      }
    },
    grid: { left: 60, right: 30, top: 16, bottom: 40 },
    xAxis: {
      type: 'value', name: featMeta.display_name + ' (' + featMeta.unit + ')',
      nameTextStyle: { color: textSecondary, fontSize: 10 },
      axisLabel: { color: textSecondary, fontSize: 9 },
      splitLine: { lineStyle: { color: isDark ? '#1c2230' : '#e8ecf0' } }
    },
    yAxis: {
      type: 'value', name: 'SHAP 贡献值',
      nameTextStyle: { color: textSecondary, fontSize: 10 },
      axisLabel: { color: textSecondary, fontSize: 9 },
      splitLine: { lineStyle: { color: isDark ? '#1c2230' : '#e8ecf0' } }
    },
    series: [{
      type: 'scatter',
      data: scatterData,
      symbolSize: function(v) { return Math.min(14, Math.max(4, Math.abs(v[4]) * 15)); },
      itemStyle: {
        color: function(p) {
          var c = levelColor[p.value[3]] || '#8e9aab';
          return p.value[1] > 0 ? c : c;
        },
        opacity: 0.7
      },
      emphasis: { itemStyle: { opacity: 1, borderColor: '#fff', borderWidth: 1 } }
    }]
  });
}

'''

content = content.replace(old_dom, shap_js + '\n' + old_dom)

with open('device-grid.html', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'SHAP exploration added. Size: {len(content)} bytes')
