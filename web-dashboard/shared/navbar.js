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
  var activeTab = 'dashboard';
  if (path === '/chat' || path.startsWith('/chat')) activeTab = 'chat';
  else if (path === '/technical-overview' || path.startsWith('/technical-overview')) activeTab = 'tech';
  else if (path === '/reports' || path.startsWith('/reports')) activeTab = 'reports';

  // ── CSS ──
  var css = [
    '#global-nav {',
    '  position: sticky; top: 0; z-index: 1000;',
    '  background: rgba(14, 17, 23, 0.92);',
    '  backdrop-filter: blur(16px) saturate(180%);',
    '  -webkit-backdrop-filter: blur(16px) saturate(180%);',
    '  border-bottom: 1px solid rgba(28, 34, 48, 0.8);',
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
    '  color: #e6ebf2; letter-spacing: 0.5px;',
    '  font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;',
    '}',
    '#global-nav .gn-links {',
    '  display: flex; align-items: center; gap: 4px;',
    '  flex: 1;',
    '}',
    '#global-nav .gn-link {',
    '  padding: 8px 16px; border-radius: 6px;',
    '  font-size: 13px; font-weight: 500;',
    '  color: #8e9aab; text-decoration: none;',
    '  transition: all 0.2s ease;',
    '  position: relative;',
    '  white-space: nowrap;',
    '}',
    '#global-nav .gn-link:hover {',
    '  color: #e6ebf2;',
    '  background: rgba(255,255,255,0.03);',
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
    '  font-size: 11px; color: #5a6474;',
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
    '}'
  ].join('\n');

  // ── HTML ──
  var links = [
    { href: '/', label: '仪表盘', icon: '&#9632;', key: 'dashboard' },
    { href: '/chat', label: 'AI Copilot', icon: '&#9881;', key: 'chat' },
    { href: '/technical-overview', label: '技术架构', icon: '&#9776;', key: 'tech' },
    { href: '/reports', label: '报告', icon: '&#128196;', key: 'reports' }
  ];

  function buildLinksHtml() {
    return links.map(function (l) {
      var cls = l.key === activeTab ? 'gn-link active' : 'gn-link';
      return '<a class="' + cls + '" href="' + l.href + '">' +
        '<span class="gn-link-icon">' + l.icon + '</span>' + l.label + '</a>';
    }).join('');
  }

  function buildNavHtml() {
    return '<nav id="global-nav">' +
      '<div class="gn-inner">' +
      '<a class="gn-logo" href="/">' +
      '<span class="gn-logo-dot"></span>' +
      '<span class="gn-logo-text">Industrial AI Copilot</span>' +
      '</a>' +
      '<div class="gn-links">' + buildLinksHtml() + '</div>' +
      '<div class="gn-right">' +
      '<div class="gn-status">' +
      '<span class="gn-status-dot"></span>' +
      '<span>System Online</span>' +
      '</div>' +
      '<span class="gn-badge">v2.0</span>' +
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

    // Page transition
    var gnLinks = document.querySelectorAll('#global-nav .gn-link');
    for (var j = 0; j < gnLinks.length; j++) {
      gnLinks[j].addEventListener('click', function (e) {
        var href = this.getAttribute('href');
        if (href === path || href === path + '/') return;
        document.body.classList.add('gn-transitioning');
        setTimeout(function () {
          window.location = href;
        }, 120);
        e.preventDefault();
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
