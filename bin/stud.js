#!/usr/bin/env node
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
const localPython=fileURLToPath(new URL(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python',import.meta.url));
const result = spawnSync(process.env.STUD_PYTHON || (existsSync(localPython)?localPython:'python3'), [fileURLToPath(new URL('../stud_cli.py', import.meta.url)), ...process.argv.slice(2)], {stdio: 'inherit'});
if (result.error) { console.error(`Could not start stud: ${result.error.message}. Install Python 3.10+ or set STUD_PYTHON.`); }
process.exit(result.status ?? 1);
