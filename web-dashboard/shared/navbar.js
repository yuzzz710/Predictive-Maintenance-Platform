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
    '/* ════════════════════════════════════════════════════════════',
    '   iOS 26 Design Tokens — Single Source of Truth',
    '   ════════════════════════════════════════════════════════════ */',

    /* ── Deep Mode (default :root) ── */
    ':root {',
    '  --bg-root: #000000;',
    '  --bg-surface: #1c1c1e;',
    '  --bg-card: rgba(44,44,46,0.35);',
    '  --bg-card-alt: rgba(58,58,60,0.25);',
    '  --bg-input: rgba(44,44,46,0.30);',
    '  --text-primary: #f5f5f7;',
    '  --text-secondary: #98989d;',
    '  --text-muted: #636366;',
    '  --border: rgba(255,255,255,0.08);',
    '  --border-light: rgba(255,255,255,0.05);',
    '  --border-accent: rgba(255,255,255,0.12);',
    '  --accent-cyan: #66d9c8;',
    '  --accent-green: #30d158;',
    '  --accent-blue: #6db5f9;',
    '  --accent-amber: #ffb340;',
    '  --accent-red: #ff453a;',
    '  --accent-purple: #bf5af2;',
    '  --accent-pink: #ff6482;',
    '  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);',
    '  --shadow-md: 0 4px 16px rgba(0,0,0,0.4);',
    '  --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);',
    '  --shadow-xl: 0 12px 48px rgba(0,0,0,0.6);',
    '  --radius-sm: 10px;',
    '  --radius: 14px;',
    '  --radius-md: 18px;',
    '  --radius-lg: 22px;',
    '  --radius-xl: 28px;',
    '  --glass-bg-card: rgba(44,44,46,0.35);',
    '  --glass-bg-header: rgba(28,28,30,0.4);',
    '  --glass-bg-modal: rgba(44,44,46,0.55);',
    '  --glass-bg-sidebar: rgba(28,28,30,0.5);',
    '  --glass-blur: blur(45px) saturate(220%);',
    '  --glass-blur-light: blur(30px) saturate(200%);',
    '  --glass-blur-strong: blur(55px) saturate(240%);',
    '  --glass-border: rgba(255,255,255,0.10);',
    '  --glass-highlight: inset 0 0.5px 0 rgba(255,255,255,0.08);',
    '  --glass-highlight-strong: inset 0 0.5px 0 rgba(255,255,255,0.14);',
    '  --font-sans: -apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei","Hiragino Sans GB","Segoe UI",system-ui,sans-serif;',
    '  --font-mono: "SF Mono","Cascadia Code","Fira Code","JetBrains Mono","Consolas",monospace;',
    '  --space-xs: 6px;',
    '  --space-sm: 10px;',
    '  --space-md: 16px;',
    '  --space-lg: 24px;',
    '  --space-xl: 32px;',
    '  --space-2xl: 48px;',
    '  --transition: 0.25s cubic-bezier(0.25,0.1,0.25,1);',
    '  --transition-spring: 0.35s cubic-bezier(0.34,1.56,0.64,1);',
    '}',

    /* ── Light Mode ── */
    '[data-theme="light"] {',
    '  --bg-root: #f2f2f7;',
    '  --bg-surface: #fafafa;',
    '  --bg-card: rgba(255,255,255,0.38);',
    '  --bg-card-alt: rgba(245,245,247,0.25);',
    '  --bg-input: rgba(255,255,255,0.32);',
    '  --text-primary: #1d1d1f;',
    '  --text-secondary: #6e6e73;',
    '  --text-muted: #aeaeb2;',
    '  --border: rgba(0,0,0,0.06);',
    '  --border-light: rgba(0,0,0,0.04);',
    '  --border-accent: rgba(0,0,0,0.10);',
    '  --accent-cyan: #5ac8b8;',
    '  --accent-green: #4cd964;',
    '  --accent-blue: #64b5f6;',
    '  --accent-amber: #f0a840;',
    '  --accent-red: #e06060;',
    '  --accent-purple: #b388eb;',
    '  --accent-pink: #e080a0;',
    '  --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);',
    '  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);',
    '  --shadow-lg: 0 8px 30px rgba(0,0,0,0.10);',
    '  --shadow-xl: 0 12px 40px rgba(0,0,0,0.14);',
    '  --glass-bg-card: rgba(255,255,255,0.38);',
    '  --glass-bg-header: rgba(250,250,250,0.45);',
    '  --glass-bg-modal: rgba(255,255,255,0.55);',
    '  --glass-bg-sidebar: rgba(250,250,250,0.5);',
    '  --glass-blur: blur(40px) saturate(220%);',
    '  --glass-blur-light: blur(30px) saturate(200%);',
    '  --glass-blur-strong: blur(50px) saturate(240%);',
    '  --glass-border: rgba(255,255,255,0.5);',
    '  --glass-highlight: inset 0 0.5px 0 rgba(255,255,255,0.6);',
    '  --glass-highlight-strong: inset 0 0.5px 0 rgba(255,255,255,0.85);',
    '}',

    /* ── Ambient Light Orbs (body::before) ── */
    'body::before {',
    '  content:""; position:fixed; inset:0; pointer-events:none; z-index:0;',
    '  background:',
    '    radial-gradient(ellipse 80% 60% at 30% 20%, rgba(102,217,200,0.06) 0%, transparent 60%),',
    '    radial-gradient(ellipse 60% 50% at 70% 60%, rgba(109,181,249,0.05) 0%, transparent 60%),',
    '    radial-gradient(ellipse 50% 40% at 50% 80%, rgba(191,90,242,0.04) 0%, transparent 60%);',
    '}',
    '[data-theme="light"] body::before {',
    '  background:',
    '    radial-gradient(ellipse 80% 60% at 30% 20%, rgba(90,200,184,0.08) 0%, transparent 60%),',
    '    radial-gradient(ellipse 60% 50% at 70% 60%, rgba(100,181,246,0.06) 0%, transparent 60%),',
    '    radial-gradient(ellipse 50% 40% at 50% 80%, rgba(179,136,235,0.05) 0%, transparent 60%);',
    '}',

    /* ── Base Reset ── */
    '*, *::before, *::after { box-sizing:border-box; }',
    'body {',
    '  margin:0; padding:0 0 0 200px;',
    '  background:var(--bg-root); color:var(--text-primary);',
    '  font-family:var(--font-sans);',
    '  min-height:100vh; overflow-x:hidden;',
    '  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;',
    '  transition:padding-left var(--transition);',
    '}',

    /* ── Universal Glass Card ── */
    '.glass-card {',
    '  background:var(--glass-bg-card);',
    '  backdrop-filter:var(--glass-blur); -webkit-backdrop-filter:var(--glass-blur);',
    '  border:0.5px solid var(--glass-border);',
    '  border-radius:var(--radius-lg);',
    '  box-shadow:var(--shadow-sm),var(--glass-highlight);',
    '  transition:box-shadow var(--transition),transform var(--transition);',
    '}',
    '.glass-card:hover {',
    '  box-shadow:var(--shadow-md),var(--glass-highlight);',
    '  transform:translateY(-1px);',
    '}',
    '.glass-card .glass-card {',
    '  background:rgba(44,44,46,0.20);',
    '  backdrop-filter:var(--glass-blur-light); -webkit-backdrop-filter:var(--glass-blur-light);',
    '  border-radius:var(--radius-md);',
    '}',
    '[data-theme="light"] .glass-card .glass-card {',
    '  background:rgba(255,255,255,0.25);',
    '}',

    /* ── Universal Button System ── */
    '.btn {',
    '  padding:10px 20px; border-radius:22px; font-weight:500; font-size:13px;',
    '  cursor:pointer; font-family:var(--font-sans);',
    '  transition:all var(--transition); border:none;',
    '  display:inline-flex; align-items:center; gap:6px;',
    '}',
    '.btn:active { transform:scale(0.98); }',
    '.btn-primary {',
    '  background:var(--accent-cyan); color:#000;',
    '  box-shadow:0 4px 14px rgba(102,217,200,0.25);',
    '}',
    '.btn-primary:hover { opacity:0.88; transform:translateY(-1px);',
    '  box-shadow:0 6px 20px rgba(102,217,200,0.35); }',
    '.btn-secondary {',
    '  background:rgba(102,217,200,0.08); color:var(--accent-cyan);',
    '  border:0.5px solid rgba(102,217,200,0.25);',
    '}',
    '.btn-secondary:hover { background:rgba(102,217,200,0.14); }',
    '.btn-ghost {',
    '  background:transparent; color:var(--text-secondary);',
    '  border:0.5px solid var(--border);',
    '}',
    '.btn-ghost:hover { border-color:var(--border-accent); color:var(--text-primary); }',
    '.btn-danger {',
    '  background:var(--accent-red); color:#fff;',
    '  box-shadow:0 4px 14px rgba(255,69,58,0.25);',
    '}',
    '.btn-danger:hover { opacity:0.88; }',

    /* ── Universal Input ── */
    'input[type="text"], input[type="search"], textarea, select {',
    '  background:var(--bg-input);',
    '  backdrop-filter:var(--glass-blur-light); -webkit-backdrop-filter:var(--glass-blur-light);',
    '  border:0.5px solid var(--border-accent);',
    '  border-radius:var(--radius); padding:10px 14px;',
    '  font-size:13px; color:var(--text-primary); font-family:var(--font-sans);',
    '  transition:border-color var(--transition),box-shadow var(--transition);',
    '  outline:none;',
    '}',
    'input[type="text"]:focus, input[type="search"]:focus, textarea:focus, select:focus {',
    '  border-color:var(--accent-cyan);',
    '  box-shadow:0 0 0 3px rgba(102,217,200,0.12);',
    '}',

    /* ── Universal Tag System ── */
    '.tag {',
    '  display:inline-flex; align-items:center; gap:4px;',
    '  padding:4px 10px; border-radius:10px;',
    '  font-size:11px; font-weight:500; white-space:nowrap;',
    '}',
    '.tag-green { background:rgba(48,209,88,0.08); color:var(--accent-green); }',
    '.tag-amber { background:rgba(255,179,64,0.08); color:var(--accent-amber); }',
    '.tag-red { background:rgba(255,69,58,0.08); color:var(--accent-red); }',
    '.tag-purple { background:rgba(191,90,242,0.08); color:var(--accent-purple); }',
    '.tag-cyan { background:rgba(102,217,200,0.08); color:var(--accent-cyan); }',
    '.tag-blue { background:rgba(109,181,249,0.08); color:var(--accent-blue); }',

    /* ── Universal Table ── */
    'table {',
    '  width:100%; border-collapse:separate; border-spacing:0;',
    '  font-size:12px;',
    '}',
    'th {',
    '  text-align:left; padding:10px 14px; font-weight:600;',
    '  color:var(--text-secondary); border-bottom:0.5px solid var(--border);',
    '  font-size:10px; text-transform:uppercase; letter-spacing:0.03em;',
    '}',
    'td {',
    '  padding:10px 14px; border-bottom:0.5px solid var(--border-light);',
    '  color:var(--text-primary);',
    '}',
    'tr:hover td { background:var(--bg-card-alt); }',

    /* ── Universal Modal / Overlay System ── */
    '.modal-overlay {',
    '  position:fixed; inset:0; background:rgba(0,0,0,0.45);',
    '  backdrop-filter:blur(4px); -webkit-backdrop-filter:blur(4px);',
    '  z-index:2000; opacity:0; pointer-events:none;',
    '  transition:opacity 0.25s ease;',
    '}',
    '[data-theme="light"] .modal-overlay { background:rgba(0,0,0,0.18); }',
    '.modal-overlay.open { opacity:1; pointer-events:auto; }',
    '.modal {',
    '  position:fixed; top:50%; left:50%;',
    '  transform:translate(-50%,-50%) scale(0.95);',
    '  background:var(--glass-bg-modal);',
    '  backdrop-filter:var(--glass-blur-strong); -webkit-backdrop-filter:var(--glass-blur-strong);',
    '  border:0.5px solid var(--glass-border);',
    '  border-radius:var(--radius-xl);',
    '  box-shadow:var(--shadow-xl),var(--glass-highlight-strong);',
    '  z-index:2001; opacity:0; pointer-events:none;',
    '  transition:opacity 0.25s ease,transform 0.3s var(--transition-spring);',
    '}',
    '.modal.open { opacity:1; pointer-events:auto; transform:translate(-50%,-50%) scale(1); }',

    /* ── Sidebar Styles ── */
    '#global-nav {',
    '  position:fixed; left:0; top:0; bottom:0; width:200px; z-index:1000;',
    '  background:var(--glass-bg-sidebar);',
    '  backdrop-filter:var(--glass-blur-strong); -webkit-backdrop-filter:var(--glass-blur-strong);',
    '  border-right:0.5px solid var(--border);',
    '  display:flex; flex-direction:column; overflow:hidden;',
    '  font-family:var(--font-sans);',
    '}',
    '#global-nav .gn-inner {',
    '  display:flex; flex-direction:column; height:100%; padding:16px 0;',
    '}',
    '#global-nav .gn-logo {',
    '  display:flex; align-items:center; gap:10px; padding:12px 18px;',
    '  text-decoration:none; flex-shrink:0;',
    '  border-bottom:0.5px solid var(--border); margin-bottom:4px;',
    '}',
    '#global-nav .gn-logo-dot {',
    '  width:9px; height:9px; border-radius:50%; background:var(--accent-cyan);',
    '  box-shadow:0 0 10px rgba(102,217,200,0.4);',
    '  animation:gnPulse 2.5s ease-in-out infinite; flex-shrink:0;',
    '}',
    '@keyframes gnPulse {',
    '  0%,100% { box-shadow:0 0 8px rgba(102,217,200,0.4),0 0 20px rgba(102,217,200,0.15); }',
    '  50% { box-shadow:0 0 14px rgba(102,217,200,0.7),0 0 30px rgba(102,217,200,0.3); }',
    '}',
    '#global-nav .gn-logo-text {',
    '  font-size:16px; font-weight:700; color:var(--text-primary); letter-spacing:-0.3px;',
    '  font-family:var(--font-mono);',
    '}',
    '#global-nav .gn-links {',
    '  display:flex; flex-direction:column; gap:1px; padding:4px 10px;',
    '  flex:1; overflow-y:auto; overflow-x:hidden;',
    '}',
    '#global-nav .gn-link {',
    '  display:flex; align-items:center; gap:10px;',
    '  padding:10px 14px; border-radius:var(--radius-sm);',
    '  font-size:13px; font-weight:500;',
    '  color:var(--text-secondary); text-decoration:none;',
    '  transition:all var(--transition); position:relative; white-space:nowrap;',
    '}',
    '#global-nav .gn-link:hover { color:var(--text-primary); background:var(--bg-card-alt); }',
    '#global-nav .gn-link.active {',
    '  color:var(--accent-cyan); background:rgba(102,217,200,0.06);',
    '}',
    '#global-nav .gn-link.active::before {',
    '  content:""; position:absolute; left:0; top:8px; bottom:8px;',
    '  width:3px; border-radius:0 3px 3px 0; background:var(--accent-cyan);',
    '}',
    '#global-nav .gn-link-icon { font-size:16px; width:20px; text-align:center; flex-shrink:0; }',
    '#global-nav .gn-right {',
    '  display:flex; flex-direction:column; gap:6px; padding:10px 14px;',
    '  flex-shrink:0; border-top:0.5px solid var(--border);',
    '}',
    '#global-nav .gn-status {',
    '  display:flex; align-items:center; gap:6px; font-size:10px;',
    '  color:var(--text-muted); padding:4px 0;',
    '}',
    '#global-nav .gn-status-dot {',
    '  width:6px; height:6px; border-radius:50%; background:var(--accent-green);',
    '  box-shadow:0 0 6px rgba(48,209,88,0.3); flex-shrink:0;',
    '}',
    '#global-nav .gn-role-toggle, #global-nav .gn-theme-btn {',
    '  display:flex; align-items:center; gap:6px; padding:6px 10px;',
    '  border-radius:var(--radius-sm); font-size:11px;',
    '  cursor:pointer; border:0.5px solid var(--border);',
    '  background:var(--bg-card-alt); color:var(--text-secondary);',
    '  transition:all var(--transition); user-select:none; font-family:var(--font-sans);',
    '}',
    '#global-nav .gn-role-toggle:hover, #global-nav .gn-theme-btn:hover {',
    '  color:var(--text-primary); background:var(--bg-card);',
    '}',
    '#global-nav .gn-theme-btn { width:100%; }',
    '#global-nav .gn-role-toggle .gn-role-dot {',
    '  width:6px; height:6px; border-radius:50%; flex-shrink:0;',
    '}',
    '#global-nav .gn-mode-badge {',
    '  margin: 8px 14px 0; padding: 8px 0; text-align: center;',
    '  font-size: 13px; font-weight: 700; letter-spacing: 0.5px;',
    '  color: var(--accent-green);',
    '  border-top: 0.5px solid var(--border);',
    '}',
    '#global-nav .gn-badge {',
    '  font-size:11px; padding:5px 10px; border-radius:8px; text-align:center;',
    '  font-family:var(--font-mono); font-weight:700;',
    '  background:rgba(102,217,200,0.18); color:var(--accent-cyan);',
    '  border:0.5px solid rgba(102,217,200,0.35);',
    '}',
    'body.gn-transitioning { opacity:1; transition:none; }',

    /* ── Role-Based Visibility ── */
    'html[data-role="operator"] .role-manager:not(.role-operator) { display:none !important; }',
    'html[data-role="operator"] .role-developer:not(.role-operator) { display:none !important; }',
    'html[data-role="manager"] .role-developer:not(.role-manager) { display:none !important; }',

    /* ── Degradation Popup (iOS 26 style) ── */
    '.gn-degrade-popup {',
    '  position:fixed; top:50%; left:50%; transform:translate(-50%,-50%) scale(0.95);',
    '  width:440px; max-width:94vw; max-height:84vh; overflow-y:auto;',
    '  background:var(--glass-bg-modal);',
    '  backdrop-filter:var(--glass-blur-strong); -webkit-backdrop-filter:var(--glass-blur-strong);',
    '  border:0.5px solid var(--glass-border); border-radius:var(--radius-xl);',
    '  box-shadow:var(--shadow-xl),var(--glass-highlight-strong);',
    '  z-index:9999; padding:28px 32px 24px; font-size:13px;',
    '  color:var(--text-secondary); line-height:1.6;',
    '  opacity:0; pointer-events:none;',
    '  transition:opacity 0.2s ease-out,transform 0.2s ease-out;',
    '}',
    '.gn-degrade-popup.show { opacity:1; pointer-events:auto; transform:translate(-50%,-50%) scale(1); }',
    '.gn-degrade-overlay {',
    '  position:fixed; inset:0; background:rgba(0,0,0,0.45);',
    '  backdrop-filter:blur(4px); z-index:9998;',
    '  opacity:0; pointer-events:none; transition:opacity 0.2s ease-out;',
    '}',
    '.gn-degrade-overlay.show { opacity:1; pointer-events:auto; }',
    '.gn-degrade-popup .dg-header {',
    '  display:flex; align-items:center; gap:10px; margin-bottom:20px;',
    '  padding-bottom:16px; border-bottom:0.5px solid var(--border);',
    '}',
    '.gn-degrade-popup .dg-header-icon {',
    '  width:36px; height:36px; border-radius:12px; flex-shrink:0;',
    '  display:flex; align-items:center; justify-content:center;',
    '}',
    '.gn-degrade-popup .dg-title { font-size:15px; font-weight:600; color:var(--text-primary); }',
    '.gn-degrade-popup .dg-subtitle { font-size:11px; color:var(--text-muted); }',
    '.gn-degrade-popup .dg-section { margin-bottom:16px; }',
    '.gn-degrade-popup .dg-section-label {',
    '  font-size:10px; font-weight:600; text-transform:uppercase;',
    '  letter-spacing:0.05em; color:var(--text-muted); margin-bottom:8px;',
    '}',
    '.gn-degrade-popup .dg-module {',
    '  display:flex; align-items:center; justify-content:space-between;',
    '  padding:10px 14px; margin-bottom:4px;',
    '  background:var(--bg-card-alt); border-radius:var(--radius-sm);',
    '}',
    '.gn-degrade-popup .dg-module-name { font-size:13px; font-weight:500; color:var(--text-primary); }',
    '.gn-degrade-popup .dg-module-status {',
    '  display:inline-flex; align-items:center; gap:6px;',
    '  font-size:12px; font-weight:500; padding:3px 10px; border-radius:8px;',
    '}',
    '.gn-degrade-popup .dg-module-status.ok { background:rgba(48,209,88,0.08); color:var(--accent-green); }',
    '.gn-degrade-popup .dg-module-status.fail { background:rgba(255,69,58,0.08); color:var(--accent-red); }',
    '.gn-degrade-popup .dg-desc {',
    '  font-size:12px; color:var(--text-secondary);',
    '  padding:12px 14px; background:var(--bg-card-alt);',
    '  border-radius:var(--radius-sm); border-left:3px solid var(--border-accent); line-height:1.7;',
    '}',
    '.gn-degrade-popup .dg-close {',
    '  position:absolute; top:16px; right:16px; width:28px; height:28px;',
    '  border-radius:10px; border:none; background:transparent;',
    '  color:var(--text-muted); cursor:pointer;',
    '  display:flex; align-items:center; justify-content:center;',
    '  transition:background var(--transition),color var(--transition);',
    '}',
    '.gn-degrade-popup .dg-close:hover { background:var(--bg-card-alt); color:var(--text-primary); }',

    /* ── Responsive ── */
    '@media (max-width:768px) {',
    '  body { padding-left:0; }',
    '  #global-nav { position:sticky; top:0; bottom:auto; width:100%; height:auto; flex-direction:row; }',
    '  #global-nav .gn-inner { flex-direction:row; padding:0 12px; height:48px; align-items:center; }',
    '  #global-nav .gn-logo { border-bottom:none; margin-bottom:0; padding:0; }',
    '  #global-nav .gn-links, #global-nav .gn-right { display:none; }',
    '}',
    '@media (max-width:520px) {',
    '  #global-nav .gn-logo-text { display:none; }',
    '}',
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
      '<span class="gn-logo-text">鹰眼-工业智能运维平台</span>' +
      '</a>' +
      '<div class="gn-links">' + buildLinksHtml() + '</div>' +
      '<div class="gn-mode-badge" id="gn-mode-badge">全功能</div>' +
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
      '<span class="gn-badge">决赛一等奖版</span>' +
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
        var badge = document.getElementById('gn-mode-badge');
        var mode = (data && data.mode) || 'FULL';
        var colors = { FULL: '#30d158', STAT_ONLY: '#ffb340', RULE_ONLY: '#ff8214', EMERGENCY: '#ff453a' };
        var labels = { FULL: '全功能运行', STAT_ONLY: '仅统计模式', RULE_ONLY: '仅规则模式', EMERGENCY: '紧急模式' };
        if (dot) { dot.style.background = colors[mode] || colors.FULL; dot.style.boxShadow = '0 0 6px ' + (colors[mode] || colors.FULL); }
        if (text) text.textContent = labels[mode] || labels.FULL;
        if (badge) { badge.textContent = labels[mode] || labels.FULL; badge.style.color = colors[mode] || colors.FULL; }
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
