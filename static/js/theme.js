// Apply before styles load to avoid a light flash on dark-theme pages.
(() => {
  let theme;
  try { theme = localStorage.getItem('alp-theme'); } catch (_) {}
  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.dataset.bsTheme = theme;
  document.documentElement.setAttribute('data-bs-theme', theme);
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) { meta.content = theme; }
})();
