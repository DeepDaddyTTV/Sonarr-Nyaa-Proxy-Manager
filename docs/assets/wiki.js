(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById('themeToggle');
  const themeLabel = document.getElementById('themeLabel');
  const icon = document.querySelector('link[rel="icon"]');
  const shape = new Image();
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const context = canvas.getContext('2d');
  const renderIcon = () => {
    if (!icon || !context || !shape.complete || !shape.naturalWidth) return;
    const colors = getComputedStyle(root);
    const gradient = context.createLinearGradient(0, 0, 64, 64);
    gradient.addColorStop(0, colors.getPropertyValue('--cyan').trim());
    gradient.addColorStop(1, colors.getPropertyValue('--pink').trim());
    context.clearRect(0, 0, 64, 64);
    context.globalCompositeOperation = 'source-over';
    context.fillStyle = gradient;
    context.fillRect(0, 0, 64, 64);
    // Tab icons cannot inherit the site's CSS mask.
    context.globalCompositeOperation = 'destination-in';
    context.drawImage(shape, 0, 0, 64, 64);
    icon.type = 'image/png';
    icon.href = canvas.toDataURL('image/png');
  };
  if (icon) {
    shape.addEventListener('load', renderIcon);
    shape.src = icon.href;
  }
  const applyTheme = theme => {
    root.dataset.theme = theme === 'light' ? 'light' : 'dark';
    const target = root.dataset.theme === 'dark' ? 'light' : 'dark';
    themeLabel.textContent = `${target[0].toUpperCase()}${target.slice(1)} mode`;
    themeButton.setAttribute('aria-label', `Switch to ${target} mode`);
    document.querySelector('meta[name="theme-color"]').content = target === 'light' ? '#070d16' : '#eef3f9';
    renderIcon();
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
