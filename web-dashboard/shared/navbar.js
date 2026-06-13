/**
 * Shared Global Navigation Bar
 * =============================
 * Injects a unified top nav into any page. Self-contained CSS + HTML.
 * Detects active page from window.location.pathname.
 *
 * Usage: <script src="/shared/navbar.js"></script>
 */

(function () {
  var path = window.location.pathname;

  // Determine active tab
  var activeTab = 'home';
  if (path === '/' || path === '/home' || path.startsWith('/home')) activeTab = 'home';
  else if (path === '/device-grid' || path.startsWith('/device-grid')) activeTab = 'device-grid';
  else if (path === '/dashboard' || path.startsWith('/dashboard')) activeTab = 'dashboard';
  else if (path === '/chat' || path.startsWith('/chat')) activeTab = 'chat';
  else if (path === '/work-order-tracking' || path.startsWith('/work-order-tracking')) activeTab = 'tracking';
  else if (path === '/workflows' || path.startsWith('/workflows')) activeTab = 'workflows';
  else if (path === '/inventory' || path.startsWith('/inventory')) activeTab = 'inventory';
  else if (path === '/technicians' || path.startsWith('/technicians')) activeTab = 'technicians';
  else if (path === '/technical-overview' || path.startsWith('/technical-overview')) activeTab = 'tech';
  else if (path === '/knowledge-base' || path.startsWith('/knowledge-base')) activeTab = 'kb';
  else if (path === '/reports' || path.startsWith('/reports')) activeTab = 'reports';

  // ── CSS ──
  var css = [
    ':root {',
    '  --gn-popup-bg: #ffffff;',
    '  --gn-popup-alt: #f5f6f8;',
    '  --gn-popup-border: #e2e6ed;',
    '}',
    '[data-theme="light"] {',
    '  --gn-popup-bg: #ffffff;',
    '  --gn-popup-alt: #f5f6f8;',
    '  --gn-popup-border: #e2e6ed;',
    '}',
    'body.gn-transitioning { opacity: 1; transition: none; }',
    'html[data-role="operator"] .role-manager:not(.role-operator) { display: none !important; }',
    'html[data-role="operator"] .role-developer:not(.role-operator) { display: none !important; }',
    'html[data-role="manager"] .role-developer:not(.role-manager) { display: none !important; }',
    '.gn-degrade-popup {',
    '  position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%) scale(0.95);',
    '  width: 440px; max-width: 94vw; max-height: 84vh; overflow-y: auto;',
    '  background: var(--gn-popup-bg); border: 1px solid var(--gn-popup-border);',
    '  border-radius: 12px; box-shadow: 0 24px 64px rgba(0,0,0,0.15);',
    '  z-index: 9999; padding: 28px 32px 24px; font-size: 13px;',
    '  color: var(--gn-text-secondary, #4a5568); line-height: 1.6;',
    '  opacity: 0; pointer-events: none;',
    '  transition: opacity 0.2s ease-out, transform 0.2s ease-out;',
    '}',
    '.gn-degrade-popup.show { opacity: 1; pointer-events: auto; transform: translate(-50%,-50%) scale(1); }',
    '.gn-degrade-overlay {',
    '  position: fixed; inset: 0; background: rgba(0,0,0,0.35);',
    '  backdrop-filter: blur(2px); z-index: 9998;',
    '  opacity: 0; pointer-events: none; transition: opacity 0.2s ease-out;',
    '}',
    '.gn-degrade-overlay.show { opacity: 1; pointer-events: auto; }',
    '.gn-degrade-popup .dg-header {',
    '  display: flex; align-items: center; gap: 10px; margin-bottom: 20px;',
    '  padding-bottom: 16px; border-bottom: 1px solid var(--gn-popup-border);',
    '}',
    '.gn-degrade-popup .dg-header-icon {',
    '  width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;',
    '  display: flex; align-items: center; justify-content: center;',
    '}',
    '.gn-degrade-popup .dg-header-icon svg { width: 20px; height: 20px; }',
    '.gn-degrade-popup .dg-title { font-size: 15px; font-weight: 600; color: var(--gn-text, #1a1d26); }',
    '.gn-degrade-popup .dg-subtitle { font-size: 11px; color: var(--gn-text-muted, #7a8498); }',
    '.gn-degrade-popup .dg-section { margin-bottom: 16px; }',
    '.gn-degrade-popup .dg-section-label {',
    '  font-size: 10px; font-weight: 600; text-transform: uppercase;',
    '  letter-spacing: 0.05em; color: var(--gn-text-muted, #7a8498); margin-bottom: 8px;',
    '}',
    '.gn-degrade-popup .dg-module {',
    '  display: flex; align-items: center; justify-content: space-between;',
    '  padding: 10px 14px; margin-bottom: 4px;',
    '  background: var(--gn-popup-alt); border-radius: 8px;',
    '}',
    '.gn-degrade-popup .dg-module-name { font-size: 13px; font-weight: 500; color: var(--gn-text, #1a1d26); }',
    '.gn-degrade-popup .dg-module-status {',
    '  display: inline-flex; align-items: center; gap: 6px;',
    '  font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 6px;',
    '}',
    '.gn-degrade-popup .dg-module-status.ok { background: rgba(63,185,80,0.08); color: #2d8a3e; }',
    '.gn-degrade-popup .dg-module-status.fail { background: rgba(240,68,68,0.08); color: #c0392b; }',
    '.gn-degrade-popup .dg-module-status svg { width: 14px; height: 14px; }',
    '.gn-degrade-popup .dg-desc {',
    '  font-size: 12px; color: var(--gn-text-secondary, #4a5568);',
    '  padding: 12px 14px; background: var(--gn-popup-alt);',
    '  border-radius: 8px; border-left: 3px solid var(--gn-popup-border); line-height: 1.7;',
    '}',
    '.gn-degrade-popup .dg-desc code {',
    '  display: block; margin-top: 4px; padding: 6px 10px;',
    '  background: rgba(0,0,0,0.04); border: 1px solid var(--gn-popup-border); border-radius: 4px;',
    '  font-family: var(--font-mono, monospace); font-size: 11px;',
    '  color: var(--gn-text-secondary, #4a5568); word-break: break-all;',
    '}',
    '.gn-degrade-popup .dg-close {',
    '  position: absolute; top: 16px; right: 16px; width: 28px; height: 28px;',
    '  border-radius: 8px; border: none; background: transparent;',
    '  color: var(--gn-text-muted, #7a8498); cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '  transition: background 0.15s, color 0.15s;',
    '}',
    '.gn-degrade-popup .dg-close:hover { background: var(--gn-popup-alt); color: var(--gn-text, #1a1d26); }',

  ].join('\n');

  // ── HTML ──
  var links = [
    { href: '/', label: '首页', icon: '&#9679;', key: 'home' },
    { href: '/device-grid', label: '设备矩阵', icon: '&#9633;', key: 'device-grid' },
    { href: '/dashboard', label: '仪表盘', icon: '&#9632;', key: 'dashboard' },
    { href: '/chat', label: 'AI Copilot', icon: '&#9881;', key: 'chat' },
    { href: '/work-order-tracking', label: '工单跟踪', icon: '&#128203;', key: 'tracking' },
    { href: '/workflows', label: '工作流', icon: '&#9889;', key: 'workflows' },
    { href: '/inventory', label: '库存', icon: '&#128230;', key: 'inventory', role: 'role-manager' },
    { href: '/technicians', label: '员工', icon: '&#128101;', key: 'technicians', role: 'role-manager' },
    { href: '/technical-overview', label: '技术架构', icon: '&#9776;', key: 'tech', role: 'role-developer' },
    { href: '/knowledge-base', label: '知识库', icon: '&#128218;', key: 'kb', role: 'role-developer' },
    { href: '/reports', label: '报告', icon: '&#128196;', key: 'reports' }
  ];

  function buildLinksHtml() {
    return links.map(function (l) {
      var cls = l.key === activeTab ? 'gn-link active' : 'gn-link';
      if (l.role) cls += ' ' + l.role;
      return '<a class="' + cls + '" href="' + l.href + '">' +
        '<span class="gn-link-icon">' + l.icon + '</span>' + l.label + '</a>';
    }).join('');
  }

  function buildNavHtml() {
    return '<nav id="global-nav">' +
      '<div class="gn-inner">' +
      '<a class="gn-logo" href="/">' +
      '<span class="gn-logo-dot"></span>' +
      '<span class="gn-logo-text">工业智能运维</span>' +
      '</a>' +
      '<div class="gn-links">' + buildLinksHtml() + '</div>' +
      '<div class="gn-right">' +
      '<div class="gn-role-toggle" id="gn-role-toggle" title="点击切换角色">' +
      '<span class="gn-role-dot" id="gn-role-dot"></span>' +
      '<span id="gn-role-label">运维工程师</span>' +
      '</div>' +
      '<button class="gn-theme-btn" id="gn-theme-btn" title="切换浅色/深色模式">☀ 浅色</button>' +
      '<div class="gn-status" id="gn-status" title="点击查看系统状态详情" style="cursor:pointer;">' +
      '<span class="gn-status-dot" id="gn-status-dot"></span>' +
      '<span id="gn-status-text">检测中...</span>' +
      '</div>' +
      '<span class="gn-badge">v2.0 &middot; 半决赛版</span>' +
      '</div>' +
      '</div>' +
      '</nav>';
  }

  // ── Injection (deferred until DOM is ready) ──
  function inject() {
    console.log('[global-nav] inject() running, active:', activeTab);

    // Preconnect CDN origins for faster resource loading
    ['https://cdn.jsdelivr.net'].forEach(function(origin) {
      var link = document.createElement('link');
      link.rel = 'preconnect'; link.href = origin; link.crossOrigin = 'anonymous';
      document.head.appendChild(link);
    });

    // Inject CSS
    var style = document.createElement('style');
    style.id = 'global-nav-css';
    style.textContent = css;
    document.head.appendChild(style);

    // Inject nav HTML
    var container = document.createElement('div');
    container.innerHTML = buildNavHtml();
    var navEl = container.firstElementChild;

    if (document.body.firstChild) {
      document.body.insertBefore(navEl, document.body.firstChild);
    } else {
      document.body.appendChild(navEl);
    }

    // Handle old headers
    if (path === '/' || path === '' || path.startsWith('/?')) {
      var offsetStyle = document.createElement('style');
      offsetStyle.textContent = '.header { /* sidebar layout — no top offset */ }';
      document.head.appendChild(offsetStyle);
    } else {
      var oldHeaders = document.querySelectorAll('.header');
      for (var i = 0; i < oldHeaders.length; i++) {
        oldHeaders[i].style.display = 'none';
      }
    }

    // ── Degradation Status ──
    (function initDegradeStatus() {
      var popup = document.createElement('div');
      popup.className = 'gn-degrade-popup';
      popup.id = 'gn-degrade-popup';
      popup.innerHTML = '<button class="dg-close" onclick="document.getElementById(\'gn-degrade-popup\').classList.remove(\'show\');document.getElementById(\'gn-degrade-overlay\').classList.remove(\'show\')">&times;</button>' +
        '<h3 id="dg-title"></h3><div id="dg-body"></div>';
      document.body.appendChild(popup);

      var overlay = document.createElement('div');
      overlay.className = 'gn-degrade-overlay';
      overlay.id = 'gn-degrade-overlay';
      overlay.onclick = function() { popup.classList.remove('show'); overlay.classList.remove('show'); };
      document.body.appendChild(overlay);

      function updateStatus(data) {
        var dot = document.getElementById('gn-status-dot');
        var text = document.getElementById('gn-status-text');
        if (!dot || !text) return;
        var mode = (data && data.mode) || 'FULL';
        var colors = { FULL: '#3fb950', STAT_ONLY: '#f0a030', RULE_ONLY: '#f0883e', EMERGENCY: '#f04444' };
        var labels = { FULL: '全功能运行', STAT_ONLY: '仅统计模式', RULE_ONLY: '仅规则模式', EMERGENCY: '紧急模式' };
        dot.style.background = colors[mode] || colors.FULL;
        dot.style.boxShadow = '0 0 6px ' + (colors[mode] || colors.FULL);
        text.textContent = labels[mode] || labels.FULL;
      }

      function showDetail(data) {
        var mode = (data && data.mode) || 'FULL';
        var comp = (data && data.components) || {};
        var colors = { FULL: '#3fb950', STAT_ONLY: '#f0a030', RULE_ONLY: '#f0883e', EMERGENCY: '#f04444' };
        var labels = { FULL: '全功能运行（统计+ML+SHAP）', STAT_ONLY: '仅统计模式（ML不可用，结果仅供参考）', RULE_ONLY: '仅规则模式（统计不可用，使用硬阈值）', EMERGENCY: '紧急模式（仅原始数据告警）' };
        var impacts = {
          FULL: '所有功能正常可用，工单含SHAP归因分析。',
          STAT_ONLY: 'ML预测报告不可用 · SHAP归因降级为公式分解 · 工单仍可正常生成（统计基线+规则）',
          RULE_ONLY: '统计推理不可用 · 使用电压/电流/温度硬阈值生成工单 · 健康分和Z-Score不可用',
          EMERGENCY: '仅使用原始传感器波动数据 · 按参数超限自动生成应急工单 · 不具备优先级排序'
        };
        var recovers = {
          FULL: '系统运行正常，无需操作。',
          STAT_ONLY: '检查ML模型文件 · 重新运行: python agent_orchestrator.py --data-dir 原始数据集 --model v1',
          RULE_ONLY: '检查统计基线数据 · 重新运行: python agent_orchestrator.py --data-dir 原始数据集 --skip-ml',
          EMERGENCY: '检查原始数据集完整性 · 重新运行 data-prep 步骤: python skills/predictive-maintenance-data-prep/scripts/run.py 原始数据集 outputs/data_prep'
        };

        document.getElementById('dg-title').innerHTML = '<span style="color:' + (colors[mode] || colors.FULL) + ';">⚠</span> 系统状态: ' + (labels[mode] || labels.FULL);
        var body = '<div class="dg-row"><span>ML 推理</span><span class="' + (comp.ml_available ? 'dg-ok' : 'dg-fail') + '">' + (comp.ml_available ? '✅ 正常' : '❌ 不可用') + '</span></div>';
        body += '<div class="dg-row"><span>统计推理</span><span class="' + (comp.stat_available ? 'dg-ok' : 'dg-fail') + '">' + (comp.stat_available ? '✅ 正常' : '❌ 不可用') + '</span></div>';
        body += '<div class="dg-row"><span>规则引擎</span><span class="' + (comp.rule_available ? 'dg-ok' : 'dg-fail') + '">' + (comp.rule_available ? '✅ 正常' : '❌ 不可用') + '</span></div>';
        body += '<p style="margin-top:12px;"><b>影响范围:</b><br>' + (impacts[mode] || impacts.FULL) + '</p>';
        body += '<p><b>恢复建议:</b><br>' + (recovers[mode] || recovers.FULL) + '</p>';
        document.getElementById('dg-body').innerHTML = body;
        document.getElementById('gn-degrade-popup').classList.add('show');
        document.getElementById('gn-degrade-overlay').classList.add('show');
      }

      // Fetch on load
      fetch('/data/degradation_status.json').then(function(r) { return r.ok ? r.json() : null; }).then(function(data) {
        if (data) { updateStatus(data); }
      }).catch(function() {});

      // Click to show detail
      var statusEl = document.getElementById('gn-status');
      if (statusEl) {
        statusEl.addEventListener('click', function() {
          fetch('/data/degradation_status.json').then(function(r) { return r.ok ? r.json() : null; }).then(function(data) {
            if (data) showDetail(data);
          }).catch(function() {});
        });
      }

      // Refresh every 60s
      setInterval(function() {
        fetch('/data/degradation_status.json').then(function(r) { return r.ok ? r.json() : null; }).then(function(data) {
          if (data) updateStatus(data);
        }).catch(function() {});
      }, 60000);
    })();

    // ── Theme Toggle Button ──
    (function initThemeToggle() {
      var btn = document.getElementById('gn-theme-btn');
      if (!btn) return;
      function updateIcon() {
        var isDark = !document.documentElement.hasAttribute('data-theme') ||
                     document.documentElement.getAttribute('data-theme') === 'dark';
        btn.innerHTML = isDark ? '☀ 浅色' : '☾ 深色';
      }
      updateIcon();
      btn.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme');
        var next = (current === 'light') ? 'dark' : 'light';
        try { localStorage.setItem('dashboard-theme', next); } catch(e) {}
        window.location.reload();
      });
    })();

    // ── Role Toggle Button ──
    (function initRoleToggle() {
      var ROLE_ORDER = ['operator', 'manager', 'developer'];
      var ROLE_META = {
        operator: { label: '运维工程师', color: '#00c9a0' },
        manager: { label: '生产管理负责人', color: '#f0a030' },
        developer: { label: '平台开发人员', color: '#a371f7' }
      };

      function updateButton(role) {
        var m = ROLE_META[role] || ROLE_META.developer;
        var dot = document.getElementById('gn-role-dot');
        var label = document.getElementById('gn-role-label');
        if (dot) dot.style.background = m.color;
        if (label) label.textContent = m.label;
      }

      var currentRole = sessionStorage.getItem('user_role') || 'developer';
      updateButton(currentRole);

      var toggle = document.getElementById('gn-role-toggle');
      if (toggle) {
        toggle.addEventListener('click', function () {
          var role = sessionStorage.getItem('user_role') || 'developer';
          var idx = ROLE_ORDER.indexOf(role);
          var nextIdx = (idx + 1) % ROLE_ORDER.length;
          var newRole = ROLE_ORDER[nextIdx];
          sessionStorage.setItem('user_role', newRole);
          sessionStorage.removeItem('role_context_sent');
          window.location.reload();
        });
      }
    })();

    // Page navigation — standard browser navigation, no animation delay

    console.log('[global-nav] initialized, active:', activeTab);
  }

  // Wait for DOM if still loading, otherwise inject immediately
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
