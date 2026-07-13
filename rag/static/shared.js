/* ═══════════════════════════════════════════════════════════════════════════
   shared.js — codice IDENTICO tra i template *.unified.html, servito da
   /static/ (StaticFiles). Contiene solo:
     · themeVar()      — lettura di una CSS variable dal tema attivo
     · matrix rain     — sfondo animato (parte solo nel tema Matrix)
     · setUiTheme()    — scaffold del theme switcher (cookie + live-flip)
   Il redraw specifico di ogni pagina (mermaid, canvas del grafo, …) NON vive
   qui: si aggancia definendo `window.onThemeChange`, invocato da setUiTheme
   dopo il cambio di tema. Se non definito, il flip aggiorna solo le CSS vars.
   ═══════════════════════════════════════════════════════════════════════════ */

/** Legge una CSS variable dal :root corrente (risolve già il tema attivo via data-theme). */
function themeVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/* ──────────── MATRIX RAIN BACKGROUND (parte solo se il tema attivo è "matrix") ──────────── */
let matrixRainTimer = null;
function startMatrixRain() {
  if (matrixRainTimer) return;
  const canvas = document.getElementById('matrix-rain');
  const ctx = canvas.getContext('2d');
  const glyphs = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789';
  let w, h, cols, drops;
  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    cols = Math.floor(w / 16);
    drops = new Array(cols).fill(0).map(() => Math.random() * -50);
  }
  resize();
  window.addEventListener('resize', resize);
  function draw() {
    ctx.fillStyle = 'rgba(0,0,0,0.06)';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#00ff41';
    ctx.font = '14px monospace';
    for (let i = 0; i < drops.length; i++) {
      const glyph = glyphs[Math.floor(Math.random() * glyphs.length)];
      ctx.fillText(glyph, i * 16, drops[i] * 16);
      if (drops[i] * 16 > h && Math.random() > 0.975) drops[i] = 0;
      drops[i]++;
    }
  }
  matrixRainTimer = setInterval(draw, 50);
}
function stopMatrixRain() {
  if (matrixRainTimer) { clearInterval(matrixRainTimer); matrixRainTimer = null; }
}

/* ──────────── THEME SWITCHER (live-flip, niente reload) ──────────── */
function setUiTheme(value) {
  document.cookie = 'ui_theme=' + value + ';path=/;max-age=31536000';
  document.documentElement.dataset.theme = value;   // live-flip: niente reload
  if (value === 'matrix') startMatrixRain(); else stopMatrixRain();
  // Hook per il redraw specifico della pagina (canvas bitmap, mermaid, …).
  if (typeof window.onThemeChange === 'function') window.onThemeChange(value);
}
document.addEventListener('DOMContentLoaded', function () {
  // Il server ha già impostato data-theme sul primo paint (nessun flash) — questo
  // blocco serve solo a sincronizzare lo stato del <select id="theme-switcher">.
  var sel = document.getElementById('theme-switcher');
  if (sel) sel.value = document.documentElement.dataset.theme || 'matrix';
  if (document.documentElement.dataset.theme === 'matrix') startMatrixRain();
});
