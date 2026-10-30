/* ═══════════════════════════════════════════════════════════════════════════
   i18n.js — localizzazione IT/EN della console.
   Preferenza in localStorage (vibecraft-lang), default italiano (UI attuale).
   Cataloghi in /static/i18n/messages.js (window.VIBECRAFT_MESSAGES).
   Markup: data-i18n, data-i18n-html, data-i18n-placeholder, data-i18n-title,
   data-i18n-aria-label, data-i18n-aria-labelledby (non usato), data-i18n-value.
   Parametri: t('key', { name: 'x' }) sostituisce {name} nel messaggio.
   ═══════════════════════════════════════════════════════════════════════════ */

const LANG_KEY = 'vibecraft-lang';
const SUPPORTED_LANGS = ['it', 'en'];

function detectInitialLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
  } catch (_) { /* storage non disponibile */ }
  // Default: italiano — è la lingua attuale dell'interfaccia.
  return 'it';
}

let _lang = detectInitialLang();

function currentLang() { return _lang; }

function t(key, params) {
  const catalog = (window.VIBECRAFT_MESSAGES && window.VIBECRAFT_MESSAGES[_lang]) || {};
  const fallback = (window.VIBECRAFT_MESSAGES && window.VIBECRAFT_MESSAGES.it) || {};
  let msg = catalog[key] ?? fallback[key] ?? key;
  if (params && typeof params === 'object') {
    for (const [k, v] of Object.entries(params)) {
      msg = String(msg).split('{' + k + '}').join(String(v));
    }
  }
  return msg;
}

function applyI18n(root) {
  const scope = root || document;
  scope.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (!key) return;
    el.textContent = t(key);
  });
  scope.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.getAttribute('data-i18n-html');
    if (!key) return;
    el.innerHTML = t(key);
  });
  scope.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.setAttribute('placeholder', t(key));
  });
  scope.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    if (key) el.setAttribute('title', t(key));
  });
  scope.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
    const key = el.getAttribute('data-i18n-aria-label');
    if (key) el.setAttribute('aria-label', t(key));
  });
  scope.querySelectorAll('[data-i18n-value]').forEach(el => {
    const key = el.getAttribute('data-i18n-value');
    if (key) el.value = t(key);
  });
  document.documentElement.lang = _lang;
  const sel = document.getElementById('lang-switcher');
  if (sel) sel.value = _lang;
  if (typeof syncMotionToggle === 'function') syncMotionToggle();
  if (typeof window.onLangChange === 'function') window.onLangChange(_lang);
}

function setUiLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'it';
  _lang = lang;
  try { localStorage.setItem(LANG_KEY, lang); } catch (_) { /* storage non disponibile */ }
  applyI18n(document);
  // Allinea i frame della shell (stessa origine) senza reload.
  try {
    const pages = document.getElementById('workspace-pages');
    if (pages) {
      pages.querySelectorAll('iframe').forEach(frame => {
        try {
          if (frame.contentWindow && typeof frame.contentWindow.applyI18n === 'function') {
            frame.contentWindow._lang = lang;
            frame.contentWindow.applyI18n(frame.contentDocument);
          }
        } catch (_) { /* frame non pronto */ }
      });
    }
  } catch (_) { /* shell assente */ }
}

window.addEventListener('storage', event => {
  if (event.key !== LANG_KEY) return;
  const next = event.newValue && SUPPORTED_LANGS.includes(event.newValue) ? event.newValue : 'it';
  if (next === _lang) return;
  _lang = next;
  applyI18n(document);
});

function initLangSwitcher() {
  const host = document.getElementById('workspace-theme');
  if (!host || document.getElementById('lang-switcher')) return;
  const label = document.createElement('label');
  label.className = 'workspace-sr-only';
  label.htmlFor = 'lang-switcher';
  label.setAttribute('data-i18n', 'shell.lang');
  label.textContent = t('shell.lang');
  const sel = document.createElement('select');
  sel.id = 'lang-switcher';
  sel.setAttribute('data-change', 'setUiLang');
  sel.innerHTML = '<option value="it">IT</option><option value="en">EN</option>';
  sel.value = _lang;
  // Prima del tema: lingua, tema, rain.
  const theme = document.getElementById('theme-switcher');
  if (theme) {
    const themeLabel = host.querySelector('label[for="theme-switcher"]');
    if (themeLabel) host.insertBefore(label, themeLabel);
    else host.insertBefore(label, theme);
    host.insertBefore(sel, themeLabel || theme);
  } else {
    host.append(label, sel);
  }
}

// Espone le API usate dalle pagine e da registerActions.
window.t = t;
window.currentLang = currentLang;
window.setUiLang = setUiLang;
window.applyI18n = applyI18n;
Object.defineProperty(window, '_lang', {
  get() { return _lang; },
  set(v) { _lang = v; },
});

document.documentElement.lang = _lang;

document.addEventListener('DOMContentLoaded', function () {
  initLangSwitcher();
  applyI18n(document);
});

if (typeof registerActions === 'function') {
  registerActions({ setUiLang: el => setUiLang(el.value) });
} else {
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof registerActions === 'function') {
      registerActions({ setUiLang: el => setUiLang(el.value) });
    }
  });
}
