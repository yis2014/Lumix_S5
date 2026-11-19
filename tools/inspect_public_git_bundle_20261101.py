"""Import a verified public Git bundle into an isolated bare evidence repo.
No checkout, hooks, worktree, downloaded scripts, or firmware are executed.
"""
from pathlib import Path
import os, subprocess, json, hashlib, re
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/eeprom_keyhunt_20261101/public_history'
BUNDLE=OUT/'S5-wireless-monitor_v1.1.bundle'
REPO=OUT/'evidence.git'
EMPTY=OUT/'empty_template';HOOKS=OUT/'empty_hooks'
GIT=r'D:\Git\cmd\git.exe'
ENV=os.environ.copy();ENV['GIT_CONFIG_NOSYSTEM']='1';ENV['GIT_CONFIG_GLOBAL']=os.devnull;ENV['GIT_TERMINAL_PROMPT']='0'
commands=[]

def command(args,label,stdin=None,accepted=(0,)):
    out=OUT/(label+'.txt');err=OUT/(label+'.stderr.txt')
    with out.open('wb') as o,err.open('wb') as e:
        if stdin is not None:
            with stdin.open('rb') as inp:result=subprocess.run([GIT]+args,stdin=inp,stdout=o,stderr=e,env=ENV,check=False,timeout=180)
        else:result=subprocess.run([GIT]+args,stdin=subprocess.DEVNULL,stdout=o,stderr=e,env=ENV,check=False,timeout=180)
    commands.append(dict(label=label,args=args,returncode=result.returncode))
    if result.returncode not in accepted:raise RuntimeError('Git failed: '+label+'; inspect '+str(err))
    print(label,'exit',result.returncode,flush=True)
    return out

def main():
    source=json.loads((OUT/'bundle_source.json').read_text(encoding='utf-8'))
    b=BUNDLE.read_bytes();assert len(b)==source['bytes'] and hashlib.sha256(b).hexdigest()==source['sha256']
    assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==source['git_blob_sha1']
    EMPTY.mkdir(exist_ok=True);HOOKS.mkdir(exist_ok=True)
    assert not list(EMPTY.iterdir()) and not list(HOOKS.iterdir())
    command(['bundle','list-heads',str(BUNDLE)],'bundle_heads')
    if not REPO.exists():command(['init','--bare','--template='+str(EMPTY),str(REPO)],'bare_init')
    common=['-c','core.hooksPath='+str(HOOKS),'-c','gc.auto=0','--git-dir='+str(REPO)]
    command(common+['bundle','verify',str(BUNDLE)],'bundle_verify')
    command(common+['fetch','--no-tags',str(BUNDLE),'refs/heads/*:refs/heads/*','refs/tags/*:refs/tags/*'],'bundle_import')
    command(common+['fsck','--full','--no-reflogs'],'git_fsck')
    commits_file=command(common+['rev-list','--all','--count'],'commit_count')
    objects=command(common+['rev-list','--objects','--all'],'all_objects')
    metadata=command(common+['cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)'],'object_metadata',objects)
    matches=[];counts={};large=[];all_text=[]
    for line in metadata.read_text(encoding='utf-8',errors='replace').splitlines():
        parts=line.split(' ',3)
        if len(parts)<3:continue
        oid,kind,size=parts[:3];size=int(size);path=parts[3] if len(parts)>3 else ''
        counts[kind]=counts.get(kind,0)+1
        if kind!='blob':continue
        row=dict(oid=oid,size=size,path=path)
        if size<=2*1024*1024 and re.search(r'\.(py|c|h|cpp|m|mm|md|txt|json|js|ts|swift|html|sh|command)$',path,re.I):all_text.append(row)
        if size>=1024*1024:large.append(row)
        if re.search(r'g100|g110|firmware|crypto|decrypt|recover|loader|(^|/)program(?:\.|/|$)|\.elf$|\.axf$|\.i64$|\.idb$',path,re.I):matches.append(row)
    selected=[];SNAP=OUT/'selected_source';SNAP.mkdir(exist_ok=True)
    for row in all_text:
        # Copy every small textual source by OID, not only suggestive filenames.
        # No source is executed or checked out.
        dest=command(common+['cat-file','blob',row['oid']],'selected_'+row['oid'])
        selected.append(dict(**row,evidence=str(dest.relative_to(ROOT))))
    result=dict(source=source,commands=commands,bare_repository=str(REPO.relative_to(ROOT)),
        commit_count=int(commits_file.read_text().strip()),object_counts=counts,
        relevant_paths=matches,large_blobs=large,selected_text_sources=selected,
        no_checkout=True,no_hooks=True,downloaded_code_executed=False,
        scope='Reachable objects from verified bundle imported heads/tags; no claim about unreachable or other archives.')
    (OUT/'bundle_inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['commit_count','object_counts','relevant_paths','large_blobs']},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
