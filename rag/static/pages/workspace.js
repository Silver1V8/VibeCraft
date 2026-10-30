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
let renameTargetId = '';
let deleteTargetId = '';
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
  (visible ? document.getElementById('workspace-settings-slot') : document.getElementById('workspace-nav'))
    .append(document.getElementById('settings-open'));
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
function projectMatchesFilter(project, filter) {
  if (!filter) return true;
  return project.name.toLocaleLowerCase().includes(filter)
    || String(project.id).toLocaleLowerCase().includes(filter);
}
/* Radici gestite condividono lo stesso genitore (PROJECTS_DIR); le esterne no.
   Senza flag `managed` in list, il genitore più frequente tra root/id allineati
   è la stima usata solo per il testo del dialogo — la DELETE omette `mode`. */
function managedProjectsDirGuess() {
  const counts = new Map();
  for (const project of projects) {
    if (!project.root) continue;
    const parts = String(project.root).split(/[\\/]+/).filter(Boolean);
    if (parts.at(-1) !== project.id || parts.length < 2) continue;
    const parent = parts.slice(0, -1).join('/');
    counts.set(parent, (counts.get(parent) || 0) + 1);
  }
  let best = '', bestCount = 0;
  for (const [parent, count] of counts) {
    if (count > bestCount) { best = parent; bestCount = count; }
  }
  return bestCount > 0 ? best : '';
}
function projectLooksManaged(project) {
  if (!project.root) return true;
  const parts = String(project.root).split(/[\\/]+/).filter(Boolean);
  if (parts.at(-1) !== project.id) return false;
  const managedDir = managedProjectsDirGuess();
  if (!managedDir) return true;
  return parts.slice(0, -1).join('/') === managedDir;
}
function renderProjectList() {
  const filter = document.getElementById('project-search').value.trim().toLocaleLowerCase();
  const opened = new Map(recentProjects.map(item => [item.id, item.openedAt]));
  const matching = [...projects].filter(project => projectMatchesFilter(project, filter))
    .sort((a, b) => (opened.get(b.id) || 0) - (opened.get(a.id) || 0));
  const list = document.getElementById('project-list');
  list.replaceChildren();
  for (const project of matching) {
    const card = document.getElementById('project-card-template').content.firstElementChild.cloneNode(true);
    const open = card.querySelector('.project-card-main');
    open.dataset.arg = project.id;
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
    const actions = card.querySelector('.project-card-actions');
    actions.hidden = projectReadOnly;
    for (const button of card.querySelectorAll('.project-card-action')) {
      button.dataset.arg = project.id;
      button.textContent = t(button.dataset.click === 'renameProject' ? 'workspace.rename' : 'workspace.delete');
    }
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
            page.frame.contentWindow.loadAskThread?.();
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
function showRenameProjectDialog(id) {
  if (projectReadOnly) return;
  const project = projects.find(item => item.id === id);
  if (!project) return;
  renameTargetId = id;
  document.getElementById('project-rename-title').textContent = t('workspace.renameTitle');
  document.getElementById('project-rename-label').textContent = t('workspace.dialogNewLabel');
  document.getElementById('project-rename-submit').textContent = t('workspace.renameSave');
  document.getElementById('project-rename-input').value = project.name;
  document.getElementById('project-rename-error').textContent = '';
  document.getElementById('project-rename-dialog').showModal();
  const input = document.getElementById('project-rename-input');
  input.focus();
  input.select();
}
function refreshRenameProjectDialog() {
  const dialog = document.getElementById('project-rename-dialog');
  if (!dialog.open) return;
  document.getElementById('project-rename-title').textContent = t('workspace.renameTitle');
  document.getElementById('project-rename-label').textContent = t('workspace.dialogNewLabel');
  document.getElementById('project-rename-submit').textContent = t('workspace.renameSave');
}
async function submitRenameProject(event) {
  event.preventDefault();
  if (projectReadOnly || !renameTargetId) return;
  const name = document.getElementById('project-rename-input').value.trim();
  if (!name) { document.getElementById('project-rename-input').focus(); return; }
  const submit = document.getElementById('project-rename-submit');
  submit.disabled = true;
  document.getElementById('project-rename-error').textContent = '';
  try {
    const response = await fetch('/api/projects/' + encodeURIComponent(renameTargetId), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    });
    const project = await response.json();
    if (!response.ok) throw new Error(projectError(project, response));
    const index = projects.findIndex(item => item.id === project.id);
    if (index >= 0) projects[index] = { ...projects[index], ...project };
    else projects.push(project);
    renderProjects();
    document.getElementById('project-rename-dialog').close();
  } catch (error) {
    document.getElementById('project-rename-error').textContent = t('workspace.renameFailed', {
      message: error.message || '',
    });
  } finally { submit.disabled = false; }
}
function deleteConfirmMatches(project, value) {
  const token = value.trim();
  if (!token || !project) return false;
  return token === project.id || token.toLocaleLowerCase() === project.name.toLocaleLowerCase();
}
function syncDeleteConfirmState() {
  const project = projects.find(item => item.id === deleteTargetId);
  const input = document.getElementById('project-delete-confirm');
  document.getElementById('project-delete-submit').disabled = !deleteConfirmMatches(project, input.value);
}
function showDeleteProjectDialog(id) {
  if (projectReadOnly) return;
  const project = projects.find(item => item.id === id);
  if (!project) return;
  if (project.index_status === 'indexing' || projectIndexJobs.has(project.id)) {
    toast(t('workspace.deleteBusy'), 'warning');
    return;
  }
  deleteTargetId = id;
  const managed = projectLooksManaged(project);
  fillDeleteProjectDialog(project, managed);
  document.getElementById('project-delete-confirm').value = '';
  document.getElementById('project-delete-error').textContent = '';
  syncDeleteConfirmState();
  document.getElementById('project-delete-dialog').showModal();
  document.getElementById('project-delete-confirm').focus();
}
function fillDeleteProjectDialog(project, managed = projectLooksManaged(project)) {
  document.getElementById('project-delete-title').textContent = t('workspace.deleteTitle');
  document.getElementById('project-delete-body').textContent = t(
    managed ? 'workspace.deleteBodyDestroy' : 'workspace.deleteBodyUnregister',
  );
  document.getElementById('project-delete-confirm-label').textContent = t('workspace.deleteConfirmLabel');
  document.getElementById('project-delete-hint').textContent = t('workspace.deleteConfirmHint', {
    name: project.name, id: project.id,
  });
  document.getElementById('project-delete-submit').textContent = t('workspace.deleteConfirmAction');
}
function refreshDeleteProjectDialog() {
  const dialog = document.getElementById('project-delete-dialog');
  if (!dialog.open) return;
  const project = projects.find(item => item.id === deleteTargetId);
  if (!project) { dialog.close(); return; }
  fillDeleteProjectDialog(project);
}
function forgetDeletedProject(id) {
  projects = projects.filter(item => item.id !== id);
  recentProjects = recentProjects.filter(item => item.id !== id);
  try { localStorage.setItem(RECENT_PROJECTS_STORAGE, JSON.stringify(recentProjects)); } catch (_) { /* storico facoltativo */ }
  for (const [key, page] of [...workspacePages.entries()]) {
    if (page.project !== id) continue;
    page.frame?.remove();
    workspacePages.delete(key);
  }
  workspaceProjects.delete(id);
  projectIndexJobs.delete(id);
  projectIndexRepairs.delete(id);
}
async function submitDeleteProject(event) {
  event.preventDefault();
  if (projectReadOnly || !deleteTargetId) return;
  const project = projects.find(item => item.id === deleteTargetId);
  if (!project) return;
  const confirm = document.getElementById('project-delete-confirm').value;
  if (!deleteConfirmMatches(project, confirm)) {
    syncDeleteConfirmState();
    document.getElementById('project-delete-confirm').focus();
    return;
  }
  const submit = document.getElementById('project-delete-submit');
  submit.disabled = true;
  document.getElementById('project-delete-error').textContent = '';
  const deletedId = project.id;
  const wasCurrent = currentProject === deletedId || new URL(location.href).searchParams.get('project') === deletedId;
  try {
    const params = new URLSearchParams({ confirm: confirm.trim() });
    const response = await fetch('/api/projects/' + encodeURIComponent(deletedId) + '?' + params, { method: 'DELETE' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok && response.status !== 207) {
      const code = data.detail?.code;
      if (code === 'project_busy') throw new Error(t('workspace.deleteBusy'));
      throw new Error(projectError(data, response));
    }
    forgetDeletedProject(deletedId);
    document.getElementById('project-delete-dialog').close();
    if (wasCurrent) {
      currentProject = '';
      try { sessionStorage.removeItem(PROJECT_STORAGE); } catch (_) { /* tab privata */ }
      renderProjects();
      showProjectWelcome(true);
    } else {
      renderProjects();
    }
    if (response.status === 207 || data.code === 'project_cleanup_partial') {
      toast(t('workspace.deletePartialCleanup'), 'warning');
    }
  } catch (error) {
    const message = error.message || '';
    document.getElementById('project-delete-error').textContent = message === t('workspace.deleteBusy')
      ? message
      : t('workspace.deleteFailed', { message });
    syncDeleteConfirmState();
  } finally {
    if (document.getElementById('project-delete-dialog').open) syncDeleteConfirmState();
    else submit.disabled = false;
  }
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
  refreshRenameProjectDialog();
  refreshDeleteProjectDialog();
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
  renameProject: el => showRenameProjectDialog(el.dataset.arg),
  cancelRenameProject: () => document.getElementById('project-rename-dialog').close(),
  deleteProject: el => showDeleteProjectDialog(el.dataset.arg),
  cancelDeleteProject: () => document.getElementById('project-delete-dialog').close(),
  updateProjectIndex,
});
/* ──────────── IMPOSTAZIONI: interfaccia e modelli LLM (2026-10-30) ────────────
   Le scelte LLM vivono sul server (/api/settings/llm, core/llm_settings_store.py) e
   valgono per tutti i progetti; le API key si scrivono e basta: il server risponde solo
   da dove arrivano (ambiente, file, nessuna). */
const LLM_PROVIDERS = ['ollama', 'anthropic', 'openai', 'claude_code'];
// Provider con API key e prezzo per token; claude_code usa il login dell'abbonamento.
const LLM_CLOUD = ['anthropic', 'openai'];
let llmView = null;
function settingsError(data, response) {
  if (Array.isArray(data.detail)) return data.detail.map(item => item.msg).join('; ');
  return projectError(data, response);
}
function llmMode() {
  return document.querySelector('input[name="llm-mode"]:checked')?.value || 'local';
}
function llmKeyStatus(provider) {
  const info = llmView.providers[provider];
  const key = info.key === 'env' ? t('settings.keyEnv', { env: info.key_env })
    : info.key === 'file' ? t('settings.keyFile') : t('settings.keyMissing', { env: info.key_env });
  document.getElementById('llm-key-status-' + provider).textContent = key;
}
function syncLlmPrice(el) {
  const provider = el.dataset.arg;
  const price = (llmView?.pricing || {})[el.value.trim()] || {};
  document.getElementById('llm-price-in-' + provider).value = price.input_per_mtok ?? '';
  document.getElementById('llm-price-out-' + provider).value = price.output_per_mtok ?? '';
}
function renderLlmActivities() {
  const body = document.querySelector('#llm-activities tbody');
  body.replaceChildren(...llmView.activities.map(activity => {
    const choice = llmView.purposes[activity] || {};
    const row = document.createElement('tr');
    const name = document.createElement('th');
    name.scope = 'row';
    name.textContent = t('settings.act.' + activity);
    const provider = document.createElement('select');
    provider.dataset.activity = activity;
    provider.dataset.change = 'syncLlmActivity';
    provider.setAttribute('aria-label', t('settings.providerFor', { activity: name.textContent }));
    for (const value of LLM_PROVIDERS) provider.add(new Option(t('settings.providerName.' + value), value));
    provider.value = choice.provider || 'ollama';
    const model = document.createElement('input');
    model.autocomplete = 'off';
    model.spellcheck = false;
    model.placeholder = t('settings.modelDefault');
    model.setAttribute('aria-label', t('settings.modelFor', { activity: name.textContent }));
    model.setAttribute('list', 'llm-models-' + provider.value);
    model.value = choice.model || '';
    row.append(name, ...[provider, model].map(control => { const cell = document.createElement('td'); cell.append(control); return cell; }));
    return row;
  }));
}
function syncLlmActivity(el) {
  const model = el.closest('tr').querySelector('input');
  model.setAttribute('list', 'llm-models-' + el.value);
  model.value = '';
}
function renderLlmMode() {
  const mode = llmMode();
  const cloud = document.getElementById('llm-cloud-provider').value;
  const show = (id, visible) => { document.getElementById(id).hidden = !visible; };
  show('llm-local-label', mode !== 'cloud');
  show('llm-model-ollama', mode !== 'cloud');
  show('llm-cloud-label', mode === 'cloud');
  show('llm-cloud-provider', mode === 'cloud');
  show('llm-activities', mode === 'custom');
  show('llm-budget-row', mode !== 'local');
  document.querySelectorAll('.settings-provider').forEach(box => {
    box.hidden = mode === 'local' || (mode === 'cloud' && box.dataset.provider !== cloud);
  });
}
async function loadLlmModels(provider) {
  const note = document.getElementById('llm-models-note-' + provider);
  try {
    const response = await fetch('/api/settings/llm/models?provider=' + encodeURIComponent(provider));
    const data = await response.json();
    if (!response.ok) throw new Error(settingsError(data, response));
    document.getElementById('llm-models-' + provider).replaceChildren(...data.models.map(name => new Option(name, name)));
    if (note) note.textContent = data.error ? t('settings.modelsError', { error: data.error }) : data.source === 'default' ? t('settings.modelsDefault') : '';
  } catch (error) {
    if (note) note.textContent = t('settings.modelsError', { error: error.message });
  }
}
async function loadLlmSettings() {
  const status = document.getElementById('llm-settings-status');
  status.textContent = t('settings.loading');
  try {
    const response = await fetch('/api/settings/llm');
    const data = await response.json();
    if (!response.ok) throw new Error(settingsError(data, response));
    llmView = data;
  } catch (error) {
    status.textContent = t('settings.loadError', { error: error.message });
    return;
  }
  status.textContent = '';
  document.querySelector(`input[name="llm-mode"][value="${llmView.mode}"]`).checked = true;
  document.getElementById('llm-cloud-provider').value = llmView.cloud_provider;
  for (const provider of LLM_PROVIDERS) document.getElementById('llm-model-' + provider).value = llmView.models[provider] || '';
  for (const provider of LLM_CLOUD) {
    llmKeyStatus(provider);
    syncLlmPrice(document.getElementById('llm-model-' + provider));
  }
  document.getElementById('llm-base-url-openai').value = llmView.providers.openai.base_url;
  const claudeCode = llmView.providers.claude_code;
  const warning = document.getElementById('llm-claude-code-warning');
  warning.textContent = !claudeCode.cli ? t('settings.claudeCodeNoCli') : claudeCode.api_key_env ? t('settings.claudeCodeEnvKey') : '';
  warning.hidden = !warning.textContent;
  document.getElementById('llm-budget').value = llmView.budget_daily_usd ?? '';
  renderLlmActivities();
  renderLlmMode();
  LLM_PROVIDERS.forEach(loadLlmModels);
}
async function openSettings() {
  document.getElementById('settings-dialog').showModal();
  await loadLlmSettings();
}
function llmPayload() {
  const mode = llmMode();
  const models = {};
  for (const provider of LLM_PROVIDERS) {
    const value = document.getElementById('llm-model-' + provider).value.trim();
    if (value) models[provider] = value;
  }
  const purposes = {};
  if (mode === 'custom') {
    for (const row of document.querySelectorAll('#llm-activities tbody tr')) {
      const provider = row.querySelector('select');
      const model = row.querySelector('input').value.trim();
      purposes[provider.dataset.activity] = model ? { provider: provider.value, model } : { provider: provider.value };
    }
  }
  const pricing = {};
  for (const provider of LLM_CLOUD) {
    const input = document.getElementById('llm-price-in-' + provider).value;
    if (models[provider] && input !== '') {
      pricing[models[provider]] = { input_per_mtok: Number(input), output_per_mtok: Number(document.getElementById('llm-price-out-' + provider).value || 0) };
    }
  }
  const budget = document.getElementById('llm-budget').value;
  return {
    mode, cloud_provider: document.getElementById('llm-cloud-provider').value, models, purposes, pricing,
    openai_base_url: document.getElementById('llm-base-url-openai').value.trim() || null,
    budget_daily_usd: mode === 'local' || budget === '' ? null : Number(budget),
  };
}
async function saveLlmSettings(event) {
  event.preventDefault();
  const payload = llmPayload();
  const status = document.getElementById('llm-settings-status');
  const save = document.getElementById('llm-settings-save');
  save.disabled = true;
  try {
    const response = await fetch('/api/settings/llm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(settingsError(data, response));
    llmView = data;
    status.textContent = t('settings.saved');
    toast(t('settings.saved'), 'success');
    const used = payload.mode === 'cloud' ? [payload.cloud_provider] : Object.values(payload.purposes).map(choice => choice.provider);
    const missing = LLM_CLOUD.filter(provider => used.includes(provider) && !llmView.providers[provider].key);
    // Anche nella riga di stato: i toast stanno sotto il dialogo modale aperto.
    if (missing.length) status.textContent += ' ' + t('settings.keyNeeded', { provider: missing.map(p => t('settings.providerName.' + p)).join(', ') });
  } catch (error) {
    status.textContent = t('settings.saveError', { error: error.message });
  } finally {
    save.disabled = false;
  }
}
async function sendLlmKey(provider, apiKey) {
  const status = document.getElementById('llm-settings-status');
  try {
    const response = await fetch('/api/settings/llm/key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider, api_key: apiKey }) });
    const data = await response.json();
    if (!response.ok) throw new Error(settingsError(data, response));
    llmView.providers[provider].key = data.key;
    llmKeyStatus(provider);
    document.getElementById('llm-key-' + provider).value = '';
    status.textContent = apiKey ? t('settings.keySaved') : t('settings.keyRemoved');
    loadLlmModels(provider);
  } catch (error) {
    status.textContent = t('settings.saveError', { error: error.message });
  }
}
function saveLlmKey(el) {
  const input = document.getElementById('llm-key-' + el.dataset.arg);
  if (!input.value.trim()) { input.focus(); return; }
  return sendLlmKey(el.dataset.arg, input.value.trim());
}
registerActions({
  openSettings, renderLlmMode, syncLlmActivity, syncLlmPrice, saveLlmKey,
  removeLlmKey: el => sendLlmKey(el.dataset.arg, ''),
  closeSettings: () => document.getElementById('settings-dialog').close(),
});
document.getElementById('settings-form').addEventListener('submit', saveLlmSettings);
document.getElementById('project-form').addEventListener('submit', submitProject);
document.getElementById('project-rename-form').addEventListener('submit', submitRenameProject);
document.getElementById('project-delete-form').addEventListener('submit', submitDeleteProject);
document.getElementById('project-delete-confirm').addEventListener('input', syncDeleteConfirmState);
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
