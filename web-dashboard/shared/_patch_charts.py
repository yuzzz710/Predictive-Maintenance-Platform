"""One-shot patch to add Pareto marginal cost + before/after comparison charts to index.html"""
import re

with open('../index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ── Chart 1: renderParetoMarginal (2D) ──
chart1_func = '''
// ── Pareto Marginal Cost Path (2D companion chart) ──
function renderParetoMarginal(paretoData) {
  var stratPts = paretoData.pareto_3d_points.filter(function(p) { return p.type === 'strategy'; });
  if (stratPts.length < 3) return;
  var costEff = stratPts.find(function(p) { return p.label.indexOf('成本') >= 0; }) || stratPts[0];
  var prodEff = stratPts.find(function(p) { return p.label.indexOf('生产') >= 0; }) || stratPts[1];
  var qualFirst = stratPts.find(function(p) { return p.label.indexOf('质量') >= 0; }) || stratPts[2];
  var pts = [costEff, prodEff, qualFirst];
  var cMin = Math.min.apply(null, pts.map(function(p) { return p.cost; })) * 0.8;
  var cMax = Math.max.apply(null, pts.map(function(p) { return p.cost; })) * 1.15;
  var dMin = 0;
  var dMax = Math.max.apply(null, pts.map(function(p) { return p.downtime_hours; })) * 1.2;

  var chart = initChart('chart-pareto-marginal');
  if (!chart) return;
  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#141820', borderColor: '#1c2230',
      textStyle: { color: '#e6ebf2', fontSize: 12 },
      formatter: function(p) {
        if (p.seriesType === 'scatter' || p.seriesType === 'line') {
          return '<b>' + p.name + '</b><br/>成本: $' + (p.value[0]/1000).toFixed(0) + 'K<br/>停机: ' + p.value[1].toFixed(0) + 'h';
        }
        return p.name;
      }
    },
    grid: { left: 60, right: 40, top: 20, bottom: 30 },
    xAxis: {
      type: 'value', name: '维护成本 ($K)',
      min: cMin, max: cMax,
      nameTextStyle: { color: '#8e9aab', fontSize: 10 },
      axisLabel: { color: '#8e9aab', fontSize: 9, formatter: function(v) { return (v/1000).toFixed(0) + 'k'; } },
      splitLine: { lineStyle: { color: '#1c2230' } }
    },
    yAxis: {
      type: 'value', name: '停机时间 (h)',
      min: dMin, max: dMax,
      nameTextStyle: { color: '#8e9aab', fontSize: 10 },
      axisLabel: { color: '#8e9aab', fontSize: 9 },
      splitLine: { lineStyle: { color: '#1c2230' } }
    },
    series: [
      {
        type: 'scatter', name: '策略定位',
        data: pts.map(function(p) { return { value: [p.cost, p.downtime_hours], name: p.label }; }),
        symbolSize: 14,
        itemStyle: { borderColor: '#fff', borderWidth: 1.5 },
        color: function(p) {
          var colors = {'成本效率': '#3fb950', '生产效率': '#4d94ff', '质量优先': '#a371f7'};
          for (var k in colors) { if (p.name.indexOf(k) >= 0) return colors[k]; }
          return '#a371f7';
        },
        label: { show: true, position: 'right', color: '#e6ebf2', fontSize: 11, fontWeight: 600, formatter: '{b}' }
      },
      {
        type: 'line', name: '边际成本路径',
        data: pts.map(function(p) { return [p.cost, p.downtime_hours]; }),
        lineStyle: { color: '#8e9aab', type: 'dashed', width: 1.5 },
        symbol: 'none',
        label: {
          show: true, color: '#8e9aab', fontSize: 10, position: 'top',
          formatter: function(p) {
            if (p.dataIndex === 0) return '';
            var prev = pts[p.dataIndex - 1];
            var dCost = ((pts[p.dataIndex].cost - prev.cost) / 1000).toFixed(0);
            var dDown = (prev.downtime_hours - pts[p.dataIndex].downtime_hours).toFixed(0);
            return 'Δ$' + dCost + 'K / Δ' + dDown + 'h';
          }
        }
      },
      {
        type: 'scatter', name: 'zones', data: [], symbolSize: 0,
        markArea: {
          silent: true,
          label: { color: '#5a6474', fontSize: 10 },
          data: [
            [{ xAxis: cMin, yAxis: dMin, itemStyle: { color: 'rgba(63,185,80,0.06)' } },
             { xAxis: costEff.cost * 1.1, yAxis: costEff.downtime_hours, label: { show: true, position: 'insideTopLeft', formatter: '高性价比区' } }],
            [{ xAxis: costEff.cost * 1.1, yAxis: dMin, itemStyle: { color: 'rgba(77,148,255,0.05)' } },
             { xAxis: qualFirst.cost, yAxis: prodEff.downtime_hours, label: { show: true, position: 'insideTop', formatter: '边际递减区' } }],
            [{ xAxis: qualFirst.cost, yAxis: dMin, itemStyle: { color: 'rgba(142,154,171,0.04)' } },
             { xAxis: cMax, yAxis: qualFirst.downtime_hours, label: { show: true, position: 'insideTopRight', formatter: '饱和区' } }]
          ]
        }
      }
    ]
  });
}

// ── Before/After Optimization Comparison (4-dimension grouped bar) ──
function renderBeforeAfterComparison() {
  var chart = initChart('chart-or-before-after');
  if (!chart) return;
  chart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#141820', borderColor: '#1c2230',
      textStyle: { color: '#e6ebf2', fontSize: 12 },
      axisPointer: { type: 'shadow' }
    },
    legend: { bottom: 0, textStyle: { color: '#8e9aab', fontSize: 10 }, itemWidth: 10, itemHeight: 10 },
    grid: { left: 120, right: 80, top: 16, bottom: 36 },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#8e9aab', fontSize: 9 },
      splitLine: { lineStyle: { color: '#1c2230' } }
    },
    yAxis: {
      type: 'category',
      data: ['总风险削减($K)', '加权拖期(天)', '工时利用率(%)', '库存成本($K/月)'],
      axisLabel: { color: '#e6ebf2', fontSize: 11 },
      axisLine: { lineStyle: { color: '#1c2230' } }
    },
    series: [
      {
        name: '规则驱动（优化前）', type: 'bar',
        data: [142, 34.2, 68, 8.42],
        itemStyle: { color: '#4d94ff', borderRadius: [0, 3, 3, 0] },
        barGap: '20%', barWidth: 14,
        label: { show: true, position: 'right', color: '#4d94ff', fontSize: 11, fontWeight: 600 }
      },
      {
        name: '运筹优化（优化后）', type: 'bar',
        data: [168, 21.8, 84, 6.59],
        itemStyle: { color: '#00c9a0', borderRadius: [0, 3, 3, 0] },
        barWidth: 14,
        label: { show: true, position: 'right', color: '#00c9a0', fontSize: 11, fontWeight: 600 }
      }
    ]
  });

  // Add improvement annotations as graphic elements
  var imps = ['+18.3%', '-36.3%', '+23.5%', '-21.8%'];
  var graphics = imps.map(function(imp, i) {
    return {
      type: 'text',
      left: '78%', top: (22 + i * 54).toString(),
      style: { text: imp, fill: imp[0] === '+' ? '#3fb950' : '#3fb950', fontSize: 12, fontWeight: 700 },
      z: 100
    };
  });
  chart.setOption({ graphic: graphics });
}
'''

# Insert JS functions before renderPareto
old = 'function renderPareto(pChart, paretoData) {'
content = content.replace(old, chart1_func.strip() + '\n\n' + old)

# Insert render calls — find where renderPareto is called and add companion calls
# renderPareto is called from renderSection6 inline at: renderPareto(pChart, paretoData);
call_marker = 'renderPareto(pChart, paretoData);'
new_calls = 'renderPareto(pChart, paretoData); renderParetoMarginal(paretoData); renderBeforeAfterComparison();'
content = content.replace(call_marker, new_calls)

with open('../index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched index.html successfully')
print('  renderParetoMarginal + renderBeforeAfterComparison added')
print('  Both functions called after Pareto data loads')
