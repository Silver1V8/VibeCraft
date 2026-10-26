/* ponytail: pagine residenti per due progetti in questa scheda; refresh/chiusura
   richiedono storico persistente per ripristinare conversazioni non salvate. */
const workspacePages = new Map();
const workspaceProjects = new Map();
const workspaceRoutes = new Set(['/', '/pipeline', '/intake', '/analysis', '/eval', '/infografica']);
let workspaceNavigation = 0;
let workspaceTarget = location.href;
let currentProject = selectedProjectId();
let projects = [];
let projectReadOnly = true;
let projectDialogMode = 'new';
const projectIndexJobs = new Set();
const projectIndexRepairs = new Set();
const RECENT_PROJECTS_STORAGE = 'vibecraft-recent-projects';
let recentProjects = [];
try {
  const saved = JSON.parse(localStorage.getItem(RECENT_PROJECTS_STORAGE) || '[]');
  if (Array.isArray(saved)) recentProjects = saved.filter(item => item && typeof item.id === 'string' && Number.isFinite(item.openedAt)).slice(0, 20);
} catch (_) { /* Storico facoltativo: storage privato o non valido. */ }

function dateLocale() {
  return currentLang() === 'en' ? 'en-GB' : 'it-IT';
}
function isProjectWelcome(url = new URL(location.href)) {
  return url.pathname === '/' && !url.searchParams.get('project');
}
function setWelcomeView(visible) {
  document.getElementById('project-welcome').hidden = !visible;
  document.getElementById('workspace-pages').hidden = visible;
  document.getElementById('project-context').hidden = visible;
  document.getElementById('project-toolbar').hidden = visible;
  document.getElementById('workspace-nav').hidden = visible;
}
/* La pagina corrente nella nav della shell: aria-current per gli screen reader,
   href con ?project= perché "apri in nuova scheda" porti allo stesso progetto. */
function markWorkspaceNav(url) {
  for (const link of document.querySelectorAll('#workspace-nav a')) {
    const target = new URL(link.getAttribute('href'), location.origin);
    target.search = '';
    target.searchParams.set('project', url.searchParams.get('project'));
    link.href = target.pathname + target.search;
    const current = target.pathname === url.pathname;
    link.classList.toggle('is-current', current);
    if (current) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
}
function syncNavShortcutTitles() {
  workspaceNavLinks.forEach((link, i) => {
    link.title = t('workspace.navShortcut', { label: link.textContent.trim(), n: i + 1 });
  });
}
function showProjectWelcome(push = true) {
  ++workspaceNavigation; // Una navigazione in attesa non deve riaprire un frame sopra la home.
  setWelcomeView(true);
  workspaceLoading(false);
  document.getElementById('theme-switcher').value = document.documentElement.dataset.theme;
  document.getElementById('workspace-status').hidden = true;
  document.getElementById('project-search').value = '';
  renderProjectList();
  if (projects.some(project => project.stale_pending)) completeProjectStatus();
  document.title = t('workspace.docTitle');
  const url = new URL('/', location.origin);
  if (push && url.href !== location.href) history.pushState(null, '', url);
  if (push) document.getElementById('project-welcome').focus({ preventScroll: true });
}
function setIndexBadge(element, project) {
  const labels = {
    not_indexed: t('workspace.indexNotIndexed'),
    ready: t('workspace.indexReady'),
    indexing: t('workspace.indexIndexing'),
    error: t('workspace.indexError'),
  };
  const checking = project?.index_status === 'ready' && project.stale_pending;
  const suffix = checking ? t('workspace.indexChecking') : project?.stale ? t('workspace.indexStale') : '';
  element.textContent = project ? `${labels[project.index_status] || t('workspace.indexUnknown')}${suffix}` : '';
  element.dataset.state = checking ? 'checking'
    : project?.index_status === 'ready' && project.stale ? 'stale' : project?.index_status || '';
}
function renderProjectList() {
  const filter = document.getElementById('project-search').value.trim().toLocaleLowerCase();
  const opened = new Map(recentProjects.map(item => [item.id, item.openedAt]));
  const matching = [...projects].filter(project => project.name.toLocaleLowerCase().includes(filter))
    .sort((a, b) => (opened.get(b.id) || 0) - (opened.get(a.id) || 0));
  const list = document.getElementById('project-list');
  list.replaceChildren();
  for (const project of matching) {
    const card = document.getElementById('project-card-template').content.firstElementChild.cloneNode(true);
    card.dataset.arg = project.id;
    card.querySelector('.project-card-name').textContent = project.name;
    const path = card.querySelector('.project-card-path');
    // Le ultime due cartelle ("…/projects/SGD-FE") bastano a riconoscerlo; il percorso
    // completo, lungo e uguale per tutti fino a projects\, resta nel tooltip.
    const parts = (project.root || '').split(/[\\/]+/).filter(Boolean);
    path.textContent = parts.length > 2 ? '…/' + parts.slice(-2).join('/') : project.root
      || (project.legacy ? t('workspace.legacyRoot') : t('workspace.defaultRoot'));
    path.title = project.root || path.textContent;
    // Cosa contiene e quando l'hai usato: "Pronto da aprire" su ogni scheda non distingueva nulla.
    const lastOpened = opened.get(project.id);
    const when = value => new Date(value).toLocaleString(dateLocale(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    card.querySelector('.project-card-meta').textContent = [
      Number.isInteger(project.documents) && t(project.documents === 1 ? 'workspace.documentOne' : 'workspace.documentMany', { n: project.documents }),
      Number.isInteger(project.code_files) && project.code_files > 0 && t('workspace.codeFiles', { n: project.code_files }),
      lastOpened && t('workspace.openedAt', { when: when(lastOpened) }),
    ].filter(Boolean).join(' · ');
    setIndexBadge(card.querySelector('.project-card-status'), project);
    list.appendChild(card);
  }
  document.getElementById('project-count').textContent = t(
    matching.length === 1 ? 'workspace.projectCountOne' : 'workspace.projectCountMany',
    { n: matching.length },
  );
  const empty = document.getElementById('project-list-empty');
  empty.hidden = matching.length > 0;
  empty.textContent = filter ? t('workspace.emptyFiltered') : t('workspace.emptyNone');
}

/* Scheletro al posto della pagina mentre il frame carica: la sagoma dell'interfaccia
   compare subito invece di uno schermo vuoto con un messaggio in basso. */
function workspaceLoading(visible) {
  document.getElementById('workspace-skeleton').hidden = !visible;
  // L'area pagine cede lo spazio allo scheletro; sulla home resta nascosta comunque.
  document.getElementById('workspace-pages').hidden = visible || !document.getElementById('project-welcome').hidden;
  if (visible) document.getElementById('workspace-status').hidden = true;
}
function workspaceMessage(text, retry = false) {
  workspaceLoading(false);
  document.getElementById('workspace-status').hidden = false;
  document.getElementById('workspace-message').textContent = text;
  document.getElementById('workspace-retry').hidden = !retry;
}
function projectError(data, response) {
  return data.detail?.message || (typeof data.detail === 'string' ? data.detail : '') || `HTTP ${response.status}`;
}
function renderProjects() {
  const select = document.getElementById('project-select');
  select.replaceChildren();
  if (!projects.length || !projects.some(project => project.id === currentProject)) {
    const option = document.createElement('option');
    option.value = currentProject || '';
    option.textContent = currentProject ? t('workspace.projectUnavailable') : t('workspace.selectProject');
    select.appendChild(option);
  }
  projects.forEach(project => {
    const option = document.createElement('option');
    option.value = project.id;
    option.textContent = project.name;
    select.appendChild(option);
  });
  select.value = currentProject;
  select.disabled = !projects.length;
  document.getElementById('project-new').disabled = projectReadOnly;
  document.getElementById('project-open').disabled = projectReadOnly;
  document.getElementById('welcome-new').disabled = projectReadOnly;
  document.getElementById('welcome-open').disabled = projectReadOnly;
  document.getElementById('project-read-only').hidden = !projectReadOnly;
  renderIndexStatus(projects.find(project => project.id === currentProject));
  renderProjectList();
}
function renderIndexStatus(project) {
  const busy = project && (projectIndexJobs.has(project.id) || project.index_status === 'indexing');
  const repair = project && projectIndexRepairs.has(project.id);
  const badge = document.getElementById('project-index-status');
  setIndexBadge(badge, busy ? { ...project, index_status: 'indexing', stale: false } : project);
  if (repair && !busy) { badge.textContent = t('workspace.indexRebuild'); badge.dataset.state = 'error'; }
  const button = document.getElementById('project-index-update');
  // Durante la verifica lo stato non è noto: niente pulsante che appare e poi sparisce.
  button.hidden = projectReadOnly || !project || (!busy && !repair && project.index_status === 'ready'
    && (project.stale === false || project.stale_pending));
  button.disabled = !!busy;
  button.textContent = busy ? t('workspace.indexingBusy') : repair ? t('workspace.rebuildIndex')
    : project?.index_status === 'not_indexed' ? t('workspace.createIndex') : t('workspace.updateIndex');
}
window.reportProjectIndexIssue = id => {
  projectIndexRepairs.add(id);
  if (id === currentProject) renderIndexStatus(projects.find(project => project.id === id));
};
async function updateProjectIndex() {
  const id = currentProject, project = projects.find(item => item.id === id);
  if (projectReadOnly || !project || project.index_status === 'indexing' || projectIndexJobs.has(id)) return;
  const headers = { 'Content-Type': 'application/json', 'X-VibeCraft-Project': id };
  projectIndexJobs.add(id);
  renderIndexStatus(project);
  try {
    const response = await fetch('/api/index/reindex', { method: 'POST', headers,
      body: JSON.stringify(project.index_status !== 'ready' || projectIndexRepairs.has(id) ? { full: true } : {}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(projectError(data, response));
    if (!data.job_id) throw new Error(t('workspace.reindexNoJob'));
    let notified = false;
    const tick = async () => {
      let job;
      try {
        const status = await fetch('/api/reindex/' + encodeURIComponent(data.job_id), { headers });
        const result = await status.json();
        if (!status.ok) {
          if (status.status === 404) {
            projectIndexJobs.delete(id);
            await refreshIndexStatus(id);
            toast(t('workspace.reindexToast', { name: project.name, message: projectError(result, status) }), 'warning');
            return;
          }
          throw new Error(projectError(result, status));
        }
        job = result;
      } catch (error) {
        if (!notified) toast(t('workspace.reindexRetryStatus', { name: project.name, message: error.message }), 'warning');
        notified = true;
        setTimeout(tick, 4000);
        return;
      }
      if (!['completed', 'completed_not_promoted', 'failed', 'interrupted'].includes(job.status)
          || (job.status === 'completed' && job.reload_status === 'pending')) {
        setTimeout(tick, 4000);
        return;
      }
      projectIndexJobs.delete(id);
      const ok = job.status === 'completed' && !job.reload_error && (!job.reload_status || job.reload_status === 'completed');
      if (ok) projectIndexRepairs.delete(id);
      await refreshIndexStatus(id);
      renderProjectList();
      const message = ok ? t('workspace.reindexUpdated') : job.reload_error || job.error
        || (job.status === 'completed_not_promoted' ? t('workspace.reindexNotPromoted')
          : job.status === 'completed' ? t('workspace.reindexNotLoaded') : t('workspace.reindexInterrupted'));
      toast(t('workspace.reindexToast', { name: project.name, message }), ok ? 'success' : 'warning');
      if (ok) {
        for (const page of workspacePages.values()) {
          if (page.project === id && page.frame) {
            page.frame.contentWindow.loadSemanticMap?.();
            page.frame.contentWindow.loadNodeList?.();
            page.frame.contentWindow.loadProjectStatus?.();
          }
        }
      }
    };
    await tick();
  } catch (error) {
    projectIndexJobs.delete(id);
    if (id === currentProject) renderIndexStatus(projects.find(item => item.id === id));
    toast(t('workspace.reindexToast', { name: project.name, message: error.message }), 'warning');
  }
}
/* Dipendenze esterne: senza questo la barra diceva "Indice pronto" con Qdrant spento,
   e lo si scopriva solo da un errore in pagina o in fondo all'Infografica. Le pagine
   ricevono l'elenco dei servizi spenti e bloccano i controlli con data-requires. */
function serviceImpact(name) {
  if (name === 'qdrant') return t('workspace.impactQdrant');
  if (name === 'ollama') return t('workspace.impactOllama');
  return '';
}
const SERVICE_NAMES = ['qdrant', 'ollama'];
let servicesDown = [];
async function refreshServiceStatus() {
  try {
    const response = await fetch('/api/health/deps');
    if (!response.ok) return;
    const deps = await response.json();
    servicesDown = SERVICE_NAMES.filter(name => deps[name] === false);
  } catch (_) { return; } /* server giù: lo segnalano già le richieste della pagina */
  renderServiceStatus();
}
function renderServiceStatus() {
  const badge = document.getElementById('service-status');
  const names = servicesDown.map(name => name[0].toUpperCase() + name.slice(1));
  badge.hidden = !names.length;
  if (!names.length) {
    badge.textContent = '';
    badge.title = '';
  } else if (names.length === 1) {
    badge.textContent = t('workspace.servicesDownOne', { name: names[0] });
    badge.title = serviceImpact(servicesDown[0]);
  } else {
    badge.textContent = t('workspace.servicesDownMany', { names: names.join(t('common.and')) });
    badge.title = servicesDown.map(name => serviceImpact(name)).join(' ');
  }
  for (const page of workspacePages.values()) page.frame?.contentWindow.applyServiceStatus?.(servicesDown);
}
async function refreshIndexStatus(id = currentProject) {
  if (!id) return;
  try {
    const response = await fetch('/api/projects/' + encodeURIComponent(id));
    if (!response.ok) throw new Error(projectError(await response.json(), response));
    const project = await response.json();
    const index = projects.findIndex(item => item.id === id);
    if (index >= 0) projects[index] = project;
    if (currentProject === id) renderIndexStatus(project);
  } catch (error) {
    if (currentProject === id) {
      document.getElementById('project-index-status').textContent = t('workspace.indexStatusError', { message: error.message });
    }
  }
}
function selectCurrentProject(id) {
  currentProject = id;
  try { sessionStorage.setItem(PROJECT_STORAGE, id); } catch (_) { /* tab privata */ }
  recentProjects = [{ id, openedAt: Date.now() }, ...recentProjects.filter(item => item.id !== id)].slice(0, 20);
  try { localStorage.setItem(RECENT_PROJECTS_STORAGE, JSON.stringify(recentProjects)); } catch (_) { /* storico facoltativo */ }
  document.getElementById('project-select').value = id;
  renderIndexStatus(projects.find(project => project.id === id));
}
function reserveProject(id) {
  if (workspaceProjects.has(id)) {
    workspaceProjects.delete(id);
    workspaceProjects.set(id, true);
    return;
  }
  if (workspaceProjects.size >= 2) {
    let evicted = false;
    for (const candidate of workspaceProjects.keys()) {
      const pages = [...workspacePages.values()].filter(page => page.project === candidate);
      if (pages.some(page => !page.frame || page.frame.contentWindow.workspaceIsBusy?.())) continue;
      pages.forEach(page => { page.frame.remove(); workspacePages.delete(page.key); });
      workspaceProjects.delete(candidate);
      evicted = true;
      break;
    }
    if (!evicted) throw new Error(t('workspace.twoProjectsBusy'));
  }
  workspaceProjects.set(id, true);
}

function pageLabel(pathname) {
  if (pathname === '/') return t('workspace.navConsole');
  if (pathname === '/intake') return t('workspace.navIntake');
  if (pathname === '/pipeline') return t('workspace.navPipeline');
  if (pathname === '/analysis') return t('workspace.navAnalysis');
  if (pathname === '/eval') return t('workspace.navEval');
  if (pathname === '/infografica') return t('workspace.navGuide');
  return pathname.slice(1);
}

async function navigateWorkspace(target, push = true) {
  const url = new URL(target, location.origin);
  if (url.origin !== location.origin || !workspaceRoutes.has(url.pathname)) return;
  url.searchParams.delete('workspace');
  // La root senza ID è sempre la schermata iniziale, anche con una selezione salvata.
  if (isProjectWelcome(url)) { showProjectWelcome(push); return; }
  const project = url.searchParams.get('project') || currentProject;
  if (!project) { workspaceMessage(t('workspace.noProjectSelected')); return; }
  if (!projects.some(item => item.id === project)) { workspaceMessage(t('workspace.projectNotAvailableMsg')); return; }
  url.searchParams.set('project', project);
  const key = project + ':' + url.pathname;
  const navigation = ++workspaceNavigation;
  workspaceTarget = url.href;
  setWelcomeView(false);
  // Un frame già in cache si mostra all'istante: lo scheletro serve solo al primo caricamento.
  if (!workspacePages.get(key)?.frame) workspaceLoading(true);
  try {
    reserveProject(project);
    if (!workspacePages.has(key)) {
      const pageUrl = new URL(url);
      pageUrl.searchParams.set('workspace', '1');
      const page = { key, project, frame: null };
      page.loading = fetch(pageUrl.href).then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const frame = document.createElement('iframe');
        frame.title = t('workspace.frameTitle', { page: pageLabel(url.pathname) });
        frame.dataset.workspacePage = url.pathname;
        frame.dataset.projectId = project;
        frame.hidden = true;
        // srcdoc eredita origine/CSP; l'identità è sul frame prima di shared.js.
        frame.srcdoc = await response.text();
        await new Promise(resolve => {
          frame.addEventListener('load', resolve, { once: true });
          document.getElementById('workspace-pages').appendChild(frame);
        });
        page.frame = frame;
        return frame;
      }).catch(error => { workspacePages.delete(key); throw error; });
      workspacePages.set(key, page);
    }
    const frame = await workspacePages.get(key).loading;
    if (navigation !== workspaceNavigation) return;
    selectCurrentProject(project);
    document.querySelectorAll('#workspace-pages iframe').forEach(page => { page.hidden = page !== frame; });
    const theme = document.documentElement.dataset.theme;
    if (frame.contentDocument.documentElement.dataset.theme !== theme) frame.contentWindow.setUiTheme(theme);
    document.title = frame.contentDocument.title;
    markWorkspaceNav(url);
    frame.contentWindow.applyServiceStatus?.(servicesDown);
    if (url.href !== location.href) {
      if (push) history.pushState(null, '', url);
      else history.replaceState(null, '', url);
    }
    workspaceLoading(false);
    document.getElementById('workspace-status').hidden = true;
    frame.focus();
    refreshIndexStatus(project);
    if (url.hash) frame.contentDocument.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView();
  } catch (error) {
    if (navigation !== workspaceNavigation) return;
    document.getElementById('project-select').value = currentProject;
    workspaceMessage(t('workspace.pageOpenFailed', { message: error.message }), true);
  }
}

function showProjectDialog(mode) {
  if (projectReadOnly) return;
  projectDialogMode = mode;
  const opening = mode === 'open';
  document.getElementById('project-dialog-title').textContent = opening ? t('workspace.dialogOpenTitle') : t('workspace.dialogNewTitle');
  document.getElementById('project-input-label').textContent = opening ? t('workspace.dialogOpenLabel') : t('workspace.dialogNewLabel');
  document.getElementById('project-input').value = '';
  document.getElementById('project-help').textContent = opening ? t('workspace.dialogOpenHelp') : t('workspace.dialogNewHelp');
  document.getElementById('project-submit').textContent = opening ? t('workspace.open') : t('workspace.create');
  const localBind = document.querySelector('meta[name="vibecraft-local-bind"]')?.content === 'true';
  document.getElementById('project-browse').hidden = !opening || !localBind;
  document.getElementById('project-error').textContent = '';
  document.getElementById('project-dialog').showModal();
  document.getElementById('project-input').focus();
}
function refreshOpenProjectDialog() {
  const dialog = document.getElementById('project-dialog');
  if (!dialog.open) return;
  const opening = projectDialogMode === 'open';
  document.getElementById('project-dialog-title').textContent = opening ? t('workspace.dialogOpenTitle') : t('workspace.dialogNewTitle');
  document.getElementById('project-input-label').textContent = opening ? t('workspace.dialogOpenLabel') : t('workspace.dialogNewLabel');
  document.getElementById('project-help').textContent = opening ? t('workspace.dialogOpenHelp') : t('workspace.dialogNewHelp');
  document.getElementById('project-submit').textContent = opening ? t('workspace.open') : t('workspace.create');
}
async function submitProject(event) {
  event.preventDefault();
  if (projectReadOnly) return;
  const value = document.getElementById('project-input').value.trim();
  if (!value) { document.getElementById('project-input').focus(); return; }
  const submit = document.getElementById('project-submit');
  submit.disabled = true;
  document.getElementById('project-error').textContent = '';
  try {
    const opening = projectDialogMode === 'open';
    const response = await fetch(opening ? '/api/projects/register' : '/api/projects', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opening ? { root: value } : { name: value }),
    });
    const project = await response.json();
    if (!response.ok) throw new Error(projectError(project, response));
    const existing = projects.findIndex(item => item.id === project.id);
    if (existing >= 0) projects[existing] = project; else projects.push(project);
    renderProjects();
    document.getElementById('project-dialog').close();
    const url = new URL(location.href);
    url.searchParams.set('project', project.id);
    await navigateWorkspace(url.href);
  } catch (error) { document.getElementById('project-error').textContent = error.message; }
  finally { submit.disabled = false; }
}
async function browseExistingProject() {
  const button = document.getElementById('project-browse');
  button.disabled = true;
  try {
    const response = await fetch('/api/intake/project/browse-path', { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(projectError(data, response));
    if (data.path) document.getElementById('project-input').value = data.path;
  } catch (error) { document.getElementById('project-error').textContent = error.message; }
  finally { button.disabled = false; document.getElementById('project-input').focus(); }
}
async function initializeWorkspace() {
  const welcome = isProjectWelcome();
  setWelcomeView(welcome);
  if (!welcome) workspaceLoading(true);
  try {
    // Prima l'elenco senza lo stato "da aggiornare" (secondi su progetti grandi): la pagina
    // parte subito, lo stato completo arriva dopo da completeProjectStatus.
    const response = await fetch('/api/projects?stale=0');
    const data = await response.json();
    if (!response.ok) throw new Error(projectError(data, response));
    projects = data.projects;
    projectReadOnly = data.read_only;
    // Compatibilità soltanto legacy; nessun fallback al primo progetto della lista.
    if (!welcome && !currentProject && projects.some(project => project.id === 'legacy')) currentProject = 'legacy';
    renderProjects();
    // Dentro una pagina basta refreshIndexStatus sul progetto attivo (lo lancia
    // navigateWorkspace); lo stato di tutti lo chiede showProjectWelcome.
    await navigateWorkspace(location.href, false);
  } catch (error) { workspaceMessage(t('workspace.projectsLoadFailed', { message: error.message }), true); }
}
let projectStatusRequest = null;
function completeProjectStatus() {
  projectStatusRequest ??= fetchProjectStatus().finally(() => { projectStatusRequest = null; });
  return projectStatusRequest;
}
async function fetchProjectStatus() {
  try {
    const response = await fetch('/api/projects');
    if (!response.ok) return;
    const fresh = new Map((await response.json()).projects.map(project => [project.id, project]));
    // Sostituisce solo i progetti ancora in verifica: un refreshIndexStatus arrivato
    // nel frattempo ha già un dato più recente.
    projects = projects.map(project => project.stale_pending && fresh.has(project.id) ? fresh.get(project.id) : project);
    renderIndexStatus(projects.find(project => project.id === currentProject));
    renderProjectList();
  } catch (_) { /* resta "verifica…": il refresh periodico del progetto attivo lo completa */ }
}

window.navigateWorkspace = navigateWorkspace;
window.workspaceRoutes = workspaceRoutes;
window.onLangChange = () => {
  // applyI18n ha già aggiornato il markup statico; qui il testo generato in JS.
  syncNavShortcutTitles();
  renderProjects();
  renderServiceStatus();
  refreshOpenProjectDialog();
  if (isProjectWelcome()) document.title = t('workspace.docTitle');
  for (const page of workspacePages.values()) {
    if (!page.frame) continue;
    const path = page.frame.dataset.workspacePage || '/';
    page.frame.title = t('workspace.frameTitle', { page: pageLabel(path) });
  }
};
registerActions({
  retryNavigation: () => isProjectWelcome() || !projects.length ? initializeWorkspace() : navigateWorkspace(workspaceTarget),
  showProjects: () => showProjectWelcome(), filterProjects: renderProjectList,
  openRecentProject: el => {
    const url = new URL('/', location.origin);
    url.searchParams.set('project', el.dataset.arg);
    return navigateWorkspace(url.href);
  },
  selectProject: el => { const url = new URL(location.href); url.searchParams.set('project', el.value); return navigateWorkspace(url.href); },
  newProject: () => showProjectDialog('new'), openProject: () => showProjectDialog('open'),
  cancelProject: () => document.getElementById('project-dialog').close(), browseExistingProject,
  updateProjectIndex,
});
document.getElementById('project-form').addEventListener('submit', submitProject);
document.getElementById('workspace-nav').addEventListener('click', event => {
  const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
  // Ctrl/Cmd/Maiusc e il tasto centrale restano al browser: nuova scheda o finestra.
  if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigateWorkspace(link.href);
});
window.addEventListener('popstate', () => navigateWorkspace(location.href, false));
/* Alt+1…6 apre le sezioni nell'ordine della nav. Solo le cifre della riga superiore
   (event.code DigitN): su Windows Alt+tastierino inserisce caratteri; AltGr è Ctrl+Alt e
   resta escluso. Le pagine nei frame inoltrano i tasti qui (initNavigation in shared.js). */
const workspaceNavLinks = [...document.querySelectorAll('#workspace-nav a')];
workspaceNavLinks.forEach((link, i) => {
  link.setAttribute('aria-keyshortcuts', `Alt+${i + 1}`);
  link.title = t('workspace.navShortcut', { label: link.textContent.trim(), n: i + 1 });
});
function workspaceShortcut(event) {
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const match = /^Digit([1-9])$/.exec(event.code);
  const link = match && workspaceNavLinks[Number(match[1]) - 1];
  if (!link || document.getElementById('workspace-nav').hidden) return;
  event.preventDefault();
  navigateWorkspace(link.href);
}
window.workspaceShortcut = workspaceShortcut;
document.addEventListener('keydown', workspaceShortcut);
window.onThemeChange = value => {
  for (const page of workspacePages.values()) {
    if (page.frame && !page.frame.hidden) page.frame.contentWindow.setUiTheme(value);
  }
};
setInterval(() => { if (document.getElementById('project-welcome').hidden) refreshIndexStatus(); }, 15000);
setInterval(() => { if (document.getElementById('project-welcome').hidden) refreshServiceStatus(); }, 30000);
initializeWorkspace();
refreshServiceStatus();
