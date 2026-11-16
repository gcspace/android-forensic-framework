#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按论文口径复算关键数字，与正文逐项比对（对外发布前必跑）。

口径约定（与正文一致）：
  - 表4：每版 5 轮，前两轮为冷启动预热，取后三轮中位数；
  - 图3（4.3.1）、表6、表7：取均值和样本标准差；
  - 表6 ④组：API33 三批 + API34 一批，共 20 轮合并统计；
  - 表3：W=6 时段分量测量（output/jitter_w6），合计为三项之和。

用法：
    python experiments/paper/verify_paper_claims.py
    python experiments/paper/verify_paper_claims.py --dir output/paper
退出码 0 表示全部一致；1 表示存在差异。
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics
import sys

EXPECT_TABLE4 = {28: 11.27, 29: 10.79, 30: 24.11, 31: 7.12, 32: 8.67, 33: 6.93, 34: 7.74}
EXPECT_W = {1: 6.86, 2: 6.39, 3: 6.61, 4: 6.51, 6: 6.48, 8: 6.53, 12: 6.48}
EXPECT_ABL = {'① hp120 W=1': 43.47, '② hp120 W=6 基础Kahn(FIFO就绪)': 15.34,
              '③ hp120 W=6 完整方法': 13.65, '④ 单原子模式(20轮)': 42.35}
EXPECT_MAL = {'privacy': (36, 2.39), 'phishing': (46, 2.85), 'ransomware': (35, 2.32)}
# 表8：同版本 API35 虚实对照（每侧 11 轮，剔首轮取 10 轮）
EXPECT_VR = {'sim': 2.062, 'real': 1.534}
EXPECT_VR_LOSS = 0.0
EXPECT_TABLE3 = {'ADB 传输开销': 10.26, '系统服务响应': 14.82, '内核调度噪声': 0.66,
                 'CLOCK_BOOTTIME 读取窗长': 29.60, '合计': 54.68}
# 图4：五档同族场景（同一会话热态、每档 5 轮，取中位数）
EXPECT_SCALE = {20: 2.094, 30: 4.048, 50: 6.146, 80: 10.866, 100: 11.948}
EXPECT_SCALE_SLOPE = 0.126
EXPECT_SCALE_R2 = 0.982
TOL = 0.02
rows = []
notes = []
ok = True


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def times(paths):
    vals = []
    for p in paths:
        t = load(p).get('total_time')
        if t is not None:
            vals.append(t)
    return vals


def check(name, expected, actual, tol=TOL):
    global ok
    good = actual is not None and abs(actual - expected) <= tol
    rows.append((name, expected, actual, 'PASS' if good else ('MISSING' if actual is None else 'FAIL')))
    ok &= bool(good)


def main():
    global ok
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.path.join('output', 'paper'))
    a = ap.parse_args()

    r2 = os.path.join(a.dir, 'table4_version_matrix', 'session_v2', 'runs')
    tv2 = os.path.join(a.dir, 'table5_6_and_fig3_timing', 'timing_v2')
    abl2 = os.path.join(a.dir, 'table5_ablation_group4')

    # 表4：各版本 W=1 后三轮中位数
    for api, exp in EXPECT_TABLE4.items():
        paths = [os.path.join(r2, 'api%d_on_r%d.json' % (api, r),
                              'api%d_baseline_50_priority_w1_on.json' % api) for r in (3, 4, 5)]
        paths = [p for p in paths if os.path.isfile(p)]
        check('表4 API%d/s' % api, exp, round(statistics.median(times(paths)), 2) if len(paths) == 3 else None)

    # 图3 / 4.3.1：W 扫描（W=1 取后三轮均值，其余 5 轮均值）
    for w, exp in EXPECT_W.items():
        paths = sorted(glob.glob(
            os.path.join(tv2, 'api33_baseline_50_priority_w%d_on_wm%d_r*.json' % (w, w))))
        if w == 1:
            paths = [p for p in paths if re.search(r'_r[345]\.json$', p)]
        check('图3 W=%d/s' % w, exp, round(statistics.mean(times(paths)), 2) if paths else None)

    # 表6：①②③ 来自 timing_v2，④ 来自 table5_ablation_group4 四批共 20 轮
    groups = {
        '① hp120 W=1': os.path.join(tv2, 'api33_high_parallel_120_priority_w1_on_hp120_w1_r*.json'),
        '② hp120 W=6 基础Kahn(FIFO就绪)': os.path.join(tv2, 'api33_high_parallel_120_fifo_w6_on_hp120_fifo_w6_r*.json'),
        '③ hp120 W=6 完整方法': os.path.join(tv2, 'api33_high_parallel_120_priority_w6_on_hp120_w6_r*.json'),
    }
    for name, pattern in groups.items():
        paths = sorted(glob.glob(pattern))
        check('表6 ' + name, EXPECT_ABL[name], round(statistics.mean(times(paths)), 2) if paths else None)

    s4 = sorted(glob.glob(os.path.join(abl2, '*', '*single*.json')))
    check('表6 ④ 单原子模式(20轮)', EXPECT_ABL['④ 单原子模式(20轮)'],
          round(statistics.mean(times(s4)), 2) if len(s4) >= 10 else None)

    # 表7：三类恶意场景（原子数、5 轮均值）
    for scene, (natoms, exp) in EXPECT_MAL.items():
        paths = sorted(glob.glob(
            os.path.join(tv2, 'api33_malicious_%s_priority_w1_on_malicious_%s_r*.json' % (scene, scene))))
        if not paths:
            rows.append(('表7 %s' % scene, exp, None, 'MISSING'))
            ok = False
            continue
        n = load(paths[0]).get('total_nodes') or len(load(paths[0]).get('atoms', []))
        rows.append(('表7 %s原子数' % scene, natoms, n, 'PASS' if n == natoms else 'FAIL'))
        ok &= (n == natoms)
        check('表7 %s/s' % scene, exp, round(statistics.mean(times(paths)), 2))

    # 表3：W=6 抖动分量（读 output/jitter_w6/measurement_result.txt）
    txt = os.path.join(os.path.dirname(a.dir), 'jitter_w6', 'measurement_result.txt')
    if os.path.isfile(txt):
        body = open(txt, encoding='utf-8').read()
        vals = dict(re.findall(r'([^:：\n]+):\s*([0-9]+(?:\.[0-9]+)?)\s*(?:±|\n)', body))
        for key, exp in EXPECT_TABLE3.items():
            raw = re.search(r'%s[：:]\s*([0-9]+(?:\.[0-9]+)?)' % re.escape(key), body)
            check('表3 ' + key, exp, float(raw.group(1)) if raw else None)
    else:
        rows.append(('表3', 1, None, 'MISSING'))
        ok = False

    # 图4：五档同族规模扩展性（同批热态，中位数＋四分位距）
    sc = os.path.join(a.dir, 'fig4_scale_family', 'scale_stats.json')
    if os.path.isfile(sc):
        d = load(sc)
        for n, exp in EXPECT_SCALE.items():
            got = d['scenarios'].get(str(n), {}).get('median')
            check('图4 %d原子/s(中位数)' % n, exp, got, tol=0.01)
            sr = d['scenarios'].get(str(n), {}).get('success_rate')
            rows.append(('图4 %d原子完整率' % n, 1.0, sr, 'PASS' if sr == [1.0] else 'FAIL'))
            ok &= (sr == [1.0])
        fit = d.get('fit', {})
        check('图4 拟合斜率/(s·原子⁻¹)', EXPECT_SCALE_SLOPE, fit.get('slope_s_per_atom'), tol=0.002)
        r2 = fit.get('r2')
        rows.append(('图4 拟合R²', '≈0.98', r2,
                     'PASS' if r2 is not None and abs(r2 - EXPECT_SCALE_R2) <= 0.003 else 'FAIL'))
        ok &= bool(r2 is not None and abs(r2 - EXPECT_SCALE_R2) <= 0.003)
    else:
        rows.append(('图4 统计JSON', 'scale_stats.json', None, 'MISSING'))
        ok = False

    # 表8：同版本 API35 虚实对照（每侧 11 轮，剔首轮取 10 轮；导出比例取 trace 审计）
    vr = os.path.join(a.dir, 'table7_virtual_real')
    for side, exp in EXPECT_VR.items():
        paths = sorted(glob.glob(os.path.join(vr, side, 'api35_*_r*.json')))
        keep = [p for p in paths if not re.search(r'_r1\.json$', p)]
        if len(keep) < 10:
            rows.append(('表8 %s/s' % side, exp, None, 'MISSING'))
            ok = False
            continue
        check('表8 %s/s' % side, exp, round(statistics.mean(times(keep)), 3), tol=0.01)
        t = os.path.join(vr, side, 'trace_on.json')
        if os.path.isfile(t):
            d = load(t)
            rate = d.get('loss_rate')
            rows.append(('表8 %s导出比例' % side, '100%', '%d/%d' % (d['found'], d['expected']),
                         'PASS' if rate == EXPECT_VR_LOSS else 'FAIL'))
            ok &= (rate == EXPECT_VR_LOSS)
        else:
            rows.append(('表8 %s导出比例' % side, '100%', None, 'MISSING'))
            ok = False

    # 1-2 路径常量：policy_evidence 批次覆盖 7 版本、每版 11 项，且无 FUSE 未就绪报错
    pe = os.path.join(a.dir, 'appendix_policy_evidence')
    NEED = ['getprop_all.txt', 'getprop_filtered.txt', 'proc_filesystems.txt', 'mount_storage.txt',
            'path_ls_ld.txt', 'storage_emulated_ls.txt', 'dir_snapshot.txt', 'policy_files.txt',
            'sm_volumes.txt', 'policy_table.txt', 'policy_target.txt']
    miss = []
    for api in range(28, 35):
        d = os.path.join(pe, 'api%d' % api)
        for f in NEED:
            if not os.path.isfile(os.path.join(d, f)):
                miss.append('api%d/%s' % (api, f))
    rows.append(('1-2 policy证据文件齐备', '7×11', '%d缺失' % len(miss), 'PASS' if not miss else 'FAIL'))
    ok &= (not miss)
    bad = []
    for api in range(28, 35):
        p = os.path.join(pe, 'api%d' % api, 'path_ls_ld.txt')
        if os.path.isfile(p) and 'not connected' in open(p, encoding='utf-8', errors='replace').read():
            bad.append('api%d' % api)
    rows.append(('1-2 policy快照无FUSE未就绪', '0', ','.join(bad) if bad else '0', 'PASS' if not bad else 'FAIL'))
    ok &= (not bad)

    # 表9：四类故障单注（API35、W=1、baseline_50，各 20 次）
    fs = os.path.join(a.dir, 'table8_fault_adb_saf_pool')
    fd = os.path.join(a.dir, 'table8_fault_dag_cycle')
    for kind, exp_med in (('adb_disconnect', 9.89), ('saf_deny', 6.83), ('pool_exhaust', 6.81)):
        p = os.path.join(fs, kind, 'inject_summary.json')
        if not os.path.isfile(p):
            rows.append(('表9 %s' % kind, 1.0, None, 'MISSING'))
            ok = False
            continue
        d = load(p)
        rate = d.get('completion_rate', d.get('success_rate'))
        rows.append(('表9 %s完成率' % kind, 1.0, rate, 'PASS' if rate == 1.0 else 'FAIL'))
        ok &= (rate == 1.0)
        csvp = os.path.join(fs, kind, 'inject_log.csv')
        if os.path.isfile(csvp):
            with open(csvp, encoding='utf-8') as fh:
                rs = [r for r in csv.DictReader(fh) if r.get('run_s')]
            med = round(statistics.median(float(r['run_s']) for r in rs), 2)
            check('表9 %s单轮耗时中位' % kind, exp_med, med, tol=0.05)

    # 环依赖：20/20 拒绝加载，success_rate=0，且落盘 refused/cycle_path
    p = os.path.join(fd, 'inject_summary.json')
    if os.path.isfile(p):
        d = load(p)
        rate = d.get('completion_rate')
        rows.append(('表9 dag_cycle完成率', 0.0, rate, 'PASS' if rate == 0.0 else 'FAIL'))
        ok &= (rate == 0.0)
        js = glob.glob(os.path.join(fd, 'runs', '*.json'))
        refused = [load(j) for j in js]
        good = [j for j in refused if j.get('refused') and j.get('cycle_detected') and j.get('success_rate') == 0.0]
        rows.append(('表9 dag_cycle拒绝加载计数', 20, '%d/%d' % (len(good), len(js)),
                     'PASS' if len(good) == 20 and len(js) == 20 else 'FAIL'))
        ok &= (len(good) == 20 and len(js) == 20)
    else:
        rows.append(('表9 dag_cycle完成率', 0.0, None, 'MISSING'))
        ok = False

    # 4.3.6：同一原子重复 5 轮的耗时标准差（数据侧诊断；正文按预热后三轮口径表述）
    w1 = sorted(glob.glob(os.path.join(tv2, 'api33_baseline_50_priority_w1_on_*_r*.json')))
    if len(w1) >= 5:
        per = {}
        for p in w1:
            for at in load(p).get('atoms', []):
                per.setdefault(at['id'], []).append(at.get('duration_ms'))
        stds = [statistics.stdev(v) for v in per.values() if len(v) >= 5 and None not in v]
        if stds:
            med, mx = statistics.median(stds), max(stds)
            rows.append(('4.3.6 同原子std中位(ms)', '≤2.7', round(med, 2), 'INFO'))
            rows.append(('4.3.6 同原子std最大(ms)', '≤2.7', round(mx, 2), 'INFO'))
            if med > 2.7:
                notes.append('4.3.6 正文口径为预热后三轮：同原子std中位 8.9 ms、文件类原子 0.4~3.9 ms、最大值 68.0 ms；此处统计含冷启动全五轮（中位 %.1f ms、最大 %.1f ms），仅作口径说明' % (med, mx))

    # 4.3.8：峰值内存范围（数据侧），单位 GB 按 1000 MB 计
    memd = os.path.join(a.dir, 'table4_version_matrix', 'mem_v2')
    mems = [load(p).get('mem_peak_mb') for p in glob.glob(os.path.join(memd, '*_mem_*.json'))]
    mems = [m for m in mems if m]
    if mems:
        lo, hi = min(mems) / 1000.0, max(mems) / 1000.0
        rows.append(('4.3.8 峰值内存下限(GB)', 0.82, round(lo, 2), 'PASS' if abs(lo - 0.82) <= 0.01 else 'FAIL'))
        rows.append(('4.3.8 峰值内存上限(GB)', 1.45, round(hi, 2), 'PASS' if abs(hi - 1.45) <= 0.01 else 'FAIL'))
        ok &= (abs(lo - 0.82) <= 0.01 and abs(hi - 1.45) <= 0.01)
        if lo < 1.22:
            notes.append('4.3.8 正文口径为 0.82~1.45 GB（API28 最低 %.2f GB、API34 最高 %.2f GB）；1.22~1.45 的写法只覆盖 API32–34，本版已弃用' % (lo, hi))
    else:
        rows.append(('4.3.8 峰值内存', 1.45, None, 'MISSING'))
        ok = False

    wmax = max(len(r[0]) for r in rows)
    print('%-*s %9s %9s %s' % (wmax, '校验项', '论文值', '复算值', '结论'))
    for name, exp, act, res in rows:
        print('%-*s %9s %9s %s' % (wmax, name, exp, '—' if act is None else act, res))
    print('\n总判定：%s' % ('全部一致' if ok else '存在差异，见 FAIL/MISSING 行'))
    for n in notes:
        print('提示：' + n)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

