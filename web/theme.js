(() => {
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const key = 'stud-viewer-theme';
  const appearance = window.studAppearance || {mode: 'system', colors: {}};
  let preference = 'codex';
  try {
    const saved = localStorage.getItem(key);
    if (['codex', 'system', 'light', 'dark'].includes(saved)) preference = saved;
  } catch { /* The viewer also works when storage is unavailable. */ }
  function apply() {
    const mode = preference === 'codex' ? appearance.mode : preference;
    const theme = mode === 'system' ? (system.matches ? 'dark' : 'light') : mode;
    const root = document.documentElement;
    root.dataset.theme = theme;
    for (const name of ['--paper', '--stage', '--ink', '--accent', '--line']) root.style.removeProperty(name);
    if (preference === 'codex') {
      const colors = appearance.colors?.[theme] || {};
      if (colors.surface) {
        root.style.setProperty('--paper', colors.surface);
        root.style.setProperty('--stage', theme === 'dark' ? '#1b1b1b' : colors.surface);
      }
      if (colors.ink) root.style.setProperty('--ink', colors.ink);
      if (colors.accent) root.style.setProperty('--accent', colors.accent);
      // Match the quiet chrome separators instead of inheriting the green palette.
      root.style.setProperty('--line', `color-mix(in srgb, var(--paper), var(--ink) ${theme === 'dark' ? 9 : 14}%)`);
    }
    window.dispatchEvent(new Event('themechange'));
  }
  apply();
  system.addEventListener('change', apply);
  document.addEventListener('DOMContentLoaded', () => {
    const select = document.getElementById('theme');
    select.value = preference;
    select.addEventListener('change', () => {
      preference = select.value;
      try { localStorage.setItem(key, preference); } catch { /* Keep the session preference. */ }
      apply();
    });
  });
})();
