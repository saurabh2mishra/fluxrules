/**
 * Sidebar Auto-Hide Module
 *
 * Behaviours:
 *  • Toggle open/closed via the close button (✕) in the sidebar header
 *  • Auto-hide after INACTIVITY_MS of mouse/keyboard inactivity
 *  • Auto-hide when the user clicks anywhere outside the sidebar
 *  • Re-show when the user hovers the peek-zone (left edge) or clicks the floating ☰ button
 *  • Inactivity timer is reset on any mouse move, key press, or scroll
 *  • Content smoothly centers itself when sidebar hides
 */

(function () {
  'use strict';

  const INACTIVITY_MS = 4000;   // ms of inactivity before hiding
  const PEEK_ZONE_PX  = 12;     // px from left edge that triggers a peek

  let inactivityTimer = null;

  /* ── helpers ─────────────────────────────────────────────── */

  function getSidebar()   { return document.querySelector('.sidebar'); }
  function getToggleBtn() { return document.getElementById('sidebar-close'); }
  function getReopenBtn() { return document.getElementById('sidebar-reopen-btn'); }
  function getAppShell()  { return document.querySelector('.app-shell'); }

  /* ── state ────────────────────────────────────────────────── */

  function openSidebar() {
    const sidebar   = getSidebar();
    const reopenBtn = getReopenBtn();
    const shell     = getAppShell();
    if (!sidebar) return;

    sidebar.classList.remove('sidebar-hidden');
    sidebar.classList.add('sidebar-visible');
    sidebar.setAttribute('aria-expanded', 'true');
    if (shell) shell.classList.remove('sidebar-collapsed');

    if (reopenBtn) reopenBtn.classList.remove('visible');

    startCountdown();
    resetInactivityTimer();
  }

  function closeSidebar() {
    const sidebar   = getSidebar();
    const reopenBtn = getReopenBtn();
    const shell     = getAppShell();
    if (!sidebar) return;

    sidebar.classList.add('sidebar-hidden');
    sidebar.classList.remove('sidebar-visible');
    sidebar.setAttribute('aria-expanded', 'false');
    if (shell) shell.classList.add('sidebar-collapsed');

    if (reopenBtn) reopenBtn.classList.add('visible');

    stopCountdown();
    clearInactivityTimer();
  }

  function toggleSidebar() {
    const sidebar = getSidebar();
    if (!sidebar) return;
    sidebar.classList.contains('sidebar-hidden') ? openSidebar() : closeSidebar();
  }

  function isOpen() {
    const sidebar = getSidebar();
    return sidebar && !sidebar.classList.contains('sidebar-hidden');
  }

  /* ── countdown bar ────────────────────────────────────────── */

  let countdownRaf   = null;
  let countdownStart = 0;

  function startCountdown() {
    stopCountdown();
    const sidebar = getSidebar();
    if (!sidebar) return;

    let bar = sidebar.querySelector('.sidebar-countdown');
    if (!bar) {
      bar = document.createElement('div');
      bar.className = 'sidebar-countdown';
      sidebar.appendChild(bar);
    }
    bar.style.transition = 'none';
    bar.style.transform  = 'scaleX(1)';

    countdownStart = performance.now();

    function tick(now) {
      const elapsed  = now - countdownStart;
      const progress = Math.max(0, 1 - elapsed / INACTIVITY_MS);
      bar.style.transition = 'none';
      bar.style.transform  = `scaleX(${progress})`;
      if (progress > 0) {
        countdownRaf = requestAnimationFrame(tick);
      }
    }
    countdownRaf = requestAnimationFrame(tick);
  }

  function stopCountdown() {
    if (countdownRaf) {
      cancelAnimationFrame(countdownRaf);
      countdownRaf = null;
    }
    const sidebar = getSidebar();
    if (sidebar) {
      const bar = sidebar.querySelector('.sidebar-countdown');
      if (bar) bar.style.transform = 'scaleX(0)';
    }
  }

  /* ── inactivity timer ─────────────────────────────────────── */

  function resetInactivityTimer() {
    clearInactivityTimer();
    if (isOpen()) {
      startCountdown();
      inactivityTimer = setTimeout(closeSidebar, INACTIVITY_MS);
    }
  }

  function clearInactivityTimer() {
    if (inactivityTimer) {
      clearTimeout(inactivityTimer);
      inactivityTimer = null;
    }
  }

  /* ── activity listeners ────────────────────────────────────── */

  function onActivity() {
    if (isOpen()) resetInactivityTimer();
  }

  /* ── outside-click ────────────────────────────────────────── */

  function onDocumentClick(e) {
    const sidebar   = getSidebar();
    const closeBtn  = getToggleBtn();
    const reopenBtn = getReopenBtn();
    if (!sidebar || !isOpen()) return;

    const clickedInsideSidebar = sidebar.contains(e.target);
    const clickedClose         = closeBtn  && closeBtn.contains(e.target);
    const clickedReopen        = reopenBtn && reopenBtn.contains(e.target);

    if (!clickedInsideSidebar && !clickedClose && !clickedReopen) {
      closeSidebar();
    }
  }

  /* ── peek zone (hover left edge to re-open) ───────────────── */

  function onMouseMove(e) {
    onActivity();
    if (!isOpen() && e.clientX <= PEEK_ZONE_PX) {
      openSidebar();
    }
  }

  /* ── init ─────────────────────────────────────────────────── */

  function init() {
    const sidebar = getSidebar();
    if (!sidebar) return;

    sidebar.style.position = 'relative';

    // Wrap the nav-brand in a header row with a close button
    const brand = sidebar.querySelector('.nav-brand');
    if (brand && !document.getElementById('sidebar-close')) {
      const header = document.createElement('div');
      header.className = 'sidebar-header';

      // Move brand into the header wrapper
      brand.parentNode.insertBefore(header, brand);
      header.appendChild(brand);

      // Create close ✕ button
      const closeBtn = document.createElement('button');
      closeBtn.id = 'sidebar-close';
      closeBtn.className = 'sidebar-close-btn';
      closeBtn.setAttribute('aria-label', 'Close sidebar');
      closeBtn.title = 'Close sidebar';
      closeBtn.innerHTML = '✕';
      closeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeSidebar();
      });

      header.appendChild(closeBtn);
    }

    // Wire the floating re-open button
    const reopenBtn = getReopenBtn();
    if (reopenBtn) {
      reopenBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openSidebar();
      });
    }

    // Auto-hide: outside click
    document.addEventListener('click', onDocumentClick, true);

    // Auto-hide: inactivity (mousemove also handles peek-zone)
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('keydown',   onActivity);
    document.addEventListener('scroll',    onActivity, true);

    // Sidebar interaction resets the inactivity timer
    sidebar.addEventListener('mouseenter', onActivity);
    sidebar.addEventListener('click',      onActivity);

    // Start with sidebar open; kick off inactivity timer
    resetInactivityTimer();

    // Accessibility: close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen()) closeSidebar();
    });
  }

  // Run after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
