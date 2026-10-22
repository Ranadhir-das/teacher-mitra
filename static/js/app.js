/* ============================================================
   TeacherMitra CRM & Partner Portal — Application JavaScript
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
  const workspace = document.getElementById('workspace');
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menu-toggle');
  const backdrop = document.getElementById('sidebar-backdrop');
  const collapseToggle = document.getElementById('sidebar-collapse-toggle');

  // --- Mobile Drawer Toggle ---
  function toggleMobileMenu(open) {
    if (!sidebar) return;
    const isOpen = open !== undefined ? open : !sidebar.classList.contains('is-open');
    sidebar.classList.toggle('is-open', isOpen);
    if (backdrop) backdrop.classList.toggle('is-visible', isOpen);
    if (menuToggle) menuToggle.setAttribute('aria-expanded', String(isOpen));
    document.body.classList.toggle('sidebar-mobile-open', isOpen);
  }

  menuToggle?.addEventListener('click', (e) => {
    e.preventDefault();
    toggleMobileMenu();
  });

  backdrop?.addEventListener('click', () => {
    toggleMobileMenu(false);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      toggleMobileMenu(false);
    }
  });

  // --- Desktop Sidebar Collapse Toggle ---
  const COLLAPSE_KEY = 'tm-sidebar-collapsed';
  const desktopSidebar = window.matchMedia('(min-width: 992px)');
  function updateCollapseButton(collapsed) {
    if (!collapseToggle) return;
    collapseToggle.setAttribute('aria-controls', 'sidebar');
    collapseToggle.setAttribute('aria-expanded', String(!collapsed));
    collapseToggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    collapseToggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
  }

  function setSidebarCollapsed(collapsed) {
    if (!workspace) return;
    workspace.classList.toggle('sidebar-collapsed', collapsed);
    updateCollapseButton(collapsed);
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? 'true' : 'false');
    } catch (_) {}
  }

  function restoreSidebarState() {
    if (!desktopSidebar.matches) {
      toggleMobileMenu(false);
      return;
    }
    try {
      setSidebarCollapsed(localStorage.getItem(COLLAPSE_KEY) === 'true');
    } catch (_) {
      setSidebarCollapsed(false);
    }
  }
  restoreSidebarState();
  if (desktopSidebar.addEventListener) desktopSidebar.addEventListener('change', restoreSidebarState);
  else desktopSidebar.addListener(restoreSidebarState);

  // Delegate from the workspace so clicks on the SVG/icon inside the button
  // are handled consistently, including after page navigation or template changes.
  workspace?.addEventListener('click', (event) => {
    const toggle = event.target instanceof Element
      ? event.target.closest('#sidebar-collapse-toggle')
      : null;
    if (!toggle || !workspace) return;
    event.preventDefault();
    event.stopPropagation();
    setSidebarCollapsed(!workspace.classList.contains('sidebar-collapsed'));
  });

  // --- Initialize Bootstrap Tooltips if available ---
  if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map((el) => new bootstrap.Tooltip(el, { boundary: document.body }));
  }

  // --- Bulk Selection ---
  document.getElementById('select-all-leads')?.addEventListener('change', (event) => {
    document.querySelectorAll('input[name="selected"]').forEach((input) => {
      input.checked = event.target.checked;
    });
  });

  // --- Form Double-Submission Prevention ---
  document.querySelectorAll('form[method="post"]:not([data-no-busy])').forEach((form) => {
    form.addEventListener('submit', () => {
      form.setAttribute('aria-busy', 'true');
      const button = form.querySelector('button[type="submit"]:not(.btn-no-busy)');
      if (button) {
        button.classList.add('is-submitting');
        const spinner = document.createElement('span');
        spinner.className = 'spinner-border spinner-border-sm me-2';
        spinner.setAttribute('role', 'status');
        spinner.setAttribute('aria-hidden', 'true');
        if (!button.querySelector('.spinner-border')) {
          button.prepend(spinner);
        }
      }
    });
  });
});

// --- Theme Management ---
const themeButtons = document.querySelectorAll('.theme-toggle');
function updateThemeButtons() {
  const dark = document.documentElement.dataset.bsTheme === 'dark';
  themeButtons.forEach((button) => {
    button.setAttribute('aria-pressed', String(dark));
    button.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} theme`);
    const icon = button.querySelector('.theme-icon');
    if (icon) icon.textContent = dark ? '\u2600\ufe0f' : '\u{1F319}';
    const label = button.querySelector('.theme-label');
    if (label) label.textContent = dark ? 'Light' : 'Dark';
  });
}

function setTheme(theme) {
  document.documentElement.dataset.bsTheme = theme;
  document.documentElement.setAttribute('data-bs-theme', theme);
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) { meta.content = theme; }
  try { localStorage.setItem('alp-theme', theme); } catch (_) {}
  updateThemeButtons();
  window.dispatchEvent(new CustomEvent('alp-theme-change', { detail: { theme, dark: theme === 'dark' } }));
}

themeButtons.forEach((button) => button.addEventListener('click', () => {
  const nextTheme = document.documentElement.dataset.bsTheme === 'dark' ? 'light' : 'dark';
  setTheme(nextTheme);
}));

window.addEventListener('storage', (event) => {
  if (event.key === 'alp-theme' && ['light', 'dark'].includes(event.newValue)) {
    setTheme(event.newValue);
  }
});

try {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    let stored;
    try { stored = localStorage.getItem('alp-theme'); } catch (_) {}
    if (!stored) {
      setTheme(e.matches ? 'dark' : 'light');
    }
  });
} catch (_) {}

updateThemeButtons();
