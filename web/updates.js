const notice = document.getElementById('update-notice');
let checking = false;
let shownVersion;
let dismissedVersion;
try { dismissedVersion = sessionStorage.getItem('stud-dismissed-update'); } catch {}

document.getElementById('update-dismiss').onclick = () => {
  dismissedVersion = shownVersion;
  notice.hidden = true;
  try { sessionStorage.setItem('stud-dismissed-update', dismissedVersion); } catch {}
};

async function checkUpdate() {
  if (checking) return;
  checking = true;
  try {
    const response = await fetch('/api/update', {cache: 'no-store', signal: AbortSignal.timeout(10000)});
    if (!response.ok) return;
    const update = await response.json();
    if (!update.available || typeof update.version !== 'string') return;
    const url = new URL(update.url);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com') return;
    shownVersion = update.version;
    document.getElementById('update-title').textContent = `stud ${update.version} is available`;
    document.getElementById('update-release').href = url.href;
    notice.hidden = dismissedVersion === shownVersion;
  } catch { /* A failed update check must not interrupt the viewer. */ }
  finally { checking = false; }
}
checkUpdate();
setInterval(checkUpdate, 15 * 60 * 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkUpdate(); });
