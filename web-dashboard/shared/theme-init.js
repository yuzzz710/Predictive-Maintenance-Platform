/**
 * Theme Init — synchronous, must load BEFORE page render.
 * Reads theme preference from localStorage and applies it to <html>
 * before first paint, preventing flash of wrong theme.
 */
(function () {
  try {
    var theme = localStorage.getItem('dashboard-theme');
    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  } catch (e) {
    // localStorage unavailable — use dark theme by default
  }
})();
