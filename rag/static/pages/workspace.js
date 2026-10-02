/* ponytail: conserva al massimo le sei pagine in questa scheda; per riprendere
   dopo refresh/chiusura servirebbero job persistenti sul server. */
const workspacePages = new Map();
const workspaceRoutes = new Set(['/', '/pipeline', '/intake', '/analysis', '/eval', '/infografica']);
let workspaceNavigation = 0;
let workspaceTarget = location.href;

async function navigateWorkspace(target, push = true) {
  const url = new URL(target, location.origin);
  if (url.origin !== location.origin || !workspaceRoutes.has(url.pathname)) return;
  url.searchParams.delete('workspace');
  // Una sola istanza per sezione: query/hash non devono duplicare un agente attivo.
  const key = url.pathname;
  const navigation = ++workspaceNavigation;
  workspaceTarget = url.href;
  const status = document.getElementById('workspace-status');
  const message = document.getElementById('workspace-message');
  const retry = document.getElementById('workspace-retry');
  status.hidden = false;
  message.textContent = 'Caricamento…';
  retry.hidden = true;
  try {
    if (!workspacePages.has(key)) {
      const pageUrl = new URL(url);
      pageUrl.searchParams.set('workspace', '1');
      const loading = fetch(pageUrl.href).then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const frame = document.createElement('iframe');
        frame.title = `VibeCraft · ${key === '/' ? 'Console' : key.slice(1)}`;
        frame.dataset.workspacePage = key;
        frame.hidden = true;
        // srcdoc eredita origine e CSP della shell: nessuna eccezione all'anti-framing.
        frame.srcdoc = await response.text();
        await new Promise(resolve => {
          frame.addEventListener('load', resolve, { once: true });
          document.getElementById('workspace-pages').appendChild(frame);
        });
        return frame;
      }).catch(error => { workspacePages.delete(key); throw error; });
      workspacePages.set(key, loading);
    }
    const frame = await workspacePages.get(key);
    if (navigation !== workspaceNavigation) return;
    document.querySelectorAll('#workspace-pages iframe').forEach(page => { page.hidden = page !== frame; });
    const theme = document.documentElement.dataset.theme;
    if (frame.contentDocument.documentElement.dataset.theme !== theme) frame.contentWindow.setUiTheme(theme);
    document.title = frame.contentDocument.title;
    if (push && url.href !== location.href) history.pushState(null, '', url);
    status.hidden = true;
    frame.focus();
    if (url.hash) frame.contentDocument.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView();
  } catch (error) {
    if (navigation !== workspaceNavigation) return;
    message.textContent = `Impossibile aprire la pagina: ${error.message}`;
    retry.hidden = false;
  }
}

window.navigateWorkspace = navigateWorkspace;
window.workspaceRoutes = workspaceRoutes;
registerActions({ retryNavigation: () => navigateWorkspace(workspaceTarget) });
window.addEventListener('popstate', () => navigateWorkspace(location.href, false));
navigateWorkspace(location.href, false);
