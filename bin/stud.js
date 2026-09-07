#!/usr/bin/env node
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const result = spawnSync(process.env.STUD_PYTHON || 'python3', [fileURLToPath(new URL('../stud_cli.py', import.meta.url)), ...process.argv.slice(2)], {stdio: 'inherit'});
if (result.error) { console.error(`Could not start stud: ${result.error.message}. Install Python 3.10+ or set STUD_PYTHON.`); }
process.exit(result.status ?? 1);
