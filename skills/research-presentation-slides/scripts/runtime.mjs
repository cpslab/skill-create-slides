// Resolve capabilities supplied by the host; no personal paths or silent installation.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
export async function runtime() {
  const modules=process.env.RUNTIME_NODE_MODULES || process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
  if(!modules || !path.isAbsolute(modules)) throw new Error('Set RUNTIME_NODE_MODULES to the available bundled node_modules directory.');
  const require=createRequire(path.join(modules,'package.json'));
  const api=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
  const sharp=require('sharp');
  return {...api,sharp};
}
export function args(names) {
 const a=process.argv.slice(2),out={};
 if(a.includes('--help')) {console.log(names.map(n=>`--${n} <value>`).join(' '));process.exit(0);}
 for(let i=0;i<a.length;i+=2){if(!a[i]?.startsWith('--')||!a[i+1]||!names.includes(a[i].slice(2)))throw new Error(`Unknown/incomplete argument ${a[i]}`);out[a[i].slice(2)]=a[i+1];}
 return out;
}
export async function readJSON(p){return JSON.parse(await fs.readFile(p,'utf8'));}
