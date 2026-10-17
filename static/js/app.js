const menuToggle = document.getElementById('menu-toggle');
menuToggle?.addEventListener('click', () => {
  const open = document.getElementById('sidebar').classList.toggle('is-open');
  menuToggle.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    document.getElementById('sidebar')?.classList.remove('is-open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  }
});

document.getElementById('select-all-leads')?.addEventListener('change', (event) => {
  document.querySelectorAll('input[name="selected"]').forEach((input) => { input.checked = event.target.checked; });
});
document.querySelectorAll('form[method="post"]').forEach((form) => {
  form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.classList.add('is-submitting'); button.textContent = 'Processing...'; }
  });
});

const themeButtons = document.querySelectorAll('.theme-toggle');
function updateThemeButtons() {
  const dark = document.documentElement.dataset.bsTheme === 'dark';
  themeButtons.forEach((button) => {
    button.setAttribute('aria-pressed', String(dark));
    button.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} theme`);
    const icon = button.querySelector('.theme-icon');
    if (icon) icon.textContent = dark ? '\u2600\ufe0f' : '\u{1F319}';
    const label = button.querySelector('.theme-label');
    if (label) label.textContent = dark ? 'Light theme' : 'Dark theme';
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

