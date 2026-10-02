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

function workspaceMessage(text, retry = false) {
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
    option.textContent = currentProject ? 'Progetto non disponibile' : 'Seleziona un progetto';
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
  renderIndexStatus(projects.find(project => project.id === currentProject));
}
function renderIndexStatus(project) {
  const labels = { not_indexed: 'Non indicizzato', ready: 'Indice pronto', indexing: 'Indicizzazione in corso', error: 'Errore indice' };
  document.getElementById('project-index-status').textContent = project
    ? `${labels[project.index_status] || 'Stato indice non disponibile'}${project.stale ? ' · da aggiornare' : ''}` : '';
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
    if (currentProject === id) document.getElementById('project-index-status').textContent = `Stato indice: ${error.message}`;
  }
}
function selectCurrentProject(id) {
  currentProject = id;
  try { sessionStorage.setItem(PROJECT_STORAGE, id); } catch (_) { /* tab privata */ }
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
    if (!evicted) throw new Error('Due progetti hanno operazioni attive. Attendi il completamento prima di aprire un terzo progetto.');
  }
  workspaceProjects.set(id, true);
}

async function navigateWorkspace(target, push = true) {
  const url = new URL(target, location.origin);
  if (url.origin !== location.origin || !workspaceRoutes.has(url.pathname)) return;
  url.searchParams.delete('workspace');
  const project = url.searchParams.get('project') || currentProject;
  if (!project) { workspaceMessage('Nessun progetto selezionato. Crea un nuovo progetto o aprine uno esistente.'); return; }
  if (!projects.some(item => item.id === project)) { workspaceMessage('Progetto non disponibile. Seleziona un progetto valido.'); return; }
  url.searchParams.set('project', project);
  const key = project + ':' + url.pathname;
  const navigation = ++workspaceNavigation;
  workspaceTarget = url.href;
  workspaceMessage('Caricamento…');
  try {
    reserveProject(project);
    if (!workspacePages.has(key)) {
      const pageUrl = new URL(url);
      pageUrl.searchParams.set('workspace', '1');
      const page = { key, project, frame: null };
      page.loading = fetch(pageUrl.href).then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const frame = document.createElement('iframe');
        frame.title = `VibeCraft · ${url.pathname === '/' ? 'Console' : url.pathname.slice(1)}`;
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
    if (url.href !== location.href) {
      if (push) history.pushState(null, '', url);
      else history.replaceState(null, '', url);
    }
    document.getElementById('workspace-status').hidden = true;
    frame.focus();
    refreshIndexStatus(project);
    if (url.hash) frame.contentDocument.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView();
  } catch (error) {
    if (navigation !== workspaceNavigation) return;
    document.getElementById('project-select').value = currentProject;
    workspaceMessage(`Impossibile aprire la pagina: ${error.message}`, true);
  }
}

function showProjectDialog(mode) {
  if (projectReadOnly) return;
  projectDialogMode = mode;
  const opening = mode === 'open';
  document.getElementById('project-dialog-title').textContent = opening ? 'Apri progetto esistente' : 'Nuovo progetto';
  document.getElementById('project-input-label').textContent = opening ? 'Cartella del progetto' : 'Nome del progetto';
  document.getElementById('project-input').value = '';
  document.getElementById('project-help').textContent = opening
    ? 'Scegli una cartella VibeCraft con project.yaml valido. In Docker usa una directory montata nel container.'
    : 'La cartella viene creata nella directory gestita dal server. Potrai importare codice e documenti dalla pagina Intake.';
  document.getElementById('project-submit').textContent = opening ? 'Apri' : 'Crea';
  const localBind = document.querySelector('meta[name="vibecraft-local-bind"]')?.content === 'true';
  document.getElementById('project-browse').hidden = !opening || !localBind;
  document.getElementById('project-error').textContent = '';
  document.getElementById('project-dialog').showModal();
  document.getElementById('project-input').focus();
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
  try {
    const response = await fetch('/api/projects');
    const data = await response.json();
    if (!response.ok) throw new Error(projectError(data, response));
    projects = data.projects;
    projectReadOnly = data.read_only;
    // Compatibilità soltanto legacy; nessun fallback al primo progetto della lista.
    if (!currentProject && projects.some(project => project.id === 'legacy')) currentProject = 'legacy';
    renderProjects();
    await navigateWorkspace(location.href, false);
  } catch (error) { workspaceMessage(`Impossibile caricare i progetti: ${error.message}`, true); }
}

window.navigateWorkspace = navigateWorkspace;
window.workspaceRoutes = workspaceRoutes;
registerActions({
  retryNavigation: () => projects.length ? navigateWorkspace(workspaceTarget) : initializeWorkspace(),
  selectProject: el => { const url = new URL(location.href); url.searchParams.set('project', el.value); return navigateWorkspace(url.href); },
  newProject: () => showProjectDialog('new'), openProject: () => showProjectDialog('open'),
  cancelProject: () => document.getElementById('project-dialog').close(), browseExistingProject,
});
document.getElementById('project-form').addEventListener('submit', submitProject);
window.addEventListener('popstate', () => navigateWorkspace(location.href, false));
setInterval(() => refreshIndexStatus(), 15000);
initializeWorkspace();
