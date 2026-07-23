/* ═══════════════════════════════════════════════════════════════════════════
   shared.js — codice IDENTICO fra i template *.unified.html, servito da
   /static/ (StaticFiles).

     · escapeHtml()    — escape unico per tutta l'app (era duplicato 3 volte,
                         con 3 implementazioni divergenti)
     · themeVar()      — lettura di una CSS variable del tema attivo, con cache
     · matrix rain     — sfondo animato (rAF, rispetta prefers-reduced-motion)
     · setUiTheme()    — theme switcher (cookie + live-flip, nessun reload)
     · initNavigation()— evidenzia la pagina corrente nella nav

   Il redraw specifico di ogni pagina (mermaid, canvas del grafo, …) NON vive
   qui: si aggancia definendo `window.onThemeChange`, invocato da setUiTheme
   dopo il cambio di tema. Se non definito, il flip aggiorna solo le CSS vars.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ──────────── ESCAPE HTML ────────────
   Unica implementazione condivisa. Copre anche l'apice singolo, così è sicura
   anche per l'interpolazione dentro attributi quotati con '. */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ──────────── THEME VAR (con cache) ────────────
   getComputedStyle forza la risoluzione degli stili: senza cache questa funzione
   veniva chiamata 5 volte per OGNI evento hoverNode del grafo e 13 volte per
   render del pannello JSON. La cache si azzera da sola quando cambia data-theme,
   quindi il live-flip continua a funzionare. */
let _themeVarCache = {};
let _themeVarFor = null;
function themeVar(name, fallback) {
  const theme = document.documentElement.dataset.theme || '';
  if (theme !== _themeVarFor) { _themeVarCache = {}; _themeVarFor = theme; }
  if (!(name in _themeVarCache)) {
    _themeVarCache[name] = getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
  }
  return _themeVarCache[name] || fallback;
}

/* ──────────── MATRIX RAIN ────────────
   Parte solo se il tema attivo è "matrix" E l'utente non ha chiesto meno
   movimento. Usa requestAnimationFrame invece di setInterval: si ferma da solo
   quando la tab è in background, cosa che setInterval non fa.
   Il listener di resize viene RIMOSSO in stop(): la versione precedente lo
   registrava a ogni start senza mai toglierlo, quindi ogni ciclo
   matrix → classic → matrix lasciava un listener orfano attivo per sempre. */
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

let rainRaf = null;
let rainResizeHandler = null;

function startMatrixRain() {
  if (rainRaf || prefersReducedMotion.matches) return;
  const canvas = document.getElementById('matrix-rain');
  if (!canvas) return;
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
  rainResizeHandler = resize;
  window.addEventListener('resize', rainResizeHandler);

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

  let last = 0;
  (function loop(now) {
    if (now - last >= 50) { draw(); last = now; }   // ~20fps, come il vecchio setInterval
    rainRaf = requestAnimationFrame(loop);
  })(0);
}

function stopMatrixRain() {
  if (rainRaf) { cancelAnimationFrame(rainRaf); rainRaf = null; }
  if (rainResizeHandler) {
    window.removeEventListener('resize', rainResizeHandler);
    rainResizeHandler = null;
  }
}

/* Se l'utente cambia la preferenza di movimento a runtime, adeguati subito:
   il tema Matrix resta selezionato, cade solo l'animazione. */
prefersReducedMotion.addEventListener('change', () => {
  if (prefersReducedMotion.matches) stopMatrixRain();
  else if (document.documentElement.dataset.theme === 'matrix') startMatrixRain();
});

/* ──────────── THEME SWITCHER (live-flip, niente reload) ──────────── */
function setUiTheme(value) {
  document.cookie = 'ui_theme=' + value + ';path=/;max-age=31536000';
  document.documentElement.dataset.theme = value;   // live-flip: niente reload
  if (value === 'matrix') startMatrixRain(); else stopMatrixRain();
  // Hook per il redraw specifico della pagina (canvas bitmap, mermaid, …).
  if (typeof window.onThemeChange === 'function') window.onThemeChange(value);
}

/* ──────────── NAVIGAZIONE: pagina corrente ────────────
   Ogni pagina aveva la propria nav scritta a mano, con ordine diverso e nessuna
   indicazione di dove ci si trovasse. Qui la pagina corrente viene marcata
   confrontando l'href con location.pathname: funziona su tutti e 6 i template
   senza modificarne il markup. `aria-current` copre anche gli screen reader,
   così lo stato non dipende dal solo colore. */
function initNavigation() {
  const links = document.querySelectorAll('header a[href], nav a[href], .app-nav a[href]');
  const here = location.pathname.replace(/\/+$/, '') || '/';
  links.forEach(a => {
    const href = (a.getAttribute('href') || '').replace(/\/+$/, '') || '/';
    if (href === here) {
      a.classList.add('is-current');
      a.setAttribute('aria-current', 'page');
    }
  });
}

/* ──────────── BOOTSTRAP ──────────── */
document.addEventListener('DOMContentLoaded', function () {
  // Il server ha già impostato data-theme sul primo paint (nessun flash) — questo
  // blocco serve solo a sincronizzare lo stato del <select id="theme-switcher">.
  const sel = document.getElementById('theme-switcher');
  if (sel) sel.value = document.documentElement.dataset.theme || 'matrix';
  if (document.documentElement.dataset.theme === 'matrix') startMatrixRain();
  initNavigation();
});
