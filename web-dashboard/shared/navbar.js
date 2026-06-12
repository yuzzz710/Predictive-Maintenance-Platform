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
    '  --gn-bg: rgba(14, 17, 23, 0.92);',
    '  --gn-border: rgba(28, 34, 48, 0.8);',
    '  --gn-text: #e6ebf2;',
    '  --gn-text-secondary: #8e9aab;',
    '  --gn-text-muted: #5a6474;',
    '  --gn-hover-bg: rgba(255,255,255,0.03);',
    '}',
    '[data-theme="light"] {',
    '  --gn-bg: rgba(255, 255, 255, 0.94);',
    '  --gn-border: rgba(200, 210, 225, 0.8);',
    '  --gn-text: #1a1d26;',
    '  --gn-text-secondary: #4a5568;',
    '  --gn-text-muted: #7a8498;',
    '  --gn-hover-bg: rgba(0,0,0,0.03);',
    '}',
    '#global-nav {',
    '  position: sticky; top: 0; z-index: 1000;',
    '  background: var(--gn-bg);',
    '  backdrop-filter: blur(16px) saturate(180%);',
    '  -webkit-backdrop-filter: blur(16px) saturate(180%);',
    '  border-bottom: 1px solid var(--gn-border);',
    '  font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", "Segoe UI", system-ui, sans-serif;',
    '  line-height: 1;',
    '}',
    '#global-nav .gn-inner {',
    '  max-width: 1400px; margin: 0 auto;',
    '  display: flex; align-items: center;',
    '  height: 48px; padding: 0 24px;',
    '}',
    '#global-nav .gn-logo {',
    '  display: flex; align-items: center; gap: 10px;',
    '  text-decoration: none; flex-shrink: 0;',
    '  margin-right: 32px;',
    '}',
    '#global-nav .gn-logo-dot {',
    '  width: 9px; height: 9px; border-radius: 50%;',
    '  background: #00c9a0;',
    '  box-shadow: 0 0 8px rgba(0,201,160,0.4), 0 0 20px rgba(0,201,160,0.15);',
    '  animation: gnPulse 2.5s ease-in-out infinite;',
    '}',
    '@keyframes gnPulse {',
    '  0%, 100% { box-shadow: 0 0 8px rgba(0,201,160,0.4), 0 0 20px rgba(0,201,160,0.15); }',
    '  50% { box-shadow: 0 0 14px rgba(0,201,160,0.7), 0 0 30px rgba(0,201,160,0.3); }',
    '}',
    '#global-nav .gn-logo-text {',
    '  font-size: 13px; font-weight: 700;',
    '  color: var(--gn-text); letter-spacing: 0.5px;',
    '  font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;',
    '}',
    '#global-nav .gn-links {',
    '  display: flex; align-items: center; gap: 4px;',
    '  flex: 1;',
    '}',
    '#global-nav .gn-link {',
    '  padding: 8px 16px; border-radius: 6px;',
    '  font-size: 13px; font-weight: 500;',
    '  color: var(--gn-text-secondary); text-decoration: none;',
    '  transition: all 0.2s ease;',
    '  position: relative;',
    '  white-space: nowrap;',
    '}',
    '#global-nav .gn-link:hover {',
    '  color: var(--gn-text);',
    '  background: var(--gn-hover-bg);',
    '}',
    '#global-nav .gn-link.active {',
    '  color: #00c9a0;',
    '  background: rgba(0,201,160,0.06);',
    '}',
    '#global-nav .gn-link.active::after {',
    '  content: ""; position: absolute; bottom: -1px; left: 8px; right: 8px;',
    '  height: 2px; border-radius: 1px;',
    '  background: #00c9a0;',
    '  box-shadow: 0 0 8px rgba(0,201,160,0.3);',
    '}',
    '#global-nav .gn-link-icon { margin-right: 4px; font-size: 14px; }',
    '#global-nav .gn-right {',
    '  display: flex; align-items: center; gap: 14px;',
    '  flex-shrink: 0; margin-left: auto;',
    '}',
    '#global-nav .gn-status {',
    '  display: flex; align-items: center; gap: 6px;',
    '  font-size: 11px; color: var(--gn-text-muted);',
    '}',
    '#global-nav .gn-status-dot {',
    '  width: 6px; height: 6px; border-radius: 50%;',
    '  background: #3fb950;',
    '  box-shadow: 0 0 6px rgba(63,185,80,0.3);',
    '}',
    '#global-nav .gn-badge {',
    '  font-size: 10px; padding: 3px 8px; border-radius: 10px;',
    '  font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;',
    '  background: rgba(0,201,160,0.08); color: #00c9a0;',
    '  border: 1px solid rgba(0,201,160,0.15);',
    '}',
    'body.gn-transitioning { opacity: 0.6; transition: opacity 0.15s ease; }',
    '#global-nav .gn-role-toggle {',
    '  display: flex; align-items: center; gap: 5px;',
    '  padding: 4px 10px; border-radius: 14px;',
    '  font-size: 10px; color: var(--gn-text-secondary);',
    '  cursor: pointer; border: 1px solid var(--gn-border);',
    '  background: var(--gn-hover-bg);',
    '  font-family: "PingFang SC","Microsoft YaHei","Hiragino Sans GB","Segoe UI",system-ui,sans-serif;',
    '  transition: all 0.2s ease; white-space: nowrap; user-select: none;',
    '}',
    '#global-nav .gn-role-toggle:hover {',
    '  color: var(--gn-text);',
    '  border-color: rgba(255,255,255,0.15);',
    '  background: rgba(255,255,255,0.05);',
    '}',
    '#global-nav .gn-role-toggle .gn-role-dot {',
    '  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;',
    '  transition: background 0.3s ease;',
    '}',
    '#global-nav .gn-theme-btn {',
    '  display: flex; align-items: center; gap: 4px;',
    '  padding: 4px 10px; border-radius: 14px;',
    '  font-size: 10px; cursor: pointer; border: 1px solid var(--gn-border);',
    '  background: var(--gn-hover-bg); color: var(--gn-text-secondary);',
    '  transition: all 0.2s ease; flex-shrink: 0;',
    '  font-family: \"PingFang SC\",\"Microsoft YaHei\",\"Hiragino Sans GB\",\"Segoe UI\",system-ui,sans-serif;',
    '  white-space: nowrap; user-select: none;',
    '}',
    '#global-nav .gn-theme-btn:hover {',
    '  color: var(--gn-text);',
    '  border-color: rgba(255,255,255,0.15);',
    '  background: rgba(255,255,255,0.05);',
    '}',
    '#global-nav .gn-degrade-popup {',
    '  position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);',
    '  width: 420px; max-width: 92vw; max-height: 80vh; overflow-y: auto;',
    '  background: rgba(20,24,32,0.98); backdrop-filter: blur(16px);',
    '  border: 1px solid var(--gn-border); border-radius: 10px;',
    '  box-shadow: 0 16px 48px rgba(0,0,0,0.5); z-index: 9999;',
    '  padding: 24px; font-size: 12px; color: var(--gn-text-secondary);',
    '  display: none; line-height: 1.8;',
    '}',
    '#global-nav .gn-degrade-popup.show { display: block; }',
    '#global-nav .gn-degrade-overlay {',
    '  position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 9998;',
    '  display: none;',
    '}',
    '#global-nav .gn-degrade-overlay.show { display: block; }',
    '#global-nav .gn-degrade-popup h3 { font-size: 16px; margin-bottom: 12px; color: var(--gn-text); }',
    '#global-nav .gn-degrade-popup .dg-row { display: flex; justify-content: space-between; padding: 5px 0; }',
    '#global-nav .gn-degrade-popup .dg-ok { color: #3fb950; }',
    '#global-nav .gn-degrade-popup .dg-fail { color: #f04444; }',
    '#global-nav .gn-degrade-popup .dg-close {',
    '  position: absolute; top: 12px; right: 14px;',
    '  width: 24px; height: 24px; border-radius: 50%;',
    '  border: 1px solid var(--gn-border); background: transparent;',
    '  color: var(--gn-text-secondary); cursor: pointer; font-size: 14px;',
    '  display: flex; align-items: center; justify-content: center;',
    '}',
    '@media (max-width: 768px) {',
    '  #global-nav .gn-links { gap: 0; }',
    '  #global-nav .gn-link { padding: 8px 10px; font-size: 11px; }',
    '  #global-nav .gn-link-icon { display: none; }',
    '  #global-nav .gn-right { display: none; }',
    '  #global-nav .gn-logo-text { font-size: 11px; }',
    '  #global-nav .gn-inner { padding: 0 12px; }',
    '  #global-nav .gn-logo { margin-right: 8px; }',
    '}',
    '@media (max-width: 520px) {',
    '  #global-nav .gn-link { padding: 8px 7px; font-size: 10px; }',
    '  #global-nav .gn-logo-text { display: none; }',
    '}',
    '/* Role-based visibility for nav links */',
    'html[data-role="operator"] .role-manager:not(.role-operator) { display: none !important; }',
    'html[data-role="operator"] .role-developer:not(.role-operator) { display: none !important; }',
    'html[data-role="manager"] .role-developer:not(.role-manager) { display: none !important; }',
  ].join('\n');

  // ── HTML ──
  var links = [
    { href: '/', label: '首页', icon: '&#9679;', key: 'home' },
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
      offsetStyle.textContent = '.header { top: 48px !important; } .nav-bar { top: 100px !important; }';
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

    // Page transition
    var gnLinks = document.querySelectorAll('#global-nav .gn-link');
    for (var j = 0; j < gnLinks.length; j++) {
      gnLinks[j].addEventListener('click', function (e) {
        var href = this.getAttribute('href');
        if (!href) return;
        // Same page: let default behavior handle it
        if (href === path || href === path + '/' || path === href || path === href + '/') return;
        e.preventDefault();
        document.body.classList.add('gn-transitioning');
        setTimeout(function () {
          window.location.href = href;
        }, 120);
      });
    }

    console.log('[global-nav] initialized, active:', activeTab);
  }

  // Wait for DOM if still loading, otherwise inject immediately
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
