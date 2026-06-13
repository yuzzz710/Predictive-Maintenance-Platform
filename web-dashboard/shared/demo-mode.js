/**
 * Demo Mode — Golden Path Auto-Advance + Spotlight (v2)
 * Cross-page navigation via sessionStorage. Activated by ?demo=true.
 * Exposes window.DemoMode API.
 *
 * Usage:
 *   DemoMode.start()    // begin from step 0
 *   DemoMode.stop()     // exit & clear state
 *   DemoMode.next()     // skip to next step
 *   DemoMode.prev()     // go back one step
 */

(function () {
  // ── Step definitions ──
  var STEPS = [
    {
      id: 'grid-overview', page: '/',
      title: '10×10 设备健康网格',
      narration: '系统实时监控100台CNC机床。绿色=健康，琥珀=退化，红色=高危。Top 3 风险设备以金色脉冲高亮标记。',
      selector: '#machine-grid',
      duration: 8000,
      action: function () {
        var role = sessionStorage.getItem('user_role') || 'developer';
        if (role === 'manager' && window.RoleSwitcher) { window.RoleSwitcher.set('operator'); }
      }
    },
    {
      id: 'shap-attribution', page: '/',
      title: 'SHAP 可解释性归因分析',
      narration: '点击任意高危设备（红色方块）可查看AI根因分析。SHAP值揭示每个传感器参数对故障预测的贡献度——从"黑盒预测"到"白盒归因"。',
      selector: '#machine-grid .cell.critical',
      duration: 10000,
      action: function () {
        if (typeof machineMap === 'undefined') return;
        var topMid = null;
        Object.keys(machineMap).forEach(function(mid) {
          var m = machineMap[mid];
          if (m.health && m.health.health_level === 'Critical' && !topMid) topMid = mid;
        });
        if (topMid && typeof openPanel === 'function') {
          setTimeout(function() { openPanel(topMid, machineMap[topMid]); }, 1200);
        }
      }
    },
    {
      id: 'fault-injection', page: '/',
      title: '一键故障注入·6步闭环演示',
      narration: '从故障信号注入→Z-Score异常检测→SHAP根因分析→自动工单生成→技师分配与邮件通知→修复验收，完整演示AI驱动的运维闭环。',
      selector: '#btn-fi',
      duration: 8000,
      action: function () {
        var btn = document.getElementById('btn-fi');
        if (btn && typeof openFixture === 'function') {
          setTimeout(function() { openFixture(); }, 1000);
        }
      }
    },
    {
      id: 'algorithm-comparison', page: '/technical-overview',
      title: '7种算法对比实验墙',
      narration: '在真实2999行工业数据上训练7种算法。MTNN达到AUC≈0.59，XGBoost≈0.50。数据天花板分析揭示：受限于4参数传感器，升级后可提升至AUC≈0.90。',
      selector: 'h2',
      duration: 12000,
      action: function () { /* page just loaded — nothing extra needed */ }
    },
    {
      id: 'kde-ceiling', page: '/technical-overview',
      title: '传感器升级ROI·数据天花板',
      narration: '交互式KDE分布对比——拖动Phase滑块从0→3，Youden\'s J 从0.075→0.90。量化传感器升级的投资回报：成本$12.5万，预期故障检测率提升12倍。',
      selector: '#sensor-slider',
      duration: 12000,
      action: function () {
        var slider = document.getElementById('sensor-slider');
        if (slider) {
          var val = 0;
          var interval = setInterval(function() {
            val++; slider.value = val; slider.dispatchEvent(new Event('input'));
            if (val >= 3) clearInterval(interval);
          }, 2500);
        }
      }
    },
    {
      id: 'strategy-selector', page: '/dashboard',
      title: '三策略维护模式对比',
      narration: '成本效率·生产效率·质量优先——三种策略在成本-停机-质量三角中各有侧重。切换策略后系统自动重算工单优先级与排程方案。',
      selector: '#strategy-selector',
      duration: 12000,
      action: function () {
        var role = sessionStorage.getItem('user_role') || 'developer';
        if (role !== 'manager' && window.RoleSwitcher) { window.RoleSwitcher.set('manager'); }
        // Scroll to sec6 if needed
        var sec6 = document.getElementById('sec6');
        if (sec6) setTimeout(function() { sec6.scrollIntoView({behavior:'smooth',block:'start'}); }, 500);
      }
    },
    {
      id: 'pareto-frontier', page: '/dashboard',
      title: '多目标帕累托优化',
      narration: '三维帕累托前沿图——X轴=维护成本，Y轴=停机时间，Z轴=质量风险。三种策略定位在最优前沿面上，展现运筹优化的数学美感。',
      selector: '#chart-pareto-3d',
      duration: 15000,
      action: function () {
        var sec6 = document.getElementById('sec6');
        if (sec6) setTimeout(function() { sec6.scrollIntoView({behavior:'smooth',block:'start'}); }, 500);
      }
    },
    {
      id: 'ai-copilot', page: '/chat',
      title: 'AI Copilot 智能问答',
      narration: '基于DeepSeek大模型+RAG知识库的工业智能助手。自然语言查询设备状态、故障历史、维护建议——"当前哪些设备风险最高？"',
      selector: '.chat-input',
      duration: 10000,
      action: function () {}
    }
  ];

  var state = {
    running: false,
    currentStep: -1,
    paused: false,
    timerId: null
  };

  var spotlightEl = null, narrationEl = null, controlBar = null, progressBar = null;

  function saveState() {
    sessionStorage.setItem('demo_state', JSON.stringify({
      running: state.running,
      currentStep: state.currentStep,
      paused: state.paused
    }));
  }

  function clearState() {
    sessionStorage.removeItem('demo_state');
  }

  // ── DOM ──
  function createDOM() {
    if (spotlightEl) return;

    spotlightEl = document.createElement('div');
    spotlightEl.className = 'demo-spotlight';
    document.body.appendChild(spotlightEl);

    narrationEl = document.createElement('div');
    narrationEl.className = 'demo-narration';
    narrationEl.innerHTML =
      '<div class="demo-narr-icon"></div>' +
      '<div class="demo-narr-title"></div>' +
      '<div class="demo-narr-text"></div>' +
      '<div class="demo-narr-step">0 / ' + STEPS.length + '</div>';
    document.body.appendChild(narrationEl);

    controlBar = document.createElement('div');
    controlBar.className = 'demo-controls';
    controlBar.innerHTML =
      '<div class="demo-ctrl-buttons">' +
        '<button class="demo-ctrl-btn" data-action="prev" title="上一步 (←)">&#x23EE;</button>' +
        '<button class="demo-ctrl-btn" data-action="pause" title="暂停/继续 (Space)">&#x23F8;</button>' +
        '<button class="demo-ctrl-btn" data-action="next" title="下一步 (→)">&#x23ED;</button>' +
        '<button class="demo-ctrl-btn demo-ctrl-exit" data-action="stop" title="退出 (Esc)">&#x2715;</button>' +
      '</div>' +
      '<div class="demo-ctrl-progress">' +
        '<div class="demo-progress-track">' +
          '<div class="demo-progress-fill" id="demo-progress-fill"></div>' +
        '</div>' +
        '<span class="demo-progress-label" id="demo-progress-label">0/' + STEPS.length + '</span>' +
      '</div>';
    document.body.appendChild(controlBar);
    progressBar = document.getElementById('demo-progress-fill');

    controlBar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var a = btn.getAttribute('data-action');
      if (a === 'prev') prev();
      else if (a === 'next') next();
      else if (a === 'pause') togglePause();
      else if (a === 'stop') stop();
    });

    document.addEventListener('keydown', function (e) {
      if (!state.running) return;
      if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') prev();
      else if (e.key === ' ') { e.preventDefault(); togglePause(); }
      else if (e.key === 'Escape') stop();
    });
  }

  // ── Spotlight ──
  function updateSpotlight(targetEl, padding) {
    padding = padding || 24;
    if (!targetEl) { spotlightEl.style.clipPath = 'none'; return; }
    var r = targetEl.getBoundingClientRect();
    var W = window.innerWidth, H = window.innerHeight;
    var x = Math.max(0, r.left - padding);
    var y = Math.max(0, r.top - padding);
    var w = Math.min(W - x, r.width + padding * 2);
    var h = Math.min(H - y, r.height + padding * 2);

    spotlightEl.style.clipPath =
      'polygon(0% 0%,0% 100%,' + x + 'px 100%,' + x + 'px ' + y + 'px,' +
      (x + w) + 'px ' + y + 'px,' + (x + w) + 'px ' + (y + h) + 'px,' +
      x + 'px ' + (y + h) + 'px,' + x + 'px 100%,100% 100%,100% 0%)';

    var nX = r.right + 32, nY = r.top;
    var nW = 380;
    if (nX + nW > W - 24) { nX = Math.max(24, r.left); nY = r.bottom + 24; }
    if (nY + 180 > H - 120) { nY = Math.max(80, r.top - 200); }
    nX = Math.max(24, Math.min(W - nW - 24, nX));
    nY = Math.max(80, Math.min(H - 200, nY));
    narrationEl.style.left = nX + 'px';
    narrationEl.style.top = nY + 'px';
  }

  function onResize() {
    if (!state.running || state.currentStep < 0) return;
    var el = document.querySelector(STEPS[state.currentStep].selector);
    if (el) updateSpotlight(el);
  }

  // ── Navigation ──
  function navigateToStep(idx) {
    if (idx < 0 || idx >= STEPS.length) { finish(); return; }

    var step = STEPS[idx];
    var currentPage = window.location.pathname;

    // Different page — save state and navigate
    if (step.page && step.page !== currentPage && step.page !== '/') {
      state.currentStep = idx;
      saveState();
      window.location.href = step.page + '?demo=true&step=' + idx;
      return;
    }
    if (step.page === '/' && currentPage !== '/' && currentPage !== '') {
      state.currentStep = idx;
      saveState();
      window.location.href = '/?demo=true&step=' + idx;
      return;
    }

    // Same page — render step
    renderStep(idx);
  }

  function renderStep(idx) {
    state.currentStep = idx;
    saveState();
    var step = STEPS[idx];

    narrationEl.querySelector('.demo-narr-icon').textContent = (idx + 1) + '/' + STEPS.length;
    narrationEl.querySelector('.demo-narr-title').textContent = step.title;
    narrationEl.querySelector('.demo-narr-text').textContent = step.narration;
    narrationEl.querySelector('.demo-narr-step').textContent = (idx + 1) + ' / ' + STEPS.length;

    document.getElementById('demo-progress-label').textContent = (idx + 1) + '/' + STEPS.length;
    progressBar.style.width = ((idx + 1) / STEPS.length * 100) + '%';

    // Spotlight target element — retry if not yet rendered
    var target = document.querySelector(step.selector);
    var retries = 0;
    function trySpotlight() {
      target = document.querySelector(step.selector);
      if (target) {
        spotlightEl.classList.add('active');
        narrationEl.classList.add('active');
        updateSpotlight(target);
      } else if (retries < 20) {
        retries++;
        setTimeout(trySpotlight, 300);
      }
    }
    trySpotlight();

    if (step.action) {
      try { step.action(); } catch (e) { console.warn('[demo-mode] action error:', e); }
    }

    if (!state.paused && state.running) {
      clearTimeout(state.timerId);
      state.timerId = setTimeout(function () { navigateToStep(idx + 1); }, step.duration);
    }
  }

  // ── Public API ──
  function start() {
    if (state.running) return;
    createDOM();
    state.running = true;
    state.paused = false;
    controlBar.classList.add('active');
    spotlightEl.classList.add('active');
    window.addEventListener('resize', onResize);
    console.log('[demo-mode] Started. ' + STEPS.length + ' steps.');
    navigateToStep(0);
  }

  function stop() {
    state.running = false; state.paused = false;
    clearTimeout(state.timerId);
    if (spotlightEl) spotlightEl.classList.remove('active');
    if (narrationEl) narrationEl.classList.remove('active');
    if (controlBar) controlBar.classList.remove('active');
    window.removeEventListener('resize', onResize);
    clearState();
    console.log('[demo-mode] Stopped.');
  }

  function next() {
    if (!state.running) return;
    clearTimeout(state.timerId);
    navigateToStep(state.currentStep + 1);
  }

  function prev() {
    if (!state.running || state.currentStep <= 0) return;
    clearTimeout(state.timerId);
    navigateToStep(state.currentStep - 1);
  }

  function togglePause() {
    if (!state.running) return;
    state.paused = !state.paused;
    saveState();
    var btn = controlBar.querySelector('[data-action="pause"]');
    if (btn) btn.textContent = state.paused ? '▶' : '⏸';
    if (!state.paused) {
      var step = STEPS[state.currentStep];
      state.timerId = setTimeout(function () { navigateToStep(state.currentStep + 1); }, step.duration);
    } else {
      clearTimeout(state.timerId);
    }
  }

  function finish() {
    narrationEl.querySelector('.demo-narr-icon').textContent = '✓';
    narrationEl.querySelector('.demo-narr-title').textContent = '演示完成';
    narrationEl.querySelector('.demo-narr-text').textContent = '黄金演示路径已走完。系统全部核心能力已展示。评委可自由探索或点击底部按钮重新演示。';
    narrationEl.querySelector('.demo-narr-step').textContent = STEPS.length + ' / ' + STEPS.length;
    progressBar.style.width = '100%';
    document.getElementById('demo-progress-label').textContent = STEPS.length + '/' + STEPS.length;
    if (spotlightEl) { spotlightEl.style.clipPath = 'none'; spotlightEl.style.opacity = '0.3'; }
    state.running = false;
    clearTimeout(state.timerId);
    clearState();
  }

  window.DemoMode = {
    start: start, stop: stop,
    next: next, prev: prev,
    togglePause: togglePause,
    getState: function () {
      return { running: state.running, currentStep: state.currentStep, totalSteps: STEPS.length, paused: state.paused };
    }
  };

  // ── Auto-init ──
  function autoInit() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('demo') !== 'true') return;

      // Inject demo CSS into any page (ensures spotlight/narration/controls work everywhere)
      if (!document.getElementById('demo-mode-css')) {
        var style = document.createElement('style');
        style.id = 'demo-mode-css';
        style.textContent =
          '.demo-spotlight{position:fixed;inset:0;z-index:9980;background:rgba(0,0,0,0.62);pointer-events:none;opacity:0;transition:opacity 0.5s ease}' +
          '.demo-spotlight.active{opacity:1}' +
          '.demo-narration{position:fixed;z-index:9981;width:380px;max-width:90vw;background:rgba(20,24,32,0.96);border:1px solid rgba(0,201,160,0.25);border-radius:10px;padding:20px 24px;box-shadow:0 12px 40px rgba(0,0,0,0.5);opacity:0;transform:translateY(12px);transition:opacity 0.35s ease,transform 0.35s ease;pointer-events:none;font-family:"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif}' +
          '.demo-narration.active{opacity:1;transform:translateY(0)}' +
          '.demo-narr-icon{font-size:13px;color:var(--accent-cyan,#00c9a0);margin-bottom:6px}' +
          '.demo-narr-title{font-size:16px;font-weight:700;color:#e6ebf2;margin-bottom:10px}' +
          '.demo-narr-text{font-size:13px;color:#8e9aab;line-height:1.7}' +
          '.demo-narr-step{font-size:10px;color:#5a6474;margin-top:10px;text-align:right}' +
          '.demo-controls{position:fixed;bottom:0;left:0;right:0;z-index:9982;background:rgba(10,14,23,0.94);border-top:1px solid rgba(0,201,160,0.2);padding:12px 24px;display:none;align-items:center;gap:16px;font-family:"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif;backdrop-filter:blur(12px)}' +
          '.demo-controls.active{display:flex}' +
          '.demo-ctrl-buttons{display:flex;gap:8px}' +
          '.demo-ctrl-btn{width:36px;height:36px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:#8e9aab;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;transition:all 0.15s}' +
          '.demo-ctrl-btn:hover{background:rgba(255,255,255,0.08);color:#e6ebf2}' +
          '.demo-ctrl-exit:hover{background:rgba(240,68,68,0.12)!important;color:#f04444!important}' +
          '.demo-ctrl-progress{flex:1;display:flex;align-items:center;gap:10px}' +
          '.demo-progress-track{flex:1;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden}' +
          '.demo-progress-fill{height:100%;background:var(--accent-cyan,#00c9a0);border-radius:2px;transition:width 0.4s ease;width:0%}' +
          '.demo-progress-label{font-size:11px;color:#5a6474;font-family:"Cascadia Code",monospace;white-space:nowrap}' +
          'html[data-demo="true"] .btn-demo-start{display:inline-flex!important}';
        document.head.appendChild(style);
      }

      document.documentElement.setAttribute('data-demo', 'true');

      var stepParam = parseInt(params.get('step'));
      var saved = null;
      try { saved = JSON.parse(sessionStorage.getItem('demo_state') || 'null'); } catch(e) {}

      // Show start button on home page
      function showButton() {
        var btn = document.getElementById('btn-demo-start');
        if (btn) { btn.style.display = 'inline-flex'; btn.title = '点击开始8步黄金演示路径'; }
      }

      if (saved && saved.running && saved.currentStep >= 0) {
        // Resuming demo from cross-page navigation
        createDOM();
        state.running = true;
        state.paused = saved.paused || false;
        state.currentStep = saved.currentStep;
        controlBar.classList.add('active');
        spotlightEl.classList.add('active');
        window.addEventListener('resize', onResize);
        renderStep(saved.currentStep);
        // Re-schedule auto-advance
        if (!state.paused) {
          var step = STEPS[saved.currentStep];
          state.timerId = setTimeout(function () { navigateToStep(saved.currentStep + 1); }, step.duration);
        }
      } else if (!isNaN(stepParam) && stepParam >= 0) {
        // Explicit step from URL — resume
        createDOM();
        state.running = true;
        state.paused = false;
        controlBar.classList.add('active');
        spotlightEl.classList.add('active');
        window.addEventListener('resize', onResize);
        renderStep(stepParam);
        if (!state.paused) {
          var step = STEPS[stepParam];
          state.timerId = setTimeout(function () { navigateToStep(stepParam + 1); }, step.duration);
        }
      } else {
        // Fresh start — wait for page ready, show button
        var isHome = window.location.pathname === '/' || window.location.pathname === '';
        if (isHome) {
          var checkReady = setInterval(function () {
            var ready = typeof machineMap !== 'undefined' && Object.keys(machineMap).length > 0;
            if (!ready) {
              // Also check if we're not on home (no machineMap expected)
              if (typeof machineMap === 'undefined') ready = window.location.pathname !== '/' && window.location.pathname !== '';
            }
            if (ready) { clearInterval(checkReady); showButton(); console.log('[demo-mode] Ready.'); }
          }, 500);
          setTimeout(function () { clearInterval(checkReady); showButton(); }, 8000);
        } else {
          showButton();
        }
      }
    } catch (e) { console.error('[demo-mode] autoInit error:', e); }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  console.log('[demo-mode] v2 loaded. Cross-page navigation ready.');
})();
