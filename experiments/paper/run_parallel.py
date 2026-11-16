#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E3 真并发执行器：按 DAG 就绪队列调度，用线程池并发下发 ADB 原子。

与 experiments/run_real_device.py 的区别：原入口逐层逐原子串行，W 只限制层大小，
因此"并发"从未发生。本脚本保持同一套 YAML、原子与 ADB 会话池，但让同一层的
多个原子真正同时在飞，用于重测表5、表6，并回答审2-11与审1-15的口径问题。

用法：
  python experiments/paper/run_parallel.py config/scenarios/baseline_50.yaml \
      --api 33 --max-concurrency 6 --scheduler priority --out output/paper/runs
"""

import argparse
import concurrent.futures as cf
import heapq
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.scheduler.dag_builder import DAGBuilder          # noqa: E402
from core.executor.atomic_ops import AtomicFactory          # noqa: E402
from core.executor.adb_manager import get_pool              # noqa: E402


def critical_remaining(dag):
    """每个节点到汇点的最长估计成本，作为优先级；越大越先做。"""
    memo = {}

    def cp(nid):
        if nid in memo:
            return memo[nid]
        node = dag.get_node(nid)
        cost = float(getattr(node, "estimated_cost", 1.0) or 1.0)
        succ = dag.get_successors(nid)
        memo[nid] = cost if not succ else cost + max(cp(s) for s in succ)
        return memo[nid]

    for nid in dag.get_all_nodes():
        cp(nid)
    return memo


def overlap_stats(atoms):
    """峰值重叠数与原子耗时之和，用于判断并发是否真的发生。"""
    if not atoms:
        return 0, 0.0
    events = []
    for a in atoms:
        events.append((a["timestamp_start"], 1))
        events.append((a["timestamp_end"], -1))
    events.sort(key=lambda x: (x[0], -x[1]))
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak, round(sum(a["duration_ms"] for a in atoms) / 1000.0, 3)


def run(yaml_path, api_level, scheduler, max_concurrency, serial=None, adapter="on",
        atomic_mode="dag", mem_sample=False):
    from core.executor.version_paths import branch_for, target_dir
    dag = DAGBuilder()
    dag.load_yaml(yaml_path)
    cyc, cyc_path = dag.detect_cycle()
    if cyc:
        print("检测到环形依赖，拒绝加载: %s" % " -> ".join(cyc_path))
        return {
            "api": api_level,
            "scenario": os.path.basename(yaml_path),
            "scheduler": scheduler,
            "max_concurrency": max_concurrency,
            "engine": "parallel-threads",
            "atomic_mode": "dag",
            "policy_branch": branch_for(api_level),
            "policy_target": target_dir(api_level, adapter),
            "adapter": adapter,
            "serial": serial,
            "total_nodes": len(dag.get_all_nodes()),
            "total_layers": None,
            "total_time": 0.0,
            "atom_time_sum": 0.0,
            "peak_overlap": 0,
            "success_atoms": 0,
            "success_rate": 0.0,
            "cycle_detected": True,
            "cycle_path": cyc_path,
            "refused": True,
            "mem_peak_mb": None,
            "timestamp": datetime.now().isoformat(),
            "atoms": [],
        }
    nodes = dag.get_all_nodes()
    priorities = critical_remaining(dag)

    pool = get_pool(max_sessions=max(8, max_concurrency))
    if serial is None:
        devices = pool.get_device_list()
        if not devices:
            raise RuntimeError("未检测到设备，请先启动对应 API 的模拟器")
        if len(devices) > 1:
            raise RuntimeError(
                "检测到 %d 台设备（%s），必须用 --serial 显式指定目标设备；"
                "禁止按列表首台自动选择，否则模拟器批次可能落到真机。" % (len(devices), ", ".join(devices)))
        serial = devices[0]
    print("实测目标设备: %s" % serial)

    mem_stop = threading.Event()
    mem_peak = {"used_mb": None}

    def mem_loop():
        total = None
        while not mem_stop.is_set():
            try:
                out = subprocess.run(["adb", "-s", serial, "shell", "cat", "/proc/meminfo"],
                                     capture_output=True, text=True, timeout=10).stdout
                vals = {}
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) == 2:
                        vals[parts[0].strip()] = int(parts[1].strip().split()[0])
                if "MemTotal" in vals:
                    total = vals["MemTotal"]
                if total and "MemAvailable" in vals:
                    used = round((total - vals["MemAvailable"]) / 1024.0, 1)
                    if mem_peak["used_mb"] is None or used > mem_peak["used_mb"]:
                        mem_peak["used_mb"] = used
            except Exception:
                pass
            mem_stop.wait(0.5)

    mem_thread = threading.Thread(target=mem_loop, daemon=True) if mem_sample else None
    if mem_thread:
        mem_thread.start()

    if atomic_mode == "single":
        # 贡献1消融：整个场景作为 1 个原子，内部顺序执行，不拆分、不打原子级时间戳
        indeg = {n: dag.get_in_degree(n) for n in nodes}
        order, ready0 = [], [n for n in nodes if indeg[n] == 0]
        succ_map = {n: dag.get_successors(n) for n in nodes}
        while ready0:
            nid = ready0.pop(0)
            order.append(nid)
            for s in succ_map[nid]:
                indeg[s] -= 1
                if indeg[s] == 0:
                    ready0.append(s)
        t0 = time.time()
        inner, ok = [], 0
        for nid in order:
            node = dag.get_node(nid)
            try:
                op = AtomicFactory.create(node.op_type, api_level=api_level, serial=serial,
                                          params=getattr(node, "params", {}) or {}, adapter=adapter)
                r = op.execute()
                ok += 1 if r.success else 0
                inner.append({"id": nid, "op_type": node.op_type, "success": bool(r.success),
                              "duration_ms": float(r.duration_ms)})
            except Exception as exc:
                inner.append({"id": nid, "op_type": node.op_type, "success": False,
                              "duration_ms": 0.0, "error": str(exc)})
        wall = time.time() - t0
        if mem_thread:
            mem_stop.set(); mem_thread.join(timeout=2)
        return {
            "api": api_level,
            "scenario": os.path.basename(yaml_path),
            "scheduler": scheduler,
            "max_concurrency": max_concurrency,
            "engine": "parallel-threads",
            "atomic_mode": "single",
            "policy_branch": branch_for(api_level),
            "policy_target": target_dir(api_level, adapter),
            "adapter": adapter,
            "serial": serial,
            "total_nodes": len(nodes),
            "total_layers": None,
            "total_time": round(wall, 3),
            "atom_time_sum": round(wall, 3),
            "peak_overlap": 1,
            "success_atoms": ok,
            "success_rate": round(ok / max(1, len(nodes)), 3),
            "mem_peak_mb": mem_peak["used_mb"],
            "timestamp": datetime.now().isoformat(),
            "atoms": [{"id": "scenario_blob", "op_type": "SCENARIO_BLOB",
                       "success": ok == len(nodes), "duration_ms": round(wall * 1000, 1),
                       "timestamp_start": 0.0, "timestamp_end": round(wall * 1000, 1),
                       "error": None}],
            "inner": inner,
        }

    in_deg = {n: dag.get_in_degree(n) for n in nodes}
    succ = {n: dag.get_successors(n) for n in nodes}
    ready = [(-priorities[n], n) for n in nodes if in_deg[n] == 0]
    heapq.heapify(ready)
    if scheduler == "fifo":
        ready = [(0.0, n) for n in nodes if in_deg[n] == 0]
        ready.sort(key=lambda x: x[1])

    records = []
    lock = threading.Lock()
    started = time.time()

    def work(nid):
        node = dag.get_node(nid)
        params = getattr(node, "params", {}) or {}
        t_factory = time.time()
        try:
            op = AtomicFactory.create(node.op_type, api_level=api_level, serial=serial,
                                      params=params, adapter=adapter)
            result = op.execute()
            rec = {
                "id": nid,
                "op_type": node.op_type,
                "success": bool(result.success),
                "duration_ms": float(result.duration_ms),
                "timestamp_start": float(result.timestamp_start),
                "timestamp_end": float(result.timestamp_end),
                "error": result.error,
            }
        except Exception as exc:  # 单原子异常不应中断整个场景
            rec = {"id": nid, "op_type": node.op_type, "success": False,
                   "duration_ms": 0.0, "timestamp_start": 0.0, "timestamp_end": 0.0,
                   "error": "%s: %s" % (type(exc).__name__, exc),
                   "factory_latency_ms": round((time.time() - t_factory) * 1000, 1)}
        with lock:
            records.append(rec)
        return rec

    running = {}
    with cf.ThreadPoolExecutor(max_workers=max_concurrency) as ex:
        while ready or running:
            while ready and len(running) < max_concurrency:
                _, nid = heapq.heappop(ready)
                running[ex.submit(work, nid)] = nid
            if not running:
                break
            done, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                nid = running.pop(fut)
                try:
                    fut.result()
                except Exception as exc:
                    with lock:
                        records.append({"id": nid, "op_type": "?", "success": False,
                                        "duration_ms": 0.0, "timestamp_start": 0.0,
                                        "timestamp_end": 0.0, "error": str(exc)})
                for s in succ[nid]:
                    in_deg[s] -= 1
                    if in_deg[s] == 0:
                        heapq.heappush(ready, (-priorities.get(s, 0.0), s))

    wall = time.time() - started
    if mem_thread:
        mem_stop.set()
        mem_thread.join(timeout=2)
    peak, atom_sum = overlap_stats(records)
    ok = sum(1 for r in records if r["success"])
    return {
        "api": api_level,
        "scenario": os.path.basename(yaml_path),
        "scheduler": scheduler,
        "max_concurrency": max_concurrency,
        "engine": "parallel-threads",
        "atomic_mode": "dag",
        "policy_branch": branch_for(api_level),
        "policy_target": target_dir(api_level, adapter),
        "adapter": adapter,
        "serial": serial,
        "total_nodes": len(nodes),
        "total_layers": None,
        "total_time": round(wall, 3),
        "atom_time_sum": atom_sum,
        "peak_overlap": peak,
        "success_atoms": ok,
        "success_rate": round(ok / max(1, len(records)), 3),
        "mem_peak_mb": mem_peak["used_mb"],
        "timestamp": datetime.now().isoformat(),
        "atoms": records,
    }


def main():
    ap = argparse.ArgumentParser(description="DAG 真并发执行器")
    ap.add_argument("yaml_path")
    ap.add_argument("--api", type=int, required=True)
    ap.add_argument("--max-concurrency", type=int, default=6)
    ap.add_argument("--scheduler", choices=["priority", "fifo", "basic"], default="priority",
                    help="priority=关键路径优先；fifo/basic=就绪即跑（basic 为兼容别名，落盘统一记为 fifo）")
    ap.add_argument("--serial", default=None)
    ap.add_argument("--adapter", choices=["on", "off"], default="on",
                    help="版本适配开关，写入结果供分析区分")
    ap.add_argument("--out", default="output/paper/runs")
    ap.add_argument("--atomic-mode", choices=["dag", "single"], default="dag",
                    help="dag=按原子拆分执行；single=整场景单原子（贡献1消融用）")
    ap.add_argument("--mem-sample", action="store_true", help="运行期采样 /proc/meminfo，记录峰值内存")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    scheduler = "fifo" if args.scheduler == "basic" else args.scheduler

    res = run(args.yaml_path, args.api, scheduler, args.max_concurrency,
              serial=args.serial, adapter=args.adapter,
              atomic_mode=args.atomic_mode, mem_sample=args.mem_sample)
    os.makedirs(args.out, exist_ok=True)
    name = "api%d_%s_%s_w%d_%s%s%s.json" % (
        args.api, os.path.splitext(os.path.basename(args.yaml_path))[0],
        scheduler, args.max_concurrency, args.adapter,
        "_single" if args.atomic_mode == "single" else "",
        ("_" + args.tag) if args.tag else "")
    path = os.path.join(args.out, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print("saved:", path)
    print("nodes=%d time=%.2fs peak_overlap=%d success_rate=%.3f" % (
        res["total_nodes"], res["total_time"], res["peak_overlap"], res["success_rate"]))


if __name__ == "__main__":
    main()
