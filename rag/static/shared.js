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

/* ──────────── PREFERENZA DI MOVIMENTO ────────────
   Tre stati, persistiti: 'auto' (segue il sistema operativo), 'on' e 'off'.
   Serve un override esplicito perché prefers-reduced-motion da solo è troppo
   grezzo: chi disattiva le animazioni di Windows perde il rain senza avere modo
   di riattivarlo, e il rain è l'identità del tema Matrix, non una decorazione
   accessoria. Il default resta il rispetto del sistema. */
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const MOTION_KEY = 'vibecraft-motion';

function motionPref() {
  try { return localStorage.getItem(MOTION_KEY) || 'auto'; } catch (e) { return 'auto'; }
}
function motionEnabled() {
  const p = motionPref();
  if (p === 'on')  return true;
  if (p === 'off') return false;
  return !prefersReducedMotion.matches;
}
/* Riporta la preferenza sul DOM: serve al CSS, che da solo non può sapere di un
   override memorizzato in localStorage. */
function applyMotionAttr() {
  const p = motionPref();
  if (p === 'auto') delete document.documentElement.dataset.motion;
  else document.documentElement.dataset.motion = p;
}
function setMotion(pref) {
  try { localStorage.setItem(MOTION_KEY, pref); } catch (e) { /* storage non disponibile */ }
  applyMotionAttr();
  syncMotionToggle();
  if (document.documentElement.dataset.theme === 'matrix' && motionEnabled()) startMatrixRain();
  else stopMatrixRain();
}

/* Applicato subito, non a DOMContentLoaded: shared.js è caricato in <head> in
   modo sincrono, quindi l'attributo è sul posto già al primo paint e le
   transizioni non fanno in tempo a partire con la preferenza sbagliata. */
applyMotionAttr();

/* ──────────── MATRIX RAIN ────────────
   Parte solo se il tema attivo è "matrix" E il movimento è consentito. Usa
   requestAnimationFrame invece di setInterval: si ferma da solo quando la tab è
   in background, cosa che setInterval non fa.
   Il listener di resize viene RIMOSSO in stop(): la versione precedente lo
   registrava a ogni start senza mai toglierlo, quindi ogni ciclo
   matrix → classic → matrix lasciava un listener orfano attivo per sempre. */
let rainRaf = null;
let rainResizeHandler = null;

function startMatrixRain() {
  if (rainRaf || !motionEnabled()) return;
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

/* Se cambia la preferenza di sistema a runtime, adeguati — ma solo in 'auto':
   una scelta esplicita dell'utente non va scavalcata dal sistema operativo. */
prefersReducedMotion.addEventListener('change', () => {
  if (motionPref() !== 'auto') return;
  syncMotionToggle();
  if (motionEnabled() && document.documentElement.dataset.theme === 'matrix') startMatrixRain();
  else stopMatrixRain();
});

/* ──────────── TOGGLE DEL MOVIMENTO ────────────
   Il comando viene iniettato accanto al selettore del tema, così compare su
   tutte e 6 le pagine senza doverne toccare il markup. È visibile solo nel tema
   Matrix: il rain non esiste in Classico e un interruttore che non fa nulla
   confonde. */
function syncMotionToggle() {
  const btn = document.getElementById('motion-toggle');
  if (!btn) return;
  const on = motionEnabled();
  btn.textContent = on ? '🌧 Rain on' : '🌧 Rain off';
  btn.setAttribute('aria-pressed', String(on));
  btn.title = on
    ? 'Disattiva le animazioni di sfondo (rain)'
    : 'Attiva le animazioni di sfondo (rain)';
  btn.hidden = document.documentElement.dataset.theme !== 'matrix';
}

function initMotionToggle() {
  const sel = document.getElementById('theme-switcher');
  if (!sel || document.getElementById('motion-toggle')) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'motion-toggle';
  btn.className = 'motion-toggle';
  btn.addEventListener('click', () => setMotion(motionEnabled() ? 'off' : 'on'));
  sel.insertAdjacentElement('afterend', btn);
  syncMotionToggle();
}

/* ──────────── THEME SWITCHER (live-flip, niente reload) ──────────── */
function setUiTheme(value) {
  document.cookie = 'ui_theme=' + value + ';path=/;max-age=31536000';
  document.documentElement.dataset.theme = value;   // live-flip: niente reload
  if (value === 'matrix') startMatrixRain(); else stopMatrixRain();
  syncMotionToggle();   // il toggle del rain esiste solo nel tema Matrix
  // Hook per il redraw specifico della pagina (canvas bitmap, mermaid, …).
  if (typeof window.onThemeChange === 'function') window.onThemeChange(value);
}

/* ──────────── TOAST ────────────
   Sostituisce alert(): un dialogo nativo di sistema è bloccante, non stilizzabile
   e spezza completamente l'identità del tema — comparivano finestre di Windows
   sopra la console verde. Qui il messaggio resta nel linguaggio dell'app e non
   interrompe il flusso. Gli errori non spariscono da soli: vanno chiusi, così
   non si perde la causa di un fallimento mentre si guarda altrove. */
function toast(message, level) {
  level = level || 'info';
  let host = document.getElementById('toast-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toast-host';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
  }
  const el = document.createElement('div');
  el.className = 'toast toast-' + level;
  const icon = { info: 'ℹ', success: '✓', warning: '⚠', error: '✕' }[level] || 'ℹ';
  // textContent, non innerHTML: i messaggi contengono spesso testo dal server.
  const ico = document.createElement('span');
  ico.className = 'toast-icon';
  ico.textContent = icon;
  const txt = document.createElement('span');
  txt.textContent = message;
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Chiudi la notifica');
  close.textContent = '×';
  close.addEventListener('click', () => el.remove());
  el.append(ico, txt, close);
  host.appendChild(el);
  if (level !== 'error') setTimeout(() => el.remove(), 5000);
  return el;
}

/* ──────────── CONFIRM DIALOG ────────────
   Sostituisce confirm(): un dialogo nativo di sistema espone l'origin
   ("127.0.0.1:8000 dice") ed è bloccante e non stilizzabile, esattamente come
   alert() prima del toast. Ritorna una Promise<boolean> così le chiamate
   restano un semplice `if (!await confirmDialog(...)) return;`.
   opts.danger marca l'azione come distruttiva (bordo/icona rossi, bottone
   btn-danger invece di btn-primary) — usato per operazioni non reversibili
   dall'interfaccia come l'archiviazione. */
function confirmDialog(message, opts) {
  opts = opts || {};
  const title = opts.title || 'Conferma azione';
  const confirmText = opts.confirmText || 'Conferma';
  const cancelText = opts.cancelText || 'Annulla';
  const danger = !!opts.danger;

  return new Promise(resolve => {
    let host = document.getElementById('confirm-host');
    if (host) host.remove();  // una conferma alla volta
    host = document.createElement('div');
    host.id = 'confirm-host';
    host.setAttribute('role', 'alertdialog');
    host.setAttribute('aria-modal', 'true');

    const backdrop = document.createElement('div');
    backdrop.className = 'confirm-backdrop';

    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog' + (danger ? ' is-danger' : '');

    const h = document.createElement('h2');
    h.className = 'confirm-title';
    const icon = document.createElement('span');
    icon.className = 'confirm-icon';
    icon.textContent = danger ? '⚠' : 'ℹ';
    const titleText = document.createElement('span');
    titleText.textContent = title;
    h.append(icon, titleText);

    const p = document.createElement('p');
    p.className = 'confirm-message';
    p.textContent = message;  // textContent: i messaggi includono spesso nomi feature dall'utente

    const actions = document.createElement('div');
    actions.className = 'confirm-actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = cancelText;
    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
    okBtn.textContent = confirmText;

    function settle(result) {
      host.remove();
      document.removeEventListener('keydown', onKeydown);
      resolve(result);
    }
    function onKeydown(e) {
      if (e.key === 'Escape') settle(false);
    }
    cancelBtn.addEventListener('click', () => settle(false));
    okBtn.addEventListener('click', () => settle(true));
    backdrop.addEventListener('click', () => settle(false));
    document.addEventListener('keydown', onKeydown);

    actions.append(cancelBtn, okBtn);
    dialog.append(h, p, actions);
    host.append(backdrop, dialog);
    document.body.appendChild(host);
    okBtn.focus();
  });
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
  applyMotionAttr();
  initMotionToggle();
  if (document.documentElement.dataset.theme === 'matrix') startMatrixRain();
  initNavigation();
});
