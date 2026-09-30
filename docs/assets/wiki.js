(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById('themeToggle');
  const themeLabel = document.getElementById('themeLabel');
  const applyTheme = theme => {
    root.dataset.theme = theme === 'light' ? 'light' : 'dark';
    const target = root.dataset.theme === 'dark' ? 'light' : 'dark';
    themeLabel.textContent = `${target[0].toUpperCase()}${target.slice(1)} mode`;
    themeButton.setAttribute('aria-label', `Switch to ${target} mode`);
    document.querySelector('meta[name="theme-color"]').content = target === 'light' ? '#070d16' : '#eef3f9';
  };
  applyTheme(root.dataset.theme);
  themeButton.addEventListener('click', () => {
    applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
    try { localStorage.setItem('sonarr-proxy-manager.wiki.theme', root.dataset.theme); } catch {}
  });
  const menu = document.getElementById('menuToggle');
  const closeMenu = () => {
    root.classList.remove('menu-open');
    menu.setAttribute('aria-expanded', 'false');
  };
  menu.addEventListener('click', () => {
    const open = root.classList.toggle('menu-open');
    menu.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
  document.querySelectorAll('.docs-nav a').forEach(link => link.addEventListener('click', closeMenu));
  const toc = document.getElementById('pageToc');
  document.querySelectorAll('.docs-content h2[id]').forEach(heading => {
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    toc.append(link);
  });
})();
