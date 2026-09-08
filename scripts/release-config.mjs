import fs from 'node:fs/promises';

export function releaseConfig(repository, publicKey) {
  if (!/^[\w.-]+\/[\w.-]+$/.test(repository || '')) throw new Error('Set STUD_RELEASE_REPOSITORY to owner/repository');
  const key = (publicKey || '').trim();
  const decoded = Buffer.from(key, 'base64').toString('utf8');
  const keyBytes = Buffer.from(decoded.trim().split('\n')[1] || '', 'base64');
  if (!decoded.startsWith('untrusted comment:') || keyBytes.length !== 42 || keyBytes.subarray(0, 2).toString() !== 'Ed') throw new Error('Set STUD_UPDATER_PUBLIC_KEY to the contents of the Tauri .pub file');
  return { bundle: { createUpdaterArtifacts: true }, plugins: { updater: {
    pubkey: key, endpoints: [`https://github.com/${repository}/releases/latest/download/latest.json`], windows: { installMode: 'passive' }
  } } };
}
if (process.argv[1] && import.meta.url === (await import('node:url')).pathToFileURL(process.argv[1]).href) {
  const config = releaseConfig(process.env.STUD_RELEASE_REPOSITORY || process.env.GITHUB_REPOSITORY, process.env.STUD_UPDATER_PUBLIC_KEY);
  if (!process.env.TAURI_SIGNING_PRIVATE_KEY) throw new Error('TAURI_SIGNING_PRIVATE_KEY is required');
  await fs.writeFile('src-tauri/release.conf.json', JSON.stringify(config, null, 2) + '\n');
  console.log('Prepared signed GitHub release configuration.');
}
