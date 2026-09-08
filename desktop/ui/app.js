const $ = id => document.getElementById(id);
const invoke = window.__TAURI__?.core.invoke;
let checking = false;
let installing = false;
let info;
let addingProject = false;
let projectRefresh = 0;

async function refresh() {
  info = await invoke('status');
  $('version').textContent = `v${info.version}`;
  $('runtime').textContent = info.python;
  $('runtime-dot').classList.toggle('ready', info.python.startsWith('Python '));
  $('cli-state').textContent = info.cliInstalled ? 'Connected' : 'One-time setup';
  $('install-cli').disabled = false;
  $('install-cli').textContent = info.cliInstalled ? 'Reinstall command-line tool' : 'Install command-line tool ↗';
  $('copy-path').disabled = false;
  $('cli-path').textContent = info.cliPath;
  $('check-updates').disabled = !info.updatesConfigured;
  if (!info.updatesConfigured) $('update-message').textContent = 'Local build · release channel not configured';
}
async function checkUpdates() {
  if (!info?.updatesConfigured || checking || installing) return;
  checking = true;
  $('check-updates').disabled = true;
  $('install-update').hidden = true;
  $('update-message').textContent = 'Checking for updates…';
  try {
    const version = await invoke('check_update');
    $('update-message').textContent = version ? `stud ${version} is ready to install.` : 'You’re running the latest version.';
    $('install-update').hidden = !version;
  } catch (error) { $('update-message').textContent = `Couldn’t check for updates. ${error}`; }
  finally { checking = false; $('check-updates').disabled = false; }
}
$('install-cli').addEventListener('click', async () => {
  $('install-cli').disabled = true;
  $('cli-message').textContent = 'Installing the command-line tool…';
  try { $('cli-message').textContent = await invoke('install_cli'); await refresh(); }
  catch (error) { $('cli-message').textContent = String(error); }
  finally { $('install-cli').disabled = false; }
});
$('copy-path').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(info.cliPath); $('cli-message').textContent = 'CLI path copied.'; }
  catch { $('cli-message').textContent = 'Select and copy the path below.'; document.querySelector('details').open = true; }
});
$('check-updates').addEventListener('click', checkUpdates);
$('install-update').addEventListener('click', async () => {
  if (installing) return;
  installing = true;
  $('install-update').disabled = true;
  $('check-updates').disabled = true;
  $('update-message').textContent = 'Downloading and verifying the update. stud will restart when it’s ready.';
  try { await invoke('install_update'); }
  catch (error) {
    $('update-message').textContent = String(error);
    $('install-update').hidden = true;
  } finally {
    installing = false;
    $('install-update').disabled = false;
    $('check-updates').disabled = false;
  }
});
if (invoke) {
  refresh().then(checkUpdates).catch(error => { $('cli-message').textContent = String(error); });
  setInterval(checkUpdates, 6 * 60 * 60 * 1000);
} else {
  $('cli-message').textContent = 'Open this setup window through the stud desktop app.';
  $('update-message').textContent = 'Desktop app required';
}

async function refreshProjects() {
  if (!invoke) { $('projects-message').textContent = 'Open the desktop app to see your projects.'; return; }
  const revision = ++projectRefresh;
  $('refresh-projects').disabled = true;
  try {
    const projects = await invoke('list_projects');
    if (revision !== projectRefresh) return;
    $('project-list').replaceChildren();
    for (const project of projects) {
      const row = document.createElement('li');
      const name = document.createElement('strong');
      name.textContent = project.name;
      const path = document.createElement('p');
      path.className = 'path';
      path.textContent = project.path;
      row.append(name, path);
      if (!project.available) {
        const missing = document.createElement('span');
        missing.className = 'badge';
        missing.textContent = 'Folder or design.py missing';
        row.append(missing);
      }
      $('project-list').append(row);
    }
    $('projects-message').textContent = projects.length ? '' : 'Your next build starts here. Create or register a project to see it in this list.';
  } catch (error) { if (revision === projectRefresh) $('projects-message').textContent = `Couldn’t load projects. ${error}`; }
  finally { if (revision === projectRefresh) $('refresh-projects').disabled = addingProject; }
}
$('refresh-projects').addEventListener('click', refreshProjects);
window.addEventListener('focus', () => { if (!addingProject) refreshProjects(); });
refreshProjects();

$('add-project').disabled = !invoke;
$('add-project').addEventListener('click', async () => {
  if (!invoke || addingProject) return;
  addingProject = true;
  ++projectRefresh;
  $('add-project').disabled = true;
  $('refresh-projects').disabled = true;
  try {
    await invoke('add_project');
    await refreshProjects();
  } catch (error) {
    $('projects-message').textContent = `Couldn’t add project. ${error}`;
  } finally {
    addingProject = false;
    $('add-project').disabled = false;
    $('refresh-projects').disabled = false;
  }
});
