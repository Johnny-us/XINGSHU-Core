#!/usr/bin/env python3
"""离线校验交接证据状态；不执行工具、写入或授权判断。"""
import argparse
import json
from pathlib import Path


def validate(record):
    failures = []
    pending = []
    task = record.get('task_id')
    version = record.get('work_version')
    source = record.get('source_thread_id')
    mode = record.get('mode')
    if not all(isinstance(x, str) and x for x in (task, version, source)):
        failures.append('IDENTITY_MISSING')
    if mode not in ('paired', 'codex_only'):
        failures.append('MODE_INVALID')
    if record.get('return_thread_id') != source:
        failures.append('RETURN_ENDPOINT_MISMATCH')
    for key in ('background', 'formal_binding_changed', 'old_task_resent'):
        if record.get(key) is not False:
            failures.append(key.upper() + '_NOT_FALSE')
    for key in ('navigation_requested', 'navigated'):
        if type(record.get(key)) is not bool:
            failures.append(key.upper() + '_NOT_BOOLEAN')
    if record.get('navigated') is True and record.get('navigation_requested') is not True:
        failures.append('UNAUTHORIZED_NAVIGATION')
    if record.get('legacy_dependency_affects_current') is not False:
        pending.append('LEGACY_DEPENDENCY_NOT_ISOLATED')
    if not isinstance(record.get('current_unknown_operations'), list):
        failures.append('CURRENT_UNKNOWN_LIST_MISSING')
    elif record['current_unknown_operations']:
        pending.append('CURRENT_OPERATION_UNKNOWN_NO_RETRY')
    if not isinstance(record.get('isolated_legacy_unknowns'), list):
        failures.append('ISOLATED_LEGACY_LIST_MISSING')
    expected_done = record.get('expected_completed')
    expected_next = record.get('expected_next_step')
    expected_stops = record.get('expected_stops')
    if not isinstance(expected_done, list) or not isinstance(expected_next, str):
        failures.append('EXPECTED_PROGRESS_MISSING')
    if not isinstance(expected_stops, list) or not all(isinstance(x, str) for x in expected_stops):
        failures.append('EXPECTED_STOPS_MISSING_OR_INVALID')
    ids = []
    for side in ('codex', 'web') if mode == 'paired' else ('codex',):
        value = record.get(side, {})
        if not isinstance(value, dict):
            failures.append(side.upper() + '_RECORD_INVALID')
            continue
        identity = value.get('thread_id')
        if not isinstance(identity, str) or not identity:
            pending.append(side.upper() + '_IDENTITY_PENDING')
        elif identity == source or identity in ids:
            failures.append(side.upper() + '_NOT_A_NEW_DISTINCT_CHAT')
        else:
            ids.append(identity)
        if value.get('task_id') != task or value.get('work_version') != version:
            failures.append(side.upper() + '_TASK_VERSION_MISMATCH')
        if side == 'web' and value.get('kind') != 'ordinary_web':
            failures.append('WEB_NOT_ORDINARY_WEB')
        for key in ('project_verified', 'input_read', 'accepted'):
            if value.get(key) is not True:
                pending.append(side.upper() + '_' + key.upper() + '_NOT_PROVEN')
        if value.get('already_done') != expected_done or value.get('next_step') != expected_next:
            failures.append(side.upper() + '_PROGRESS_MISMATCH')
        stops = value.get('stops')
        if not isinstance(stops, list) or stops != expected_stops:
            failures.append(side.upper() + '_STOPS_MISSING_OR_MISMATCH')
    for key in ('progress_preserved', 'same_task_version', 'return_read'):
        if record.get(key) is not True:
            pending.append(key.upper() + '_NOT_PROVEN')
    if record.get('return_mode') not in ('native', 'host_assisted'):
        failures.append('RETURN_MODE_UNDECLARED')
    status = 'REJECT' if failures else 'PENDING_RECOVERY' if pending else 'PASS_BOUNDED'
    return {'status': status, 'failures': failures, 'pending': pending,
            'evidence_kind': 'STATE_CONTRACT_CHECK_NOT_AUTHENTICITY_PROOF',
            'deployment_complete': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('record', nargs='?', help='已授权的最小 JSON 验收记录')
    parser.add_argument('--cases', help='离线合成反例集合，不是实际建窗')
    args = parser.parse_args()
    if bool(args.record) == bool(args.cases):
        parser.error('只指定 record 或 --cases')
    if args.cases:
        cases = json.loads(Path(args.cases).read_text(encoding='utf-8'))
        rows = []
        for case in cases:
            result = validate(case['record'])
            rows.append({'id': case['id'], 'expected': case['expected'],
                         'observed': result['status'], 'pass': result['status'] == case['expected']})
        payload = {'evidence_kind': 'SYNTHETIC_STATE_FIXTURE', 'cases': rows,
                   'total': len(rows), 'passed': sum(row['pass'] for row in rows)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0 if payload['passed'] == payload['total'] else 2)
    result = validate(json.loads(Path(args.record).read_text(encoding='utf-8')))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS_BOUNDED' else 2)


if __name__ == '__main__':
    main()
