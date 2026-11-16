#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E4 抖动重测：按版本采集表3的四类分量，替代仓库中为空或手填的日志。

分量口径：
  1) adb_roundtrip   空 shell 命令端到端往返（1000 次）
  2) host_overhead   主机侧进程创建开销（200 次），用于从往返中扣减
  3) service_resp    系统服务查询往返（100 次）
  4) clock_window    一次 CLOCK_BOOTTIME 读取封装窗口（100 次）
  5) kernel_jitter   相邻两次空命令往返差值的标准差

用法：
  python experiments/paper/measure_jitter.py --api 33 --serial emulator-5554 --out output/paper/jitter
"""

import argparse
import csv
import json
import os
import statistics as st
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from experiments.paper.version_policy import branch_for  # noqa: E402


def timed(cmd, timeout=20):
    t0 = time.perf_counter()
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
        return (time.perf_counter() - t0) * 1000
    except subprocess.TimeoutExpired:
        return None


def summarize(values, drop=0):
    vals = sorted(v for v in values if v is not None)
    if drop and len(vals) > drop:
        vals = vals[:-drop]
    if not vals:
        return dict(n=0, mean=None, sd=None, p50=None, p95=None)
    return dict(n=len(vals), mean=round(st.mean(vals), 3),
                sd=round(st.pstdev(vals), 3) if len(vals) > 1 else 0.0,
                p50=round(st.median(vals), 3),
                p95=round(vals[int(len(vals) * 0.95) - 1], 3))


def measure(serial, api, n_adb=1000, n_svc=100, n_clock=100, n_host=200):
    base = ["adb"] + (["-s", serial] if serial else [])
    host_cmd = [sys.executable, "-c", "pass"]

    host = [timed(host_cmd) for _ in range(n_host)]

    adb_rt = [timed(base + ["shell", "echo", "x"]) for _ in range(n_adb)]
    raw = summarize(adb_rt, drop=int(len(adb_rt) * 0.01))  # 去掉最慢 1% 的抖动尾部
    host_s = summarize(host)
    net = None
    if raw["mean"] is not None and host_s["mean"] is not None:
        net = round(raw["mean"] - host_s["mean"], 3)

    svc = [timed(base + ["shell", "settings", "get", "global", "device_name"]) for _ in range(n_svc)]

    # 读取封装窗口：两次 uptime 读取之间夹一次空操作
    clock = []
    for _ in range(n_clock):
        t0 = time.perf_counter()
        subprocess.run(base + ["shell", "cat", "/proc/uptime"], capture_output=True,
                       text=True, timeout=15, encoding="utf-8", errors="replace")
        subprocess.run(base + ["shell", "echo", "x"], capture_output=True,
                       text=True, timeout=15, encoding="utf-8", errors="replace")
        subprocess.run(base + ["shell", "cat", "/proc/uptime"], capture_output=True,
                       text=True, timeout=15, encoding="utf-8", errors="replace")
        clock.append((time.perf_counter() - t0) * 1000)

    diffs = []
    vals = [v for v in adb_rt if v is not None]
    for a, b in zip(vals, vals[1:]):
        diffs.append(abs(b - a))

    return {
        "api": api,
        "branch": branch_for(api),
        "serial": serial,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "adb_roundtrip": raw,
        "host_overhead": host_s,
        "adb_transfer_net": net,
        "service_resp": summarize(svc),
        "clock_window": summarize(clock, drop=int(len(clock) * 0.01)),
        "kernel_jitter": summarize(diffs),
        "raw": {"adb_roundtrip_ms": [round(v, 3) for v in adb_rt if v is not None],
                "clock_window_ms": [round(v, 3) for v in clock]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", type=int, required=True)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--out", default="output/paper/jitter")
    ap.add_argument("--n-adb", type=int, default=1000)
    args = ap.parse_args()

    res = measure(args.serial, args.api, n_adb=args.n_adb)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "jitter_api%d.json" % args.api)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)

    rows = [
        ["adb_roundtrip", res["adb_roundtrip"]],
        ["host_overhead", res["host_overhead"]],
        ["adb_transfer_net", dict(n=res["adb_roundtrip"]["n"], mean=res["adb_transfer_net"])],
        ["service_resp", res["service_resp"]],
        ["clock_window", res["clock_window"]],
        ["kernel_jitter", res["kernel_jitter"]],
    ]
    csv_path = os.path.join(args.out, "jitter_summary.csv")
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["api", "branch", "component", "n", "mean_ms", "sd_ms", "p50_ms", "p95_ms"])
        for name, s in rows:
            w.writerow([args.api, res["branch"], name, s.get("n"), s.get("mean"),
                        s.get("sd"), s.get("p50"), s.get("p95")])
    print("saved:", path)
    for name, s in rows:
        print("%-18s n=%-5s mean=%-8s sd=%s" % (name, s.get("n"), s.get("mean"), s.get("sd")))


if __name__ == "__main__":
    main()
