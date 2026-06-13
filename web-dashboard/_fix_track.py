with open('device-grid.html', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('function addToTracking(machineId)')
if idx < 0:
    print('Function not found')
    exit(1)

# Find the closing brace of the function
brace_count = 0
end_idx = idx
started = False
for i in range(idx, len(content)):
    if content[i] == '{':
        brace_count += 1
        started = True
    elif content[i] == '}':
        brace_count -= 1
        if started and brace_count == 0:
            end_idx = i + 1
            break

new_func = '''function addToTracking(machineId) {
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
        btn.style.borderColor = 'var(--green)';
        btn.style.color = 'var(--green)';
      } else if (d.same_strategy) {
        btn.textContent = '已在跟踪中';
        btn.style.background = 'rgba(240,160,48,0.1)';
        btn.style.borderColor = 'var(--amber)';
        btn.style.color = 'var(--amber)';
      } else if (d.different_strategy) {
        var oldLabel = strategyLabels[d.old_strategy] || d.old_strategy;
        var newLabel = strategyLabels[strategy] || strategy;
        if (confirm(machineId + ' 已在「' + oldLabel + '」策略下存在工单。\\n\\n是否转移到「' + newLabel + '」策略？\\n（原工单及其分配记录将被清除）')) {
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
}'''

content = content[:idx] + new_func + content[end_idx:]
with open('device-grid.html', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'addToTracking replaced ({idx}-{end_idx})')
