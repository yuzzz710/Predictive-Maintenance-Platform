/**
 * Role Check — synchronous, must load BEFORE page render.
 * Include as the FIRST <script> in <head>.
 *
 * Checks sessionStorage for user_role. If missing, redirects to /role-gate.
 * Otherwise sets data-role on <html> so CSS rules can filter content
 * before the first paint — zero flash of wrong content.
 */
(function () {
  try {
    var role = sessionStorage.getItem('user_role');

    // No role selected → redirect to role gate, preserving intended destination
    if (!role) {
      var target = encodeURIComponent(window.location.pathname + window.location.search);
      // Only redirect if we're not already on the role-gate page
      if (window.location.pathname !== '/role-gate') {
        window.location.replace('/role-gate?redirect=' + target);
      }
      return;
    }

    // Validate role is one of the three known values
    if (role !== 'operator' && role !== 'manager' && role !== 'developer') {
      sessionStorage.removeItem('user_role');
      if (window.location.pathname !== '/role-gate') {
        window.location.replace('/role-gate');
      }
      return;
    }

    // Set data-role attribute — CSS rules use this to filter content
    document.documentElement.setAttribute('data-role', role);
    console.log('[role-check] data-role set to:', role);
  } catch (e) {
    // sessionStorage unavailable (e.g. iframe sandbox, privacy mode)
    // Fall through — page renders without role filtering (all content visible)
    console.warn('[role-check] sessionStorage unavailable, skipping role filter');
  }
})();
