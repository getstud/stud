/** Copy and verify the design guidance shipped with the desktop engine. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const trees = [['skills/stud-design', 'skills/stud-design'], ['docs', 'engine/docs'], ['examples', 'engine/examples']];
async function files(directory, prefix = '') {
  const found = [];
  for (const entry of await fs.readdir(path.join(directory, prefix), { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name.endsWith('.pyc') || entry.name === 'output') continue;
    const relative = path.join(prefix, entry.name);
    if (entry.isDirectory()) found.push(...await files(directory, relative));
    else if (entry.isFile()) found.push(relative);
    else throw new Error(`Unsupported design resource: ${relative}`);
  }
  return found.sort();
}

export async function verifyDesignResources(root, resources) {
  for (const [source, destination] of trees) {
    const expected = await files(path.join(root, source));
    const actual = await files(path.join(resources, destination));
    if (JSON.stringify(expected) !== JSON.stringify(actual)) {
      throw new Error(`Design resource inventory differs: ${destination}`);
    }
    for (const file of expected) {
      const [a, b] = await Promise.all([
        fs.readFile(path.join(root, source, file)),
        fs.readFile(path.join(resources, destination, file)),
      ]);
      if (!a.equals(b)) throw new Error(`Stale design resource: ${path.join(destination, file)}`);
    }
  }
}

export async function copyDesignResources(root, resources) {
  for (const [source, destination] of trees) {
    await fs.cp(path.join(root, source), path.join(resources, destination), { recursive: true, filter: file => !file.split(path.sep).some(part => part === '__pycache__' || part === 'output' || part.endsWith('.pyc')) });
  }
  await verifyDesignResources(root, resources);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv[2] !== 'verify' || !process.argv[3]) {
    throw new Error('Usage: node scripts/design-resources.mjs verify /path/to/Resources');
  }
  const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
  await verifyDesignResources(root, path.resolve(process.argv[3]));
  console.log('Packaged design skill and documentation match this checkout.');
}
