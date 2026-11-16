#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四类故障注入主脚本（四类故障注入：ADB 断开、SAF 拒绝、会话池占满、DAG 环形依赖）。

支持四类故障：
  adb_disconnect  断开 adb 服务端 / 设备连接，运行期间恢复
  saf_deny        撤销存储权限并拒绝 SAF 授权相关 appop
  pool_exhaust    占满 adb 会话池（N 个常驻 shell 会话），运行期间释放
  dag_cycle       人为构造环形依赖（在场景依赖图上加一条回边），运行后还原

默认只依赖标准库；dag_cycle 需要 pyyaml。
首次使用请先 --repeat 1 --dry-run 校验环境，再正式跑。

示例：
  python3 experiments/paper/fault_inject.py --fault adb_disconnect --repeat 20 \
      --out output/paper/table8_fault_adb_saf_pool/adb_disconnect
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAULTS = ('adb_disconnect', 'saf_deny', 'pool_exhaust', 'dag_cycle')
DEP_KEYS = ('depends_on', 'deps', 'dependencies', 'predecessors', 'parents')
ATOM_KEYS = ('atoms', 'nodes', 'tasks', 'steps')


def run(argv, check=False, timeout=600):
    p = subprocess.run(argv, shell=False, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout, cwd=REPO)
    if check and p.returncode != 0:
        raise RuntimeError('%s 失败: %s' % (' '.join(argv), p.stderr.strip()[:300]))
    return p


# ---------------- 故障动作 ----------------

def apply_adb_disconnect(dev, args):
    run(['adb', '-s', dev, 'kill-server'])
    return lambda: run(['adb', 'start-server']) and run(['adb', '-s', dev, 'wait-for-device'], timeout=180)


def apply_saf_deny(dev, args):
    if not args.pkg:
        raise SystemExit('saf_deny 需要 --pkg（被测应用包名）')
    run(['adb', '-s', dev, 'shell', 'pm', 'revoke', args.pkg, 'android.permission.READ_EXTERNAL_STORAGE'])
    run(['adb', '-s', dev, 'shell', 'pm', 'revoke', args.pkg, 'android.permission.WRITE_EXTERNAL_STORAGE'])
    for op in ('MANAGE_EXTERNAL_STORAGE', 'READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE'):
        run(['adb', '-s', dev, 'shell', 'appops', 'set', args.pkg, op, 'deny'])

    def release():
        for op in ('MANAGE_EXTERNAL_STORAGE', 'READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE'):
            run(['adb', '-s', dev, 'shell', 'appops', 'set', args.pkg, op, 'allow'])
        for perm in ('android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'):
            run(['adb', '-s', dev, 'shell', 'pm', 'grant', args.pkg, perm])
    return release


def apply_pool_exhaust(dev, args):
    procs = []
    for _ in range(args.pool):
        procs.append(subprocess.Popen(['adb', '-s', dev, 'shell', 'sleep 120'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(3)

    def release():
        for p_ in procs:
            try:
                p_.terminate()
            except Exception:
                pass
        for p_ in procs:
            try:
                p_.wait(timeout=5)
            except Exception:
                pass
        run(['adb', '-s', dev, 'shell', 'echo', 'pool_released'])
    return release


def apply_dag_cycle(dev, args):
    try:
        import yaml
    except ImportError:
        raise SystemExit('dag_cycle 需要 pyyaml：python3 -m pip install --user pyyaml')
    src = args.scenario_yaml or os.path.join(REPO, 'config', 'scenarios', '%s.yaml' % args.scenario)
    if not os.path.exists(src):
        raise SystemExit('找不到场景配置: %s（用 --scenario-yaml 指定）' % src)
    with open(src, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    atoms = None
    for k in ATOM_KEYS:
        if isinstance(data, dict) and isinstance(data.get(k), list) and len(data[k]) > 1:
            atoms = data[k]
            break
    if atoms is None:
        raise SystemExit('未在 %s 中识别到原子列表，已知顶层键: %s' % (src, list(data.keys()) if isinstance(data, dict) else type(data)))
    dep_key = next((k for k in DEP_KEYS if isinstance(atoms[0], dict) and k in atoms[0]), None)
    if dep_key is None:
        raise SystemExit('未识别依赖字段，首个原子键: %s' % list(atoms[0].keys()))
    # depends_on 语义为“前驱”，成环需让首节点反过来依赖末节点（末节点依赖首节点只是冗余边）
    first_id = atoms[0].get('id', atoms[0].get('name', 0))
    last_id = atoms[-1].get('id', atoms[-1].get('name'))
    back = atoms[0].setdefault(dep_key, [])
    if not isinstance(back, list):
        raise SystemExit('依赖字段不是列表: %s' % dep_key)
    if last_id not in back:
        back.append(last_id)
    tmp = os.path.join(tempfile.mkdtemp(prefix='dagcycle_'), '%s_cycle.yaml' % args.scenario)
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print('[dag_cycle] 已生成环 %s(依赖)->%s ... ->%s: %s' % (first_id, last_id, first_id, tmp))
    return (lambda: shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)), tmp


# ---------------- 运行证据采集 ----------------

def newest_json(root, since):
    best = None
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith('.json'):
                continue
            fp = os.path.join(dirpath, name)
            if os.path.getmtime(fp) >= since:
                if best is None or os.path.getmtime(fp) > os.path.getmtime(best):
                    best = fp
    return best


def read_metrics(path):
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return {'success_rate': d.get('success_rate'), 'success_atoms': d.get('success_atoms'),
                'total_nodes': d.get('total_nodes'), 'total_time': d.get('total_time')}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fault', required=True, choices=FAULTS)
    ap.add_argument('--repeat', type=int, default=20)
    ap.add_argument('--out', required=True)
    ap.add_argument('--device', default='emulator-5554')
    ap.add_argument('--pkg', default=None, help='saf_deny 需要的被测应用包名')
    ap.add_argument('--pool', type=int, default=8)
    ap.add_argument('--scenario', default='baseline_50', help='config/scenarios 下的场景名')
    ap.add_argument('--scenario-yaml', default=None)
    ap.add_argument('--api', type=int, default=33)
    ap.add_argument('--w', type=int, default=1, help='并发上限，传给 --max-concurrency')
    ap.add_argument('--scheduler', default='priority', choices=['priority', 'fifo', 'basic'])
    ap.add_argument('--adapter', default='on', choices=['on', 'off'])
    ap.add_argument('--run-out', default='output/paper/runs')
    ap.add_argument('--cmd', default=None,
                    help='自定义被测命令模板，{yaml} {api} {w} 会被替换；默认调用 run_parallel.py')
    ap.add_argument('--result-root', default=None, help='结果JSON检索根目录，默认取 --run-out')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows, yaml_override = [], None

    for i in range(1, args.repeat + 1):
        t0 = time.time()
        inject, extra_yaml, release = None, None, (lambda: None)
        fault_ok = True
        try:
            if args.fault == 'adb_disconnect':
                release = apply_adb_disconnect(args.device, args)
            elif args.fault == 'saf_deny':
                release = apply_saf_deny(args.device, args)
            elif args.fault == 'pool_exhaust':
                release = apply_pool_exhaust(args.device, args)
            elif args.fault == 'dag_cycle':
                release, extra_yaml = apply_dag_cycle(args.device, args)
        except Exception as e:
            fault_ok = False
            print('[%d/%d] 注入失败: %s' % (i, args.repeat, e))
        inject = time.time() - t0

        if args.dry_run:
            release()
            print('[%d/%d] dry-run 完成，注入耗时 %.1fs，未执行被测命令' % (i, args.repeat, inject))
            rows.append({'run': i, 'fault': args.fault, 'inject_s': round(inject, 2),
                         'rc': None, 'success_rate': None, 'dry_run': True})
            continue

        if fault_ok:
            yaml_path = extra_yaml or args.scenario_yaml or os.path.join(
                REPO, 'config', 'scenarios', '%s.yaml' % args.scenario)
            if args.cmd:
                cmd = (args.cmd.replace('{yaml}', yaml_path)
                       .replace('{api}', str(args.api)).replace('{w}', str(args.w)))
                argv = cmd.split()
            else:
                argv = [sys.executable, 'experiments/paper/run_parallel.py', yaml_path,
                        '--api', str(args.api), '--max-concurrency', str(args.w),
                        '--scheduler', args.scheduler, '--adapter', args.adapter,
                        '--out', args.run_out, '--tag', 'fault_%s_%d' % (args.fault, i)]
            t1 = time.time()
            proc = run(argv, timeout=args.timeout)
            dur = time.time() - t1
            root = args.result_root or args.run_out
            got = newest_json(os.path.join(REPO, root), t1)
            m = read_metrics(got)
        else:
            dur, proc, m = 0.0, None, {}

        release()
        row = {'run': i, 'fault': args.fault, 'inject_s': round(inject, 2),
               'run_s': round(dur, 2), 'rc': None if proc is None else proc.returncode,
               'success_rate': m.get('success_rate'), 'success_atoms': m.get('success_atoms'),
               'total_nodes': m.get('total_nodes'), 'result_json': os.path.basename(got) if not args.dry_run and fault_ok else '',
               'stderr_tail': (proc.stderr.strip().splitlines()[-1][:120] if proc and proc.stderr.strip() else '')}
        rows.append(row)
        print('[%d/%d] rc=%s success_rate=%s 耗时=%.1fs' % (i, args.repeat, row['rc'], row['success_rate'], row['run_s']))
        time.sleep(2)

    csvp = os.path.join(args.out, 'inject_log.csv')
    keys = sorted({k for r in rows for k in r})
    with open(csvp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r.get('success_rate') is not None and float(r['success_rate']) >= 0.999)
    summary = {'fault': args.fault, 'repeat': args.repeat, 'injected': len(rows),
               'full_success': ok, 'completion_rate': round(ok / max(1, len(rows)), 4),
               'device': args.device, 'scenario': args.scenario, 'w': args.w,
               'out': os.path.abspath(args.out)}
    with open(os.path.join(args.out, 'inject_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print('\n汇总: %s 注入 %d 次，场景完整执行 %d 次，完成率 %.1f%%'
          % (args.fault, summary['injected'], ok, 100 * summary['completion_rate']))
    print('明细:', os.path.abspath(csvp))


if __name__ == '__main__':
    main()
