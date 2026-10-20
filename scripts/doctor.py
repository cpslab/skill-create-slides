#!/usr/bin/env python3
"""Report capabilities, without installing software or claiming application validation."""
import argparse, hashlib, json, os, pathlib, platform, shutil, subprocess, sys

def run(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=30)
        return {'status':'pass' if p.returncode==0 else 'unverified','exit_code':p.returncode,'output':(p.stdout+p.stderr).strip()[:4000]}
    except (OSError,subprocess.TimeoutExpired) as e:return {'status':'unverified','reason':str(e)}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',required=True);a=ap.parse_args()
    d={'platform':platform.platform(),'architecture':platform.machine(),'python':sys.version,'python_executable':sys.executable,'tools':{},'application_edit_and_video':{'status':'unverified','reason':'Requires actual operation in the target application.'}}
    for tool in ('uv','ni','nix','node','fc-list','soffice','sandbox-exec'):
        exe=shutil.which(tool);d['tools'][tool]={'path':exe,'status':'available' if exe else 'unverified'}
    node=os.environ.get('RUNTIME_NODE') or shutil.which('node');mods=os.environ.get('RUNTIME_NODE_MODULES') or os.environ.get('CODEX_PRIMARY_RUNTIME_NODE_MODULES')
    if node:d['node_version']=run([node,'--version'])
    if node and mods:
        code="import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';const r=createRequire(process.argv[1]+'/package.json');for(const n of ['@oai/artifact-tool','sharp']){const p=r.resolve(n);console.log(n,p);await import(pathToFileURL(p).href)}"
        d['node_import']=run([node,'--input-type=module','-e',code,mods])
    else:d['node_import']={'status':'unverified','reason':'Set RUNTIME_NODE and RUNTIME_NODE_MODULES (or CODEX_PRIMARY_RUNTIME_NODE_MODULES).'}
    font_files=[]
    for root in [pathlib.Path('/Library/Fonts'),pathlib.Path.home()/'Library/Fonts',pathlib.Path('/usr/share/fonts')]:
        if root.exists():font_files += [p for p in root.rglob('*') if p.is_file() and 'noto' in p.name.lower() and p.suffix.lower() in ('.ttf','.otf','.ttc')]
    d['font_files']=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in font_files]
    d['font_rendering']={'status':'unverified','reason':'Installed files alone do not prove renderer font selection; inspect final renders.'}
    out=pathlib.Path(a.report);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(a.report)
if __name__=='__main__':main()
