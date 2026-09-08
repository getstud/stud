const $ = id => document.getElementById(id);
const invoke = window.__TAURI__?.core.invoke;
let checking = false;
let installing = false;
let info;

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
