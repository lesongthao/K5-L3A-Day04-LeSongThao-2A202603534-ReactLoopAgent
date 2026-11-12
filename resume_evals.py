"""Chay lai case unscored bang runner/judge goc, giu nguyen case da cham.

Dung: python -X utf8 resume_evals.py eval_before.json
Giu nguyen agent va cau hinh; ho tro ca bai chinh va bonus.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from providers import Provider
from run_evals_slow import CallPacer, paced_complete

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'evals'))
from run_evals import run_case
from grading import bonus_points, grade_case, summarize


def save_report(path, report):
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=path.parent,
        prefix='eval_results_resume_', suffix='.tmp', delete=False
    ) as temporary:
        json.dump(report, temporary, ensure_ascii=False, indent=2)
        temporary.write('\n')
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def rerun_unscored(case, args, previous):
    if previous['result'].get('status') == 'completed':
        updated = dict(previous)
        judge = Provider(args.judge_provider, args.judge_model)
        updated['grade'] = grade_case(case, previous['result'], judge)
        return updated
    return run_case(case, args)


def resume_report(report, source_cases, run_one, save):
    config = report['config']
    if config.get('dataset') not in ('core', 'bonus'):
        raise ValueError('Dataset phai la core hoac bonus.')
    by_id = {case['id']: case for case in source_cases}
    if [item['id'] for item in report['cases']] != [case['id'] for case in source_cases]:
        raise ValueError('File phai chua du cac case, dung thu tu bo eval goc.')
    for item in report['cases']:
        source = by_id[item['id']]
        if item['question'] != source['question'] or item['expected'] != source['expected']:
            raise ValueError('Cau hoi/expected khac bo eval goc; khong the chay tiep.')

    args = SimpleNamespace(**config, bonus=config['dataset'] == 'bonus')
    for index, item in enumerate(report['cases']):
        if item['grade'].get('status') == 'scored' and item['grade'].get('score') is not None:
            continue
        print(f"Chay lai {item['id']} (truoc do chua cham duoc)...", flush=True)
        updated = run_one(by_id[item['id']], args, item)
        report['cases'][index] = updated
        report['summary'] = summarize(report['cases'])
        if args.bonus:
            report['summary']['bonus_points_0_15'] = bonus_points(report['summary']['score_0_100'], True)
        save(report)
        grade = updated['grade']
        print(
            f"{item['id']}: {grade.get('score')} ({grade['status']}); "
            f"da cham {report['summary']['scored_cases']}/{report['summary']['total_cases']}",
            flush=True
        )
        if grade.get('status') == 'unscored':
            print(grade.get('reason', 'Chua co ly do.'), flush=True)
    return report


def check_sources(path, report):
    files = [
        'agent.py', 'providers.py', 'status_tools.py', 'evals/cases.json',
        'evals/scenarios.py', 'evals/grading.py',
        'fixtures/github.json', 'fixtures/cloudflare.json'
    ]
    if report['config'].get('dataset') == 'bonus':
        files += [
            'bonus/tools.py', 'bonus/cases.json', 'bonus/fixtures/vercel.json',
            'bonus/fixtures/npm.json', 'bonus/fixtures/digitalocean.json'
        ]
    state = {
        'config': report['config'],
        'source_hashes': {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in files
        }
    }
    state_path = path.with_name('eval_results_state_' + path.stem + '.json')
    if state_path.exists():
        if json.loads(state_path.read_text(encoding='utf-8')) != state:
            raise ValueError('Code/du lieu/cau hinh da thay doi tu lan chay tiep truoc. Khong ghep ket qua.')
    else:
        save_report(state_path, state)


def main():
    parser = argparse.ArgumentParser(description='Chay tiep rieng case unscored, giu nguyen cau hinh.')
    parser.add_argument('report', type=Path)
    path = parser.parse_args().report.resolve()
    report = json.loads(path.read_text(encoding='utf-8'))
    folder = 'bonus' if report['config'].get('dataset') == 'bonus' else 'evals'
    source_cases = json.loads((ROOT / folder / 'cases.json').read_text(encoding='utf-8'))
    check_sources(path, report)
    original_complete = Provider.complete
    Provider.complete = paced_complete(original_complete, CallPacer())
    try:
        resume_report(report, source_cases, rerun_unscored, lambda result: save_report(path, result))
    finally:
        Provider.complete = original_complete
    summary = report['summary']
    print(f"Diem: {summary['score_0_100']}/100; da cham {summary['scored_cases']}/{summary['total_cases']}. File: {path.name}")
    return 0 if summary['score_0_100'] is not None else 1


if __name__ == '__main__':
    sys.exit(main())
