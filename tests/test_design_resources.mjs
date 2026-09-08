import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyDesignResources, verifyDesignResources } from '../scripts/design-resources.mjs';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

test('desktop resources include the current skill, references and modeling docs', async t => {
  const resources = await fs.mkdtemp(path.join(os.tmpdir(), 'stud-guidance-'));
  t.after(() => fs.rm(resources, { recursive: true, force: true }));
  await copyDesignResources(root, resources);
  await verifyDesignResources(root, resources);
  for (const file of ['engine/docs/assemblies.md', 'engine/docs/workshop.md',
    'skills/stud-design/references/framed-buildings.md', 'engine/examples/framed-shed/design.py',
    'engine/examples/framed-shed/README.md']) {
    assert.ok((await fs.stat(path.join(resources, file))).isFile());
  }
  await fs.appendFile(path.join(resources, 'skills/stud-design/SKILL.md'), '\nStale installation edit.\n');
  await assert.rejects(verifyDesignResources(root, resources), /Stale design resource/);
});

test('missing or extra packaged reference fails parity verification', async t => {
  const resources = await fs.mkdtemp(path.join(os.tmpdir(), 'stud-guidance-'));
  t.after(() => fs.rm(resources, { recursive: true, force: true }));
  await copyDesignResources(root, resources);
  await fs.writeFile(path.join(resources, 'skills/stud-design/stale.md'), 'old');
  await assert.rejects(verifyDesignResources(root, resources), /inventory differs/);
});
