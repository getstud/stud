// Called after native installer smoke/uninstallation, only for a signed draft.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {compareVersions,releaseVersion} from './release-channel.mjs';
const triple=process.argv[2],repository=process.env.GITHUB_REPOSITORY;
assert.ok(triple&&repository&&process.env.STUD_UPDATER_PUBLIC_KEY);
const version=JSON.parse(await fs.readFile('package.json','utf8')).version;
const platform=`${process.platform}-${process.arch}`;
const temporary=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'stud-update-inputs-')));
function run(command,args,options={}) {
 const result=spawnSync(command,args,{encoding:'utf8',timeout:1200000,maxBuffer:16*1024*1024,...options});
 assert.equal(result.status,0,result.error?.message||[result.stdout,result.stderr].filter(Boolean).join('\n')||`${command} failed`);
 return result.stdout;
}
try {
 const releases=JSON.parse(run('gh',['release','list','--repo',repository,'--limit','100','--json','tagName,isDraft']));
 const previous=releases.filter(release=>{
   if(release.isDraft||!release.tagName.startsWith('v'))return false;
   try{return compareVersions(releaseVersion(release.tagName.slice(1)).version,version)<0;}catch{return false;}
 }).sort((a,b)=>compareVersions(b.tagName.slice(1),a.tagName.slice(1)))[0];
 assert.ok(previous,'A previous published release is required for native update acceptance');
 const assets=JSON.parse(run('gh',['release','view',previous.tagName,'--repo',repository,'--json','assets'])).assets;
 const suffix=process.platform==='win32'?'_x64-setup.exe':process.arch==='arm64'?'_aarch64.dmg':'_x64.dmg';
 const installers=assets.filter(asset=>asset.name.endsWith(suffix));assert.equal(installers.length,1);
 const asset=installers[0];
 run('gh',['release','download',previous.tagName,'--repo',repository,'--pattern',asset.name,'--dir',temporary]);
 const previousInstaller=path.join(temporary,asset.name);
 if(asset.digest?.startsWith('sha256:'))assert.equal(createHash('sha256').update(await fs.readFile(previousInstaller)).digest('hex'),asset.digest.slice(7));
 const bundle=path.resolve('src-tauri/target',triple,'release/bundle');
 let candidate,payload;
 if(process.platform==='darwin') {
   candidate=path.join(bundle,'macos/stud.app/Contents/MacOS/stud');
   const archives=(await fs.readdir(path.join(bundle,'macos'))).filter(name=>name.endsWith('.app.tar.gz'));
   assert.equal(archives.length,1);payload=path.join(bundle,'macos',archives[0]);
 } else {
   const seed=path.join(temporary,'candidate');await fs.cp('src-tauri/resources',seed,{recursive:true});
   candidate=path.join(seed,'stud.exe');await fs.copyFile(`src-tauri/binaries/stud-${triple}.exe`,candidate);
   const installers=(await fs.readdir(path.join(bundle,'nsis'))).filter(name=>name.endsWith('-setup.exe'));
   assert.equal(installers.length,1);payload=path.join(bundle,'nsis',installers[0]);
 }
 run(process.execPath,['scripts/verify-signed-desktop-update.mjs','--candidate-cli',candidate,
   '--previous-installer',previousInstaller,'--previous-version',previous.tagName.slice(1),
   '--payload',payload,'--signature',payload+'.sig','--target',triple,
   '--evidence',`docs/evidence/updates/${platform}.json`],{stdio:'inherit'});
} finally {await fs.rm(temporary,{recursive:true,force:true,maxRetries:10,retryDelay:500});}
