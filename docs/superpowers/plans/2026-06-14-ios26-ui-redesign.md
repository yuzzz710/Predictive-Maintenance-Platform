# iOS 26 Glassmorphism UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the entire predictive maintenance web dashboard to iOS 26 glassmorphism style — high transparency (28-40%), strong blur (30-55px), large round corners (18-28px), ambient light orbs, and inset highlights on every content panel.

**Architecture:** Put all design tokens into navbar.js (single source of truth, injected via `<style>` into every page). Update sidebar.css for iOS 26 sidebar. Each HTML page: remove old `:root`/`[data-theme="light"]` blocks, convert all content blocks to `.glass-card`, update component-specific styles. Zero business logic changes.

**Tech Stack:** Vanilla CSS (CSS custom properties), Vanilla JS, ECharts 5.5 — no new dependencies.

**Files affected:** 14 files, ~20K lines total.

---

## Phase 0: Shared Design Infrastructure (navbar.js + sidebar.css)

These two files establish the design baseline for ALL pages.

### Task 0: Rewrite navbar.js CSS block with full iOS 26 design tokens + sidebar + glass card system + ambient light orbs

**Files:**
- Modify: `web-dashboard/shared/navbar.js` (lines 28-213, the CSS block)

Complete new CSS block to inject into every page:

```javascript
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
  '.input, input[type="text"]:not(.gn-*), input[type="search"], textarea, select {',
  '  background:var(--bg-input);',
  '  backdrop-filter:var(--glass-blur-light); -webkit-backdrop-filter:var(--glass-blur-light);',
  '  border:0.5px solid var(--border-accent);',
  '  border-radius:var(--radius); padding:10px 14px;',
  '  font-size:13px; color:var(--text-primary); font-family:var(--font-sans);',
  '  transition:border-color var(--transition),box-shadow var(--transition);',
  '  outline:none;',
  '}',
  '.input:focus, input[type="text"]:focus, textarea:focus, select:focus {',
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
  '  font-size:13px; font-weight:700; color:var(--text-primary); letter-spacing:-0.3px;',
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
  '#global-nav .gn-badge {',
  '  font-size:9px; padding:3px 6px; border-radius:6px; text-align:center;',
  '  font-family:var(--font-mono);',
  '  background:rgba(102,217,200,0.08); color:var(--accent-cyan);',
  '  border:0.5px solid rgba(102,217,200,0.15);',
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
];
```

- [ ] **Step 1: Replace the CSS block in navbar.js**

Read the current navbar.js, locate the `var css = [` block (starts at ~line 28, ends at `].join("\n");` at ~line 213). Replace the entire CSS array content with the above.

- [ ] **Step 2: Verify navbar.js syntax**

Run: `node -c web-dashboard/shared/navbar.js`
Expected: No syntax errors.

- [ ] **Step 3: Commit**

```bash
git add web-dashboard/shared/navbar.js
git commit -m "feat: iOS26设计令牌注入navbar.js — 全局Design Tokens + 玻璃卡片系统 + 侧边栏 + 环境光晕"
```

---

### Task 1: Simplify sidebar.css (now redundant — navbar.js provides sidebar styles)

**Files:**
- Modify: `web-dashboard/shared/sidebar.css`

Since navbar.js now injects all sidebar styles, sidebar.css should only keep page-specific overrides that don't fit in the shared CSS. For now, keep it minimal (or empty). Pages that load it will still work.

- [ ] **Step 1: Replace sidebar.css with minimal content**

```css
/* Sidebar styles now injected by navbar.js — this file reserved for page-specific overrides */
```

- [ ] **Step 2: Commit**

```bash
git add web-dashboard/shared/sidebar.css
git commit -m "refactor: sidebar.css精简 — 样式已由navbar.js注入"
```

---

## Phase 1: P0 Core Pages

### Task 2: Rewrite role-gate.html — iOS 26 glass role cards

**Files:**
- Modify: `web-dashboard/role-gate.html`

**Key changes:**
1. Remove old `:root` CSS block (navbar.js now provides tokens)
2. Remove `body::after` scanning line effect
3. Role cards: transparent glass with large border-radius, inset highlight
4. Buttons: capsule shape, 22px border-radius
5. Body background: solid `var(--bg-root)` (ambient orbs from navbar.js)

- [ ] **Step 1: Remove old `:root` CSS variables block, scanning line, update body**

In role-gate.html `<style>` block, remove:
- All `:root { ... }` variables
- `body::after` scanning line
- Old button/card styles

- [ ] **Step 2: Replace with iOS 26 role card styles**

```css
body {
  background: var(--bg-root); color: var(--text-primary);
  font-family: var(--font-sans);
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 40px 20px;
}
.role-gate-container {
  max-width: 960px; width: 100%;
  text-align: center;
}
.role-gate-title {
  font-size: 28px; font-weight: 700; letter-spacing: -0.5px;
  color: var(--text-primary); margin-bottom: 6px;
}
.role-gate-subtitle {
  font-size: 14px; color: var(--text-secondary); margin-bottom: 32px;
}
.role-cards {
  display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;
}
.role-card {
  flex: 1; min-width: 240px; max-width: 280px;
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-xl);
  padding: 28px 24px 24px;
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  cursor: pointer; text-align: center;
  transition: all var(--transition-spring);
  position: relative; overflow: hidden;
}
.role-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg), var(--glass-highlight-strong);
}
.role-card:active { transform: scale(0.98); }
.role-card .card-icon { font-size: 36px; margin-bottom: 12px; }
.role-card .card-title {
  font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px;
}
.role-card .card-subtitle {
  font-size: 11px; color: var(--text-muted); margin-bottom: 12px;
}
.role-card .card-desc {
  font-size: 12px; color: var(--text-secondary); line-height: 1.6;
}
/* Color accents per card */
.role-card.card-operator { border-top: 3px solid var(--accent-cyan); }
.role-card.card-manager { border-top: 3px solid var(--accent-amber); }
.role-card.card-developer { border-top: 3px solid var(--accent-purple); }
/* Card entrance animation */
.role-card { animation: cardIn 0.5s var(--transition-spring) both; }
.role-card:nth-child(1) { animation-delay: 0.05s; }
.role-card:nth-child(2) { animation-delay: 0.15s; }
.role-card:nth-child(3) { animation-delay: 0.25s; }
@keyframes cardIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (max-width: 860px) {
  .role-cards { flex-direction: column; align-items: center; }
  .role-card { max-width: 100%; }
}
```

- [ ] **Step 3: Update HTML card structure**

Replace existing role card HTML with simplified structure using new classes:
```html
<div class="role-card card-operator" onclick="selectRole('operator')">
  <div class="card-icon">⚙</div>
  <div class="card-title">运维工程师</div>
  <div class="card-subtitle">Operator · 执行层</div>
  <div class="card-desc">设备健康监控、异常告警处理、工单执行跟踪、根因归因分析</div>
</div>
```
(Repeat for manager and developer cards)

- [ ] **Step 4: Start server and verify role-gate page renders correctly**

Run: `cd web-dashboard; python app.py`
Visit: `http://localhost:8765/role-gate`
Check: Three glass cards with rounded corners, ambient light orbs visible behind, hover lifts card

- [ ] **Step 5: Commit**

```bash
git add web-dashboard/role-gate.html
git commit -m "feat: role-gate.html iOS26玻璃卡片重构"
```

---

### Task 3: Rewrite home.html — iOS 26 glass throughout

**Files:**
- Modify: `web-dashboard/home.html` (2275 lines)

This is the most complex page (operator + manager dual views, 10×10 grid, detail panels, trace panels, WO cards, parts table).

**Strategy:**
1. Remove old `:root` + `[data-theme="light"]` blocks (navbar.js provides them now)
2. Replace `body` styles to use new variables
3. Convert `.header` to glass card
4. Convert stat cards (4-column) to glass cards with `.glass-card` class
5. Replace 3D keycap `.cell` styles with soft glass `.cell` styles
6. Convert `.detail-panel` to iOS 26 glass
7. Convert `.trace-panel` to iOS 26 glass
8. Convert WO cards to glass cards
9. Update buttons to capsule shape
10. Update tables to iOS 26 style

- [ ] **Step 1: Remove old `:root` block and update base styles**

Remove lines ~18-36 (the `:root` and `[data-theme="light"]` blocks). Update `body` style:
```css
body {
  background: var(--bg-root); color: var(--text-primary);
  font-family: var(--font-sans);
  min-height: 100vh; overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 2: Update header as glass card**

```css
.header {
  padding: var(--space-md) var(--space-lg);
  max-width: 1400px; margin: var(--space-md) auto 0;
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 10px;
}
.header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.header h1 span { color: var(--accent-cyan); }
.header-stats { display: flex; gap: 20px; font-size: 12px; color: var(--text-secondary); }
.header-stats b { color: var(--text-primary); font-family: var(--font-mono); }
.mode-badge {
  font-size: 11px; padding: 4px 10px; border-radius: 10px; font-weight: 600;
  background: rgba(48,209,88,0.08); color: var(--accent-green);
  border: 0.5px solid rgba(48,209,88,0.15);
}
```

- [ ] **Step 3: Update stat cards (4-column row) to glass cards**

Replace the existing stat-card style with:
```css
.stat-cards {
  max-width: 1400px; margin: 16px auto; padding: 0 24px;
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.stat-card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur-light); -webkit-backdrop-filter: var(--glass-blur-light);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  transition: all var(--transition);
}
.stat-card:hover {
  box-shadow: var(--shadow-md), var(--glass-highlight);
  transform: translateY(-2px);
}
.stat-card .stat-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.stat-card .stat-value { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }
```

- [ ] **Step 4: Replace 3D keycap grid cells with soft glass**

Remove the keycap 3D effects (border-bottom shadow, inset highlight on old `.cell`).
Replace with:
```css
.machine-grid {
  display: grid; grid-template-columns: repeat(10, 1fr); grid-template-rows: repeat(10, 1fr);
  gap: 8px; max-width: 800px; margin: 0 auto;
}
.cell {
  aspect-ratio: 1; border-radius: var(--radius-sm); cursor: pointer; position: relative;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 600; letter-spacing: 0.3px;
  color: rgba(255,255,255,0.92);
  user-select: none;
  border: 0.5px solid var(--glass-border);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.cell:hover {
  transform: translateY(-2px) scale(1.04);
  box-shadow: var(--shadow-md);
  z-index: 10;
}
/* Health colors — soft glass backgrounds */
.cell.healthy  { background: rgba(48,209,88,0.25); }
.cell.warning  { background: rgba(240,168,64,0.28); }
.cell.degrading { background: rgba(255,69,58,0.22); }
.cell.critical { background: rgba(255,69,58,0.35); }
/* Work order pulse */
.cell.has-wo-alarm { animation: cellPulseAlarm 2s ease-in-out infinite; }
.cell.has-wo-warn  { animation: cellPulseWarn 3s ease-in-out infinite; }
@keyframes cellPulseAlarm {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,69,58,0.4); }
  50% { box-shadow: 0 0 0 6px rgba(255,69,58,0); }
}
@keyframes cellPulseWarn {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,179,64,0.3); }
  50% { box-shadow: 0 0 0 4px rgba(255,179,64,0); }
}
/* Priority badge */
.cell .prio-badge {
  position: absolute; top: -4px; right: -4px;
  background: var(--accent-red); color: #fff;
  font-size: 8px; font-weight: 700; padding: 1px 4px;
  border-radius: 6px; font-family: var(--font-mono);
}
```

- [ ] **Step 5: Update detail panel (slide-in) to iOS 26 glass**

```css
.detail-panel {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: 420px; max-width: 94vw;
  background: var(--glass-bg-modal);
  backdrop-filter: var(--glass-blur-strong); -webkit-backdrop-filter: var(--glass-blur-strong);
  border-left: 0.5px solid var(--glass-border);
  box-shadow: var(--shadow-xl), var(--glass-highlight);
  z-index: 2001;
  transform: translateX(100%);
  transition: transform 0.35s var(--transition-spring);
  overflow-y: auto;
  display: flex; flex-direction: column;
}
.detail-panel.open { transform: translateX(0); }
.panel-header {
  position: sticky; top: 0; z-index: 10;
  background: var(--glass-bg-header);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  padding: 18px 20px 12px; border-bottom: 0.5px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.panel-close {
  width: 32px; height: 32px; border-radius: 10px;
  border: 0.5px solid var(--border);
  background: var(--bg-card-alt); color: var(--text-secondary);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all var(--transition);
}
.panel-close:hover { background: var(--accent-red); color: #fff; border-color: var(--accent-red); }
.panel-body { padding: 16px 20px; }
/* ... keep existing panel-section, stat-row, signal-item, checklist-item styles but update colors */
```

- [ ] **Step 6: Update trace panel (center popup) to iOS 26 glass**

```css
.trace-panel {
  background: var(--glass-bg-modal);
  backdrop-filter: var(--glass-blur-strong); -webkit-backdrop-filter: var(--glass-blur-strong);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl), var(--glass-highlight-strong);
  /* ... keep existing positioning */
}
```

- [ ] **Step 7: Update WO cards to glass cards**

Replace existing `.wo-card` styles with glass-card pattern:
```css
.wo-card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur-light); -webkit-backdrop-filter: var(--glass-blur-light);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  transition: all var(--transition);
}
.wo-card:hover {
  box-shadow: var(--shadow-md), var(--glass-highlight);
  transform: translateY(-2px);
}
```

- [ ] **Step 8: Update parts table to glass container**

Wrap in `.glass-card` div or apply glass styles to the table container.

- [ ] **Step 9: Update ALL buttons to capsule shape**

Find all `<button>` elements and inline `style="..."` button styles, replace `border-radius: Xpx` with `22px` and apply new color values.

- [ ] **Step 10: Start server and verify homepage renders**

Visit `http://localhost:8765/` — check operator view, manager view, grid, panels, cards, tables.
Switch theme to light mode and verify.

- [ ] **Step 11: Commit**

```bash
git add web-dashboard/home.html
git commit -m "feat: home.html iOS26全页面玻璃化重构 — 网格/面板/卡片/按钮"
```

---

### Task 4: Rewrite index.html — iOS 26 glass throughout 8-tab dashboard

**Files:**
- Modify: `web-dashboard/index.html` (7361 lines)

This is the LARGEST file. Strategy:
1. Remove old `:root` + `[data-theme="light"]` blocks (navbar.js provides them)
2. Import shared glass-card, btn, tag, table classes from navbar.js
3. Update all section containers (sec0-sec7) to `.glass-card`
4. Update strategy cards, KPI cards, chart containers, tables
5. Update Pipeline status bar
6. Keep all JS business logic untouched

- [ ] **Step 1: Remove old Design Tokens block (lines ~17-90) and update base styles**

Remove `:root`, `[data-theme="light"]`, `[data-theme="light"] body::before` blocks.
Update body and base:
```css
body {
  background: var(--bg-root); color: var(--text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 2: Update section containers to glass cards**

For each sec0-sec7 container class, apply glass-card style:
```css
.section-container, .chart-card, .info-card, .stat-card, .card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur-light); -webkit-backdrop-filter: var(--glass-blur-light);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  transition: all var(--transition);
}
```
(This is the catch-all — individual `<style>` blocks per section may need specific overrides)

- [ ] **Step 3: Update strategy cards (sec6)**

```css
.strategy-card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 0.5px solid var(--glass-border);
  border-radius: var(--radius-xl);
  padding: var(--space-lg);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  cursor: pointer; transition: all var(--transition-spring);
}
.strategy-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg), var(--glass-highlight); }
.strategy-card.active {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 2px rgba(102,217,200,0.15), var(--shadow-md), var(--glass-highlight);
}
```

- [ ] **Step 4: Update KPI cards**
- [ ] **Step 5: Update chart containers**
- [ ] **Step 6: Update all tables**
- [ ] **Step 7: Update Pipeline status bar to glass**
- [ ] **Step 8: Update buttons**
- [ ] **Step 9: Start server and verify ALL 8 tabs**

Visit `http://localhost:8765/dashboard` — click through sec0-sec7, test theme toggle, test strategy switching.

- [ ] **Step 10: Commit**

```bash
git add web-dashboard/index.html
git commit -m "feat: index.html iOS26全8Tab玻璃化重构"
```

---

## Phase 2: P1 Secondary Pages

### Task 5: Update chat.html

**Files:**
- Modify: `web-dashboard/chat.html`

- Remove old `:root`/`[data-theme="light"]` block
- Sidebar: glass background
- Chat bubbles: glass cards with rounded corners
- Input area: glass with capsule send button
- Keep SSE streaming logic untouched

### Task 6: Update device-grid.html

**Files:**
- Modify: `web-dashboard/device-grid.html`

- Remove old `:root` block
- Device cells: soft glass (same pattern as home.html grid)
- Detail panel: iOS 26 glass slide-in
- SHAP explore modal: glass with strong blur

### Task 7: Update technical-overview.html

**Files:**
- Modify: `web-dashboard/technical-overview.html`

- Remove old `:root` block
- All 11 section cards: `.glass-card`
- Hero indicators: glass capsules
- Architecture diagram containers: glass
- KDE interactive section: glass container

---

## Phase 3: P2 Remaining Pages

### Task 8: Update knowledge-base.html (868 lines)

**Files:** Modify: `web-dashboard/knowledge-base.html`

Apply the standard P2 pattern:
1. Remove old `:root` block (navbar.js provides tokens)
2. Wrap content sections in `.glass-card` divs
3. Update buttons: `class="btn btn-primary"` / `class="btn btn-secondary"`
4. Update table containers: `class="glass-card"` wrapper
5. Update input fields: `class="input"` or apply glass styles
6. Verify: `http://localhost:8765/knowledge-base`
7. Commit: `git commit -m "feat: knowledge-base.html iOS26玻璃化"`

### Task 9: Update inventory.html (643 lines)

**Files:** Modify: `web-dashboard/inventory.html`

Same P2 pattern as Task 8. Pay special attention to:
- Inventory table: wrap in `.glass-card`, apply new table styles
- Procurement cards: `.glass-card` with amber left-border for urgent items
- Filter bar: glass input style

### Task 10: Update reports.html (907 lines)

**Files:** Modify: `web-dashboard/reports.html`

Same P2 pattern. Key areas:
- Report list cards: `.glass-card` with icon + metadata
- Search/filter: glass input + glass capsule buttons
- Report type badges: `.tag-cyan` / `.tag-purple` etc.

### Task 11: Update technicians.html (240 lines)

**Files:** Modify: `web-dashboard/technicians.html`

Same P2 pattern. Key areas:
- Technician cards: `.glass-card` with avatar + skills + availability indicator
- Schedule table: glass container

### Task 12: Update work-order-tracking.html (1300 lines)

**Files:** Modify: `web-dashboard/work-order-tracking.html`

Same P2 pattern. Key areas:
- Status columns: glass card per column (Kanban style)
- Work order cards: `.glass-card` with priority left-border
- Action buttons: `.btn` capsule system
- Status indicator dots: glass dots with glow

### Task 13: Update workflows.html (248 lines)

**Files:** Modify: `web-dashboard/workflows.html`

Same P2 pattern. Key areas:
- Workflow cards: `.glass-card` with status indicator
- Step timeline: glass nodes on glass track

---

## Verification Checklist

After ALL tasks complete, run through this checklist:

- [ ] **Server starts** without CSS errors: `cd web-dashboard; python app.py`
- [ ] **Homepage** (`/`): Operator view renders, grid cells are glass, detail panel slides in
- [ ] **Manager view**: KPI cards, strategy cards, WO cards all glass
- [ ] **Dashboard** (`/dashboard`): All 8 tabs render, ECharts charts display in glass containers
- [ ] **Theme toggle**: Switch light/dark — all pages respond correctly
- [ ] **Role gate** (`/role-gate`): Three glass cards, select role works
- [ ] **Role switching**: Navbar role toggle switches views correctly
- [ ] **Chat** (`/chat`): Messages display, input works, RAG sidebar renders
- [ ] **Device grid** (`/device-grid`): 100 cells render, detail panel opens
- [ ] **Technical overview** (`/technical-overview`): All sections render, KDE charts work
- [ ] **All P2 pages**: Render without broken styles
- [ ] **Mobile responsive**: 768px breakpoint collapses sidebar correctly
- [ ] **No console errors**: Check browser DevTools for JS/CSS errors
- [ ] **Business logic intact**: API calls, data loading, ECharts rendering all functional
