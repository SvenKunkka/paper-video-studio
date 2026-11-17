import { build } from 'esbuild';
import { cp, mkdir, rm, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.join(root, 'dist');
await rm(outdir, {recursive: true, force: true});
await mkdir(outdir, {recursive: true});
await build({entryPoints: [path.join(root, 'app.js'),path.join(root,'render-worker.js')], bundle: true, format: 'esm',
  platform: 'browser', target: 'es2022', outdir, splitting: true,
  minify: true, sourcemap: false, legalComments: 'linked', chunkNames: 'chunks/[name]-[hash]',
  define: {'process.env.NODE_ENV': '"production"'}});
for (const file of ['index.html', 'styles.css']) await cp(path.join(root,file),path.join(outdir,file));
try { await cp(path.join(root,'tts/vendor'),path.join(outdir,'tts/vendor'),{recursive:true}); }
catch(error) { if(error.code!=='ENOENT') throw error; }
try { await cp(path.join(root,'vendor'),path.join(outdir,'vendor'),{recursive:true}); }
catch(error) { if(error.code!=='ENOENT') throw error; }
for (const file of ['LICENSE','NOTICE.md','THIRD_PARTY_TTS.md','THIRD_PARTY_MEDIA.md']) {
  try { await cp(path.join(root,'..',file),path.join(outdir,file)); } catch(error) {if(error.code!=='ENOENT')throw error;}
}
console.log('Built browser app:',outdir);
