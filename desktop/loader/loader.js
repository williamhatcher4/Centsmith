// Loader-side safety net (plan item P4.1): if neither the backend handoff
// (window.navigate away from this page) nor a shell-injected error message
// has replaced this screen within 35s, say so instead of spinning silently.
// The Rust shell waits up to 30s for runtime metadata and 30s for the port,
// so its own injected error can land after this fires — it checks the title
// before writing, and overwriting this softer message is fine.
setTimeout(() => {
  const title = document.querySelector('.title');
  // The shell's error script already replaced the page — leave it alone.
  if (!title || title.textContent !== 'Starting Centsmith…') return;
  const hint = document.querySelector('.hint');
  if (!hint) return;
  hint.style.opacity = '0.85';
  hint.style.maxWidth = '36rem';
  hint.style.textAlign = 'center';
  hint.style.lineHeight = '1.6';
  hint.style.padding = '0 24px';
  hint.textContent =
    'This is taking longer than expected. If this screen never goes away, ' +
    'restart the app; if it keeps happening, check shell.log in the Centsmith ' +
    'data folder (%APPDATA%\\Centsmith) or reinstall Centsmith.';
}, 35000);
