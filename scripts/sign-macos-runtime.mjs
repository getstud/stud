import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const magic = new Set(['feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca']);
export async function machOFiles(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await machOFiles(file));
    else if (entry.isFile()) {
      const handle = await fs.open(file, 'r');
      try {
        const header = Buffer.alloc(4);
        const { bytesRead } = await handle.read(header, 0, 4, 0);
        if (bytesRead === 4 && magic.has(header.toString('hex'))) result.push(file);
      } finally { await handle.close(); }
    }
  }
  return result;
}

export async function signRuntime(directory = 'src-tauri/resources/runtime') {
  if (process.platform !== 'darwin') throw new Error('Runtime signing requires macOS');
  const identity = process.env.APPLE_SIGNING_IDENTITY;
  if (!identity || identity === '-') throw new Error('APPLE_SIGNING_IDENTITY must name a Developer ID certificate');
  const files = await machOFiles(directory);
  if (!files.length) throw new Error('No Mach-O runtime files found');
  const run = (command, args) => {
    const result = spawnSync(command, args, { encoding: 'utf8' });
    if (result.error || result.status !== 0) {
      // Never include command arguments: keychain commands contain credentials.
      throw new Error(`${command} failed: ${result.stderr || result.error?.message || result.status}`);
    }
  };
  let temporary;
  let keychain;
  try {
    if (process.env.APPLE_CERTIFICATE) {
      temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'stud-signing-'));
      const certificate = path.join(temporary, 'certificate.p12');
      keychain = path.join(temporary, 'runtime.keychain-db');
      const password = randomBytes(32).toString('hex');
      await fs.writeFile(certificate, Buffer.from(process.env.APPLE_CERTIFICATE, 'base64'), { mode: 0o600 });
      run('security', ['create-keychain', '-p', password, keychain]);
      run('security', ['set-keychain-settings', '-lut', '21600', keychain]);
      run('security', ['unlock-keychain', '-p', password, keychain]);
      run('security', ['import', certificate, '-k', keychain, '-P', process.env.APPLE_CERTIFICATE_PASSWORD || '', '-T', '/usr/bin/codesign', '-T', '/usr/bin/security']);
      run('security', ['set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:', '-s', '-k', password, keychain]);
    }
    for (const file of files) {
      run('codesign', ['--force', '--options', 'runtime', '--timestamp', '--sign', identity, ...(keychain ? ['--keychain', keychain] : []), file]);
      run('codesign', ['--verify', '--strict', file]);
    }
    console.log(`Signed and verified ${files.length} bundled Python executables and native libraries.`);
  } finally {
    if (keychain) spawnSync('security', ['delete-keychain', keychain], { stdio: 'ignore' });
    if (temporary) await fs.rm(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await signRuntime(process.argv[2]);
