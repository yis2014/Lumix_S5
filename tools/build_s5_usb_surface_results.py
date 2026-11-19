"""Offline aggregation/validation of already captured USB and WPD observations. No camera I/O."""
from pathlib import Path
import json,re,hashlib,datetime
R=Path(__file__).resolve().parent;D=R/'analysis'/'usb_surface_map'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(name):return [json.loads(x) for x in (D/name).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def wpd(name):
    p=D/name;s=p.read_text(encoding='utf-8-sig')
    def one(key):
        vals=re.findall('^'+re.escape(key)+'=(.*)$',s,re.M);return vals[-1].strip() if vals else None
    return {'log':name,'target_count':one('target_count'),'PID':one('usb_pid'),'model':one('model'),'firmware':one('firmware'),'advertised_vendor_opcodes':[x.strip() for x in re.findall(r'^vendor_opcode=(.*)$',s,re.M)],'complete':one('baseline_complete')=='true','error':one('ERROR')}
def mode(name,usbname,wpdname):
    rows=lines(usbname);summary=next(x for x in rows if x['event']=='candidate_summary');assert summary['count']==1 and summary['enumeration_complete'];assert rows[-1]['event']=='done' and rows[-1]['ok'];assert not any(x['event']=='error' for x in rows)
    r={'mode':name,'usb_log':usbname,'usb_log_sha256':sha(D/usbname),'WPD':wpd(wpdname),'events':[x for x in rows if x['event'] in ('target','device_descriptor','configuration','interface','endpoint','configuration_validated','done')]}
    target=next(x for x in rows if x['event']=='target');full=[x for x in rows if x['event']=='raw_configuration' and x['requested_bytes']>9];assert len(full)==target['configuration_count']==2
    for x in full:assert len(bytes.fromhex(x['hex']))==x['returned_bytes']==39
    r['configuration_hex_by_index']={str(x['configuration_index']):x['hex'] for x in full};return r

def main():
    a=mode('PC Tether','U2_tether_descriptors.jsonl','M0_current_wpd_baseline.txt');b=mode('PictBridge/PTP','U3_pictbridge_descriptors.jsonl','M1_pictbridge_wpd_baseline.txt')
    assert a['WPD']['PID']=='0x2382' and b['WPD']['PID']=='0x2374';assert a['WPD']['advertised_vendor_opcodes']==['0x9102','0x9103','0x9104'] and b['WPD']['advertised_vendor_opcodes']==[]
    same=a['configuration_hex_by_index']==b['configuration_hex_by_index'];assert same
    desc=json.loads((D/'D1_D2_description_verified.json').read_text(encoding='utf-8'));assert desc['child_count']==15 and desc['all_current_values_match_getter']
    for n,size in [('D1_photo_style_description.bin',1142),('D2_current_photo_style.bin',152)]:assert (D/n).stat().st_size==size
    for n in ['D1_photo_style_description_read.txt','D2_current_photo_style_read.txt']:
        s=(D/n).read_text(encoding='utf-8-sig');assert 'config_ptp_response=0x2001' in s and 'baseline_complete=true' in s
    result={'generated_at':datetime.datetime.now().astimezone().isoformat(),'scope':'Observed legitimate USB personalities and exact read requests only; not all hidden services/opcodes','modes_measured':[a,b],'same_configuration_bytes_across_modes':same,'no_vendor_class_interfaces_in_measured_descriptors':not any(x.get('class')==255 for m in [a,b] for x in m['events'] if x['event']=='interface'),'additional_mode_status':{'mass_storage':'NOT MEASURED; user elected Tether restoration rather than write-protected/no-card storage test','firmware_update':'NOT ENTERED OR PROBED','maintenance':'NOT ENTERED OR PROBED'},'new_getter':{'opcode':'0x9108','params':['0x02000010','0','0'],'PTP_response':'0x2001','bytes':1142,'description_children':15,'current_values_match_separate_9402_read':True,'PhotoStyle_options':desc['PhotoStyle_first_field_summary'],'has_diagnostic_or_memory_privilege_evidence':False},'restoration':{'first_attempt':wpd('M2_tether_restore.txt'),'second_attempt':wpd('M3_tether_restore_retry.txt'),'status':'NOT VERIFIED; final WPD enumeration found zero allowlisted targets and stopped before opening device/PTP requests'},'hypotheses':[{'id':'H1','hypothesis':'Only normal Tether/PTP functionality, no additional diagnostic surface','status':'COMPATIBLE with current descriptor observations but not proven exhaustive; unadvertised business getters already succeed'},{'id':'H2','hypothesis':'Firmware update path offers extra state reads','status':'UNTESTED; old secondary claims do not justify activating or probing upgrade actions'},{'id':'H3','hypothesis':'A handshake/key activates a hidden maintenance interface','status':'UNTESTED; no exact authorized read handshake or diagnostic implementation established; no bypass attempts'}],'LUT_evidence_status':'Identity/settings/property-description level only; no LUT coefficients, slot identity, ISP state or still-main-image consumer established','input_limitations':['No G100 executable plaintext or storage/runtime mapping','No original USBPcap/PCAP','S5M2 hardware compatibility unverified'],'observed_host_tool_issue':'U1 stopped on empty-port ConnectionIndex output; SDK marks that field INPUT. U2 accepts only fully validated canonical empty outputs; connected-device checks remain strict. This is not a camera denial or driver-permission bypass.'}
    with (D/'usb_surface_results.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    validation={'status':'PASS for captured data/aggregation only','checks':['Two USB modes independently have complete enumeration/one target/validated two configurations','Configuration descriptor bytes exactly equal across modes','Expected PIDs and observed advertised-opcode lists match','9108/9402 payload sizes/PTP OK and 15 current-value cross-checks valid','Restoration NOT verified retained as failure/uncertainty, not overwritten'],'files':[{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(D.iterdir()) if p.is_file()]}
    with (D/'surface_artifact_validation.json').open('x',encoding='utf-8') as f:json.dump(validation,f,ensure_ascii=False,indent=2)
    print(json.dumps({'modes':['Tether2382','PictBridge2374'],'configuration_bytes_equal':same,'description_child_values_verified':15,'restoration':result['restoration']['status'],'artifacts_hashed':len(validation['files'])},indent=2))
if __name__=='__main__':main()
