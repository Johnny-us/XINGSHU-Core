"""Build and genuinely exercise the owned synthetic app. Failed packages are deleted."""
import hashlib,json,os,plistlib,shutil,socket,subprocess,sys,time,uuid,tempfile,platform
from pathlib import Path

SOURCE_ROOT=Path(__file__).resolve().parent
ROOT=None
TASK='XS-SYNTHETIC-RUNNER-EXAMPLE'
BUNDLE_ID='org.xingshu.examples.localrunner.synthetic'
APP_NAME='星枢本地运行器（假资料示例）.app'
strict_json=json.loads

BUILD=None
def owned_remove(p):
    assert p.parent==BUILD and p.name==APP_NAME and not p.is_symlink()
    if p.exists():shutil.rmtree(p)

def run(args,timeout=25,expected=0):
    p=subprocess.Popen([str(a) for a in args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       cwd=str(ROOT),env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(Path.home()),'LANG':'en_US.UTF-8','TMPDIR':'/private/tmp'},start_new_session=True)
    try:out,err=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        import signal
        os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate();raise RuntimeError('OWNED_PROCESS_TIMEOUT')
    assert len(out)<=131072 and len(err)<=131072,'OUTPUT_LIMIT'
    assert p.returncode==expected,{'argv':[str(x) for x in args],'exit':p.returncode,'stderr':err.decode('utf-8','replace')[:2500],'stdout':out.decode('utf-8','replace')[:1200]}
    try:os.killpg(p.pid,0)
    except ProcessLookupError:pass
    else:raise RuntimeError('OWNED_PROCESS_GROUP_STILL_PRESENT')
    return out,err,{'pid':p.pid,'returncode':p.returncode,'reaped':True,'process_group_absent':True}

def main():
    assert not BUILD.is_symlink()
    BUILD.mkdir(exist_ok=True)
    app=BUILD/APP_NAME
    if app.exists():owned_remove(app)
    if (ROOT/'test-results.json').exists():
        with (ROOT/'build-history.jsonl').open('a') as f:f.write(json.dumps(json.loads((ROOT/'test-results.json').read_text()),ensure_ascii=False)+'\n')
        (ROOT/'test-results.json').unlink()
    if (ROOT/'latest-build-result.json').exists():
        with (ROOT/'build-history.jsonl').open('a') as f:f.write((ROOT/'latest-build-result.json').read_text().strip().replace('\n',' ')+'\n')
        (ROOT/'latest-build-result.json').unlink()
    checks=ROOT/'.checks';checks.mkdir(exist_ok=True)
    canary=checks/'outside-canary.txt';canary.write_text('synthetic outside read canary; no personal information\n')
    outside_write=checks/'outside-write.txt'
    if outside_write.exists():
        assert outside_write.is_file() and outside_write.stat().st_size==0
        outside_write.unlink()
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    run_id=uuid.uuid4().hex;processes=[];cases=[];observations=[]
    def check(name,condition):
        assert condition,name
        cases.append(name)
    try:
        contents=app/'Contents';resources=contents/'Resources';macos=contents/'MacOS'
        resources.mkdir(parents=True);macos.mkdir()
        fixture=(ROOT/'fixtures/fixture.md').read_bytes();(resources/'fixture.md').write_bytes(fixture)
        plist={'CFBundleIdentifier':BUNDLE_ID,'CFBundleName':'星枢本地运行器（假资料测试版）','CFBundleDisplayName':'星枢本地运行器（假资料测试版）','CFBundleExecutable':'XINGSHULocalRunner','CFBundlePackageType':'APPL','CFBundleVersion':'1','CFBundleShortVersionString':'0.1.0','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,'XSTestRunID':run_id,'XSFixtureSHA256':hashlib.sha256(fixture).hexdigest(),'XSOutsideCanary':str(canary),'XSOutsideWrite':str(outside_write),'XSLoopbackPort':listener.getsockname()[1],'XSSyntheticOnly':True}
        (contents/'Info.plist').write_bytes(plistlib.dumps(plist))
        ent=BUILD/'entitlements.plist';ent.write_bytes(plistlib.dumps({'com.apple.security.app-sandbox':True}))
        binary=macos/'XINGSHULocalRunner'
        sdk_raw,_,sdk_process=run(['/usr/bin/xcrun','--show-sdk-path']);processes.append({'kind':'native-sdk-location',**sdk_process})
        sdk=Path(sdk_raw.decode().strip());assert sdk.is_dir()
        out,err,pr=run(['/Library/Developer/CommandLineTools/usr/bin/clang','-isysroot',sdk,'-fobjc-arc','-Wall','-Wextra','-Werror=return-type','-arch',platform.machine(),'-mmacosx-version-min=14.0','-framework','Cocoa',ROOT/'src/main.m','-o',binary],timeout=45)
        processes.append({'kind':'compile',**pr});(BUILD/'compiler.txt').write_bytes(err)
        _,_,pr=run(['/usr/bin/codesign','--force','--sign','-','--entitlements',ent,app]);processes.append({'kind':'sign-own-app',**pr})
        _,_,pr=run(['/usr/bin/codesign','--verify','--strict',app]);processes.append({'kind':'verify-own-signature',**pr})
        def call(*args,expected=0):
            raw,err,pr=run([binary,*args],expected=expected)
            processes.append({'kind':'native-test','arguments':list(args),**pr})
            lines=[strict_json(line) for line in raw.splitlines() if line]
            obj=lines[-1]
            assert type(obj) is dict
            assert all(x.get('event')=='FIXTURE_DISCLOSURE' and x.get('synthetic_only') is True and x.get('source_id')=='synthetic:fixture-v1' for x in lines[:-1])
            observations.append({'arguments':list(args),'raw_stdout_utf8':raw.decode('utf-8'),'stdout_sha256':hashlib.sha256(raw).hexdigest(),**pr})
            if obj.get('code')=='STATUS':assert obj['handoff']['artifact_type']=='TEST_EVIDENCE'
            if obj.get('code')=='SYNTHETIC_SCENARIO_RESULT':assert obj['status']['handoff']['artifact_type']=='TEST_EVIDENCE'
            obj['_observed_disclosures']=lines[:-1]
            return obj
        probe=call('--sandbox-probe')
        for k in ['external_read_denied','external_write_denied','loopback_denied']:check(k,probe[k] is True)
        check('connect_syscall_actually_attempted',probe['socket_created'] is True and probe['connect_attempted'] is True and probe['connect_result']==-1)
        check('outside_canary_unchanged',canary.read_text()=='synthetic outside read canary; no personal information\n')
        check('outside_write_not_created',not outside_write.exists())
        life=call('--scenario','lifecycle');codes=[e['code'] for e in life['events']]
        expected=['READ_DENIED','STARTED','READ_DENIED','TEST_ONLY_GRANTED_ONCE','FIXTURE_READ_OK','READ_DENIED','TEST_ONLY_GRANTED_ONCE','REVOKED','READ_DENIED','STOPPED_AND_REVOKED','READ_DENIED']
        check('real_lifecycle_exact_sequence',codes==expected)
        result=life['events'][4]
        check('fixture_content_exact',len(life['_observed_disclosures'])==1 and life['_observed_disclosures'][0]['content'].encode()==fixture)
        check('fixture_citation_and_hash',result['citation']=='bundle://fixture.md' and result['sha256']==plist['XSFixtureSHA256'])
        check('stopped_and_revoked',life['status']['running_in_this_process'] is False and life['status']['usable_in_this_process'] is False)
        check('real_adapters_disabled',all(life['status'][k] is False for k in ['real_ai_connected','p5_connected','openwiki_connected']))
        check('no_background_helpers',life['status']['background_helpers']==0)
        fresh=call('--scenario','after-reopen')
        check('new_process_cannot_reuse_permission',fresh['events'][1]['code']=='READ_DENIED')
        check('task_progress_persisted',fresh['events'][0]['task_progress']=='read_complete')
        concurrent=call('--scenario','concurrent');cc=[x['code'] for x in concurrent['events']]
        check('concurrent_single_disclosure',cc.count('FIXTURE_READ_OK')==1 and cc.count('READ_DENIED')==1 and len(concurrent['_observed_disclosures'])==1)
        inflight=call('--scenario','revoke-inflight');ic=[x['code'] for x in inflight['events']]
        check('inflight_revoke_blocks_new_disclosure','REVOKED_BEFORE_DISCLOSURE' in ic and 'FIXTURE_READ_OK' not in ic and not inflight['_observed_disclosures'])
        publication=call('--scenario','revoke-at-publication');rev=next(e for e in publication['events'] if e['code']=='REVOKED')
        check('revocation_returns_only_after_earlier_publication',len(publication['_observed_disclosures'])==1 and publication['_observed_disclosures'][0]['emitted_at']<=rev['returned_at'])
        check('after_confirmed_revoke_no_new_disclosure',publication['events'][-1]['code']=='READ_DENIED')
        expire_publication=call('--scenario','expire-at-publication')
        check('expiry_before_actual_publication_denied',expire_publication['events'][0]['code']=='EXPIRED_BEFORE_DISCLOSURE' and not expire_publication['_observed_disclosures'])
        expiry=call('--scenario','expiry')
        check('expired_permission_denied',expiry['events'][0]['code']=='READ_DENIED')
        prepared=call('--scenario','prepare-reopen');reopen=call('--scenario','after-reopen')
        check('unspent_permission_not_restored',reopen['events'][0]['task_progress']=='awaiting_resume' and reopen['events'][0]['usable_in_this_process'] is False and reopen['events'][1]['code']=='READ_DENIED')
        crashed=call('--scenario','crash',expected=23);after_crash=call('--scenario','after-reopen')
        check('abnormal_exit_does_not_restore_authority',after_crash['events'][0]['usable_in_this_process'] is False and after_crash['events'][1]['code']=='READ_DENIED')
        inspect=call('--inspect');state=Path(inspect['state_path'])
        check('state_is_new_sandbox_container',str(state).startswith(str(Path.home()/'Library'/'Containers'/BUNDLE_ID/'Data')+'/') and state.parent.name==run_id)
        raw=state.read_bytes();state.write_bytes(raw+b'\n')
        corrupt=call('--inspect',expected=2)
        check('corrupt_state_fails_closed',corrupt['code']=='STATE_INTEGRITY_FAILURE')
        check('corrupt_state_not_auto_repaired',state.read_bytes()==raw+b'\n')
        state.write_bytes(raw)  # Restore only this test's own synthetic state, not runtime authority.
        denied=call('--approve',expected=2)
        check('no_real_approval_cli',denied['code']=='UNKNOWN_ARGUMENTS')
        fixture_path=resources/'fixture.md'
        try:
            fixture_path.write_bytes(fixture+b'\n')
            changed=call('--scenario','lifecycle')
            changed_codes=[e['code'] for e in changed['events']]
            check('source_change_blocks_disclosure','FIXTURE_CHANGED' in changed_codes and 'FIXTURE_READ_OK' not in changed_codes and not changed['_observed_disclosures'])
        finally:fixture_path.write_bytes(fixture)
        _,_,verify_process=run(['/usr/bin/codesign','--verify','--strict',app]);processes.append({'kind':'verify-final-restored-package',**verify_process})
        final=call('--inspect');check('final_state_no_usable_authority',final['usable_in_this_process'] is False)
        check('handoff_is_synthetic_test_evidence',final['handoff']['artifact_type']=='TEST_EVIDENCE')
        evidence={'task_id':TASK,'status':'PASS_NATIVE_SYNTHETIC_PACKAGE_TESTS','run_id':run_id,'checks_passed':len(cases),'checks':cases,'probe':probe,'lifecycle_codes':codes,'concurrency_codes':cc,'inflight_codes':ic,'processes':processes,'native_observations':observations,'last_status':final,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((ROOT/'src/main.m').read_bytes()).hexdigest(),'human_approval_proven':False,'real_ai_connected':False,'personal_source_reads':0,'formal_A1_accepted':False,'production_ready':False,'gui_verified':False,'failed_packages_retained':0}
        (ROOT/'test-results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':evidence['status'],'checks':len(cases),'check_names':cases,'app':str(app),'binary_sha256':evidence['binary_sha256'],'scope':'SYNTHETIC_ONLY_NOT_FORMAL_A1','human_approval_proven':False,'real_ai_connected':False,'personal_source_reads':0},ensure_ascii=False))
    except BaseException as e:
        owned_remove(app)
        failure={'status':'BUILD_OR_TEST_FAILED_PACKAGE_REMOVED','exception':str(e),'checks_passed_before_failure':cases,'processes':processes,'failed_packages_retained':0}
        (ROOT/'latest-build-result.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(failure,ensure_ascii=False));raise
    finally:listener.close()

if __name__=='__main__':
    if sys.platform!='darwin':raise SystemExit('This native example requires macOS; use the public-probe example on other systems.')
    if len(sys.argv)!=1:raise SystemExit('No activation, install or approval arguments are supported.')
    with tempfile.TemporaryDirectory(prefix='xingshu-synthetic-example-') as work:
        ROOT=Path(work);BUILD=ROOT/'.build'
        shutil.copytree(SOURCE_ROOT/'src',ROOT/'src')
        shutil.copytree(SOURCE_ROOT/'fixtures',ROOT/'fixtures')
        main()  # Both successful and failed app bundles remain temporary and are cleaned.
