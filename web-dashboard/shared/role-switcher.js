/**
 * Role Switcher — shared utility for role switching.
 * Load AFTER navbar.js, before page-specific scripts.
 *
 * Usage:
 *   RoleSwitcher.get()            // 'operator' | 'manager' | 'developer'
 *   RoleSwitcher.set('manager')   // switch role (zero-reload, ~400ms transition)
 *   RoleSwitcher.label('manager') // '生产管理负责人'
 */
window.RoleSwitcher = (function () {
  var ROLE_META = {
    operator: {
      label: '运维工程师',
      subtitle: '执行层',
      icon: '⚙',
      color: '#00c9a0'
    },
    manager: {
      label: '生产管理负责人',
      subtitle: '决策层',
      icon: '📊',
      color: '#f0a030'
    },
    developer: {
      label: '平台开发人员',
      subtitle: '全量视图',
      icon: '🔧',
      color: '#a371f7'
    }
  };

  function get() {
    return sessionStorage.getItem('user_role') || 'developer';
  }

  function set(role) {
    if (!ROLE_META[role]) {
      console.warn('[RoleSwitcher] Unknown role:', role);
      return;
    }
    var oldRole = get();
    if (oldRole === role) return;

    sessionStorage.setItem('user_role', role);
    sessionStorage.removeItem('role_context_sent');

    // Instant CSS filtering via attribute change (no reload)
    document.documentElement.setAttribute('data-role', role);

    // Show 400ms fade transition overlay
    showTransition(oldRole, role);

    // Dispatch custom event so page scripts can re-fetch role-dependent data
    var event = new CustomEvent('rolechange', {
      detail: { from: oldRole, to: role },
      bubbles: true
    });
    document.documentElement.dispatchEvent(event);
  }

  function showTransition(from, to) {
    var meta = ROLE_META[to] || ROLE_META.developer;
    var overlay = document.getElementById('role-transition-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'role-transition-overlay';
      overlay.innerHTML = '<div class="rto-icon"></div><div class="rto-label"></div><div class="rto-subtitle"></div>';
      document.body.appendChild(overlay);
    }
    overlay.querySelector('.rto-icon').textContent = meta.icon;
    overlay.querySelector('.rto-label').textContent = meta.label;
    overlay.querySelector('.rto-subtitle').textContent = meta.subtitle;
    overlay.style.setProperty('--rto-color', meta.color);

    // Trigger animation
    overlay.classList.add('active');
    setTimeout(function () {
      overlay.classList.remove('active');
    }, 420);
  }

  // Inject transition overlay CSS once
  function injectOverlayCSS() {
    if (document.getElementById('role-transition-css')) return;
    var style = document.createElement('style');
    style.id = 'role-transition-css';
    style.textContent = [
      '#role-transition-overlay {',
      '  position: fixed; inset: 0; z-index: 9999;',
      '  display: flex; flex-direction: column; align-items: center; justify-content: center;',
      '  background: rgba(10,14,23,0.88);',
      '  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);',
      '  opacity: 0; pointer-events: none;',
      '  transition: opacity 0.2s ease-out;',
      '}',
      '#role-transition-overlay.active {',
      '  opacity: 1; pointer-events: auto;',
      '  animation: rtoFade 0.42s ease-out;',
      '}',
      '@keyframes rtoFade {',
      '  0% { opacity: 0; }',
      '  30% { opacity: 1; }',
      '  70% { opacity: 1; }',
      '  100% { opacity: 0; }',
      '}',
      '#role-transition-overlay .rto-icon { font-size: 48px; margin-bottom: 12px; }',
      '#role-transition-overlay .rto-label {',
      '  font-size: 20px; font-weight: 700; color: #e6ebf2;',
      '  font-family: "PingFang SC","Microsoft YaHei","Hiragino Sans GB","Segoe UI",system-ui,sans-serif;',
      '  margin-bottom: 4px;',
      '}',
      '#role-transition-overlay .rto-subtitle {',
      '  font-size: 13px; color: var(--rto-color, #00c9a0);',
      '  font-family: "Cascadia Code","Fira Code",monospace;',
      '}'
    ].join('\n');
    document.head.appendChild(style);
  }

  // Inject CSS on first load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectOverlayCSS);
  } else {
    injectOverlayCSS();
  }

  function label(role) {
    return (ROLE_META[role] || ROLE_META.developer).label;
  }

  function subtitle(role) {
    return (ROLE_META[role] || ROLE_META.developer).subtitle;
  }

  function icon(role) {
    return (ROLE_META[role] || ROLE_META.developer).icon;
  }

  function color(role) {
    return (ROLE_META[role] || ROLE_META.developer).color;
  }

  function meta(role) {
    return ROLE_META[role] || ROLE_META.developer;
  }

  return {
    get: get,
    set: set,
    label: label,
    subtitle: subtitle,
    icon: icon,
    color: color,
    meta: meta,
    ROLE_META: ROLE_META
  };
})();
