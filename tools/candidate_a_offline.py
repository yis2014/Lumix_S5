"""CVE-2016-10229 offline control-flow audit. No networking, packet bytes, kernel or device execution.
The model abstracts decisions, not checksum arithmetic, scheduling, memory corruption or exploitability.
"""
from pathlib import Path
import hashlib,json,itertools
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'analysis'/'official_kernel_review'

def model(*,truncated,first_check_ok,initial_unnecessary,helper_sets_valid,predicate_uses_valid,local_fix):
    events=[];valid=False
    # First check corresponds to the truncated branch in udp_recvmsg.
    # partial_cov and multi-iovec layouts are deliberately not simulated.
    if truncated:
        events.append('precopy_checksum')
        if not first_check_ok:
            return {'events':events+['checksum_error_exit'],'copy':'none','full_length_helper_reached':False}
        valid=helper_sets_valid
    unnecessary=initial_unnecessary or (predicate_uses_valid and valid)
    # For a good truncated packet, local_fix represents the upstream checksum_valid guard.
    reuse=(local_fix and truncated and first_check_ok) or unnecessary
    if reuse:
        events.append('bounded_copy_of_copied_bytes')
        return {'events':events,'copy':'bounded','full_length_helper_reached':False}
    events.append('full_length_copy_and_checksum_helper')
    return {'events':events,'copy':'full_length_helper','full_length_helper_reached':True,
            'warning':'Path reachability in a Boolean model only; helper behavior and checksum outcomes not simulated'}

def run_tests():
    base=dict(truncated=True,first_check_ok=True,initial_unnecessary=False,helper_sets_valid=True,predicate_uses_valid=False,local_fix=False)
    old=model(**base);assert old['full_length_helper_reached']
    aware=model(**(base|{'predicate_uses_valid':True}));assert aware['copy']=='bounded'
    fixed=model(**(base|{'local_fix':True}));assert fixed['copy']=='bounded'
    bad=model(**(base|{'first_check_ok':False}));assert bad['copy']=='none'
    missing_propagation=model(**(base|{'predicate_uses_valid':True,'helper_sets_valid':False}));assert missing_propagation['full_length_helper_reached']
    enumerated=0
    for t,ok,unnec,prop,pred,fix in itertools.product((False,True),repeat=6):
        r=model(truncated=t,first_check_ok=ok,initial_unnecessary=unnec,helper_sets_valid=prop,predicate_uses_valid=pred,local_fix=fix)
        if t and not ok:assert r['copy']=='none'
        if t and ok and (fix or unnec or (prop and pred)):assert r['copy']=='bounded'
        enumerated+=1
    return {'status':'PASS','boolean_cases':enumerated,'examples':{'legacy_predicate_assumption':old,'valid_aware_predicate_assumption':aware,'upstream_local_guard_assumption':fixed,'initial_checksum_failure':bad},
            'does_not_prove':['which predicate S5 uses','reproduction in Linux or QEMU','UAF','remote code execution','key recovery','LUT recording']}

def token_lines(text,token):return [i for i,line in enumerate(text.splitlines(),1) if token in line]

def audit():
    manifest=json.loads((SRC/'source_manifest.json').read_text(encoding='utf-8'))
    result={'scope':'offline static evidence and abstract branch model only','network_or_camera_used':False,
            'archive_integrity':'incomplete archive stream in previous acquisition; per-member size/hash only',
            'complete_archive':manifest['complete_archive'],'sources':[],'unresolved_dependencies':[],
            'verdict':'INDETERMINATE: old-looking udp_recvmsg alone does not establish a vulnerable implementation'}
    wanted={'net__ipv4__udp.c':['udp_lib_checksum_complete(skb)','skb_csum_unnecessary(skb)','skb_copy_and_csum_datagram_iovec','checksum_valid'],
            'net__core__datagram.c':['skb->csum_valid = !sum','skb_copy_and_csum_datagram_iovec','if (iov->iov_len < chunk)','if (flags & MSG_PEEK)','atomic_inc(&skb->users)','__skb_unlink(skb, &sk->sk_receive_queue)','kfree_skb(skb)']}
    for name,tokens in wanted.items():
        b=(SRC/name).read_bytes();record=next(x for x in manifest['files'] if x['local_file']==name)
        digest=hashlib.sha256(b).hexdigest()
        if digest!=record['sha256'] or len(b)!=record['bytes']:raise ValueError('Source changed since acquisition: '+name)
        text=b.decode('utf-8');result['sources'].append({'path':str((SRC/name).relative_to(ROOT)),'sha256':digest,'member_hash_matches':True,'token_lines':{t:token_lines(text,t) for t in tokens}})
    for relative in ['include/linux/skbuff.h','include/net/udp.h','net/core/skbuff.c']:
        matches=list(ROOT.rglob(Path(relative).name))
        flat=SRC/relative.replace('/','__')
        if flat.is_file() and flat not in matches:matches.append(flat)
        found=[str(p.relative_to(ROOT)) for p in matches]
        result['unresolved_dependencies'].append({'required_original_path':relative,'matching_filenames':found,'status':'missing in visible workspace' if not found else 'must inspect actual definition and provenance'})
    dependency_manifest=SRC/'candidate_A_dependency_sources.json'
    if dependency_manifest.exists():
        dm=json.loads(dependency_manifest.read_text(encoding='utf-8'))
        for item in dm['members']:
            data=(SRC/item['file']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=item['sha256'] or len(data)!=item['bytes']:raise ValueError('Dependency hash mismatch')
        sk=(SRC/'include__linux__skbuff.h').read_text(encoding='utf-8')
        uh=(SRC/'include__net__udp.h').read_text(encoding='utf-8')
        dg=(SRC/'net__core__datagram.c').read_text(encoding='utf-8')
        predicate='return ((skb->ip_summed & CHECKSUM_UNNECESSARY) || skb->csum_valid);' in sk
        wrapper='return !skb_csum_unnecessary(skb) &&' in uh and '__udp_lib_checksum_complete(skb);' in uh
        setter='skb->csum_valid = !sum;' in dg
        result['dependency_verification']={'member_hashes_match':True,'same_HTTP_ETag':dm.get('headers',{}).get('ETag')==manifest.get('http_headers',{}).get('ETag'),'predicate_reads_csum_valid':predicate,'udp_wrapper_uses_predicate':wrapper,'checksum_implementation_sets_csum_valid':setter,'not_a_kernel_execution':True}
        if predicate and wrapper and setter:
            result['verdict']='SOURCE_PATH_PROTECTED: successful truncated precheck sets csum_valid and selects bounded copy; original candidate-A second-check path is not established in the checked source. Not a claim that all S5 firmware or UDP paths are safe.'
            result['actual_source_predicate_model']=model(truncated=True,first_check_ok=True,initial_unnecessary=False,helper_sets_valid=True,predicate_uses_valid=True,local_fix=False)
    result['model_tests']=run_tests()
    result['next_evidence']=['complete archive validation', 'S5 exact running binary/config matching evidence',
                             'actual S5 socket caller type/flags and data reachability, without assuming G100 identity']
    return result

if __name__=='__main__':
    result=audit();out=SRC/'candidate_A_final_result.json'
    if out.exists():raise RuntimeError('Refusing to overwrite prior result')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
