#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2/E3/E4 批量驱动器：按矩阵调用真并发执行器，剔除预热、断点续跑、写入索引。

用法：
  python experiments/paper/run_matrix.py --out output/paper/runs --repeats 5
  python experiments/paper/run_matrix.py --plan experiments/paper/matrix_plan.json

每个组合先跑 1 次预热（不进入统计），再跑 repeats 次。设备 API 与组合不符时直接中止，
避免把 AVD 张冠李戴。索引写入 index.csv，可随时中断续跑。
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RUNNER = os.path.join(HERE, "run_parallel.py")


def default_plan():
    """论文所需的最小矩阵。purpose 对应正文表格编号。"""
    plan = []
    versions = [28, 29, 30, 31, 32, 33, 34]
    for api in versions:
        plan.append(dict(api=api, scenario="baseline_50.yaml", scheduler="priority", w=1,
                         adapter="on", purpose="表4扩容/版本基线"))
    for sched in ("fifo", "priority"):
        for w in (1, 6):
            plan.append(dict(api=33, scenario="high_parallel_120.yaml", scheduler=sched, w=w,
                             adapter="on", purpose="表5并发/真并发对照"))
    for sc in ("privacy.yaml", "phishing.yaml", "ransomware.yaml"):
        for w in (1, 6):
            plan.append(dict(api=33, scenario=sc, scheduler="priority", w=w, adapter="on",
                             purpose="表6串并行对照/审1-15"))
    for w in (2, 4, 8, 12):
        plan.append(dict(api=33, scenario="baseline_50.yaml", scheduler="priority", w=w,
                         adapter="on", purpose="图3 W敏感性"))
    for api in versions:
        plan.append(dict(api=api, scenario="baseline_50.yaml", scheduler="priority", w=1,
                         adapter="off", purpose="版本适配消融/审2-8"))
    return plan


def device_api(serial=None):
    cmd = ["adb"] + (["-s", serial] if serial else []) + ["shell", "getprop", "ro.build.version.sdk"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8")
        return int((p.stdout or "").strip() or -1)
    except Exception:
        return -1


def run_once(combo, out_dir, repeat, tag, serial, timeout=900):
    cmd = [sys.executable, RUNNER, os.path.join(ROOT, "config", "scenarios", combo["scenario"]),
           "--api", str(combo["api"]), "--max-concurrency", str(combo["w"]),
           "--scheduler", combo["scheduler"], "--adapter", combo["adapter"],
           "--out", out_dir, "--tag", tag]
    if serial:
        cmd += ["--serial", serial]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace", cwd=ROOT)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "paper", "runs"))
    ap.add_argument("--plan", default=None, help="矩阵 JSON；缺省用内置最小矩阵")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--only-api", type=int, default=None, help="只跑某一版本，减少模拟器切换")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else default_plan()
    # 按版本聚拢：同一 AVD 开机期间把所有组合跑完，避免反复切换模拟器
    plan = sorted(plan, key=lambda c: (c["api"], c["scenario"], c["scheduler"], c["w"], c["adapter"]))
    if args.only_api is not None:
        plan = [c for c in plan if c["api"] == args.only_api]
    os.makedirs(args.out, exist_ok=True)
    index_path = os.path.join(args.out, "index.csv")
    header = ["time", "api", "scenario", "scheduler", "w", "adapter", "repeat",
              "status", "total_time", "peak_overlap", "success_rate", "purpose", "file"]

    if not os.path.exists(index_path):
        with open(index_path, "w", newline="", encoding="utf-8-sig") as fh:
            csv.writer(fh).writerow(header)

    total = len(plan) * (args.warmup + args.repeats)
    done = 0
    for combo in plan:
        cur_api = device_api(args.serial)
        if cur_api != combo["api"] and not args.dry_run:
            print("[SKIP] 需要 API %s，当前设备为 %s；请先切换模拟器" % (combo["api"], cur_api))
            continue
        for i in range(args.warmup + args.repeats):
            warm = i < args.warmup
            repeat = i if not warm else 0
            tag = "warmup" if warm else "r%d" % repeat
            fname = "api%d_%s_%s_w%d_%s_%s.json" % (
                combo["api"], os.path.splitext(combo["scenario"])[0],
                combo["scheduler"], combo["w"], combo["adapter"], tag)
            path = os.path.join(args.out, fname)
            done += 1
            if os.path.exists(path) and not warm:
                print("[%d/%d] 已存在，跳过 %s" % (done, total, fname))
                continue
            if args.dry_run:
                print("[dry] %s" % fname)
                continue
            t0 = time.time()
            rc, out, err = run_once(combo, args.out, repeat, tag, args.serial)
            status = "ok" if rc == 0 and os.path.exists(path) else "fail"
            total_time = peak = rate = ""
            if status == "ok":
                res = json.load(open(path, encoding="utf-8"))
                total_time, peak, rate = res["total_time"], res["peak_overlap"], res["success_rate"]
            with open(index_path, "a", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh).writerow([time.strftime("%Y-%m-%dT%H:%M:%S"), combo["api"],
                                         combo["scenario"], combo["scheduler"], combo["w"],
                                         combo["adapter"], tag, status, total_time, peak, rate,
                                         combo.get("purpose", ""), fname])
            print("[%d/%d] %s %s %.1fs %s" % (done, total, status, fname, time.time() - t0,
                                              ("(warmup)" if warm else "")))
            if status == "fail":
                print("  stdout:", out[-300:])
                print("  stderr:", err[-500:])


if __name__ == "__main__":
    main()
