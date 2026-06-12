/**
 * Role Switcher — shared utility for role switching.
 * Load AFTER navbar.js, before page-specific scripts.
 *
 * Usage:
 *   RoleSwitcher.get()            // 'operator' | 'manager' | 'developer'
 *   RoleSwitcher.set('manager')   // switch role + reload
 *   RoleSwitcher.label('manager') // '生产管理负责人'
 */
window.RoleSwitcher = (function () {
  var ROLE_META = {
    operator: {
      label: '运维工程师',
      subtitle: '执行层',
      icon: '&#9881;',  // ⚙ gear
      color: '#00c9a0'
    },
    manager: {
      label: '生产管理负责人',
      subtitle: '决策层',
      icon: '&#128202;',  // 📊 chart
      color: '#f0a030'
    },
    developer: {
      label: '平台开发人员',
      subtitle: '全量视图',
      icon: '&#128295;',  // 🔧 wrench
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
    sessionStorage.setItem('user_role', role);
    // Clear role context flag so AI gets fresh context on next chat
    sessionStorage.removeItem('role_context_sent');
    window.location.reload();
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
