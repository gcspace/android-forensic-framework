#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E5 结果汇总：把跑数目录聚合成可直接填表的均值、标准差、加速比与重叠数。

用法：
  python experiments/paper/analyze_runs.py --dir output/paper/runs
  python experiments/paper/analyze_runs.py --dir output/groundtruth --allow-missing-api

输出：
  summary.csv            每个组合一行
  table5_like.csv        同场景 W=1 与 W=N 的对照（可直接对表5）
  adapter_ablation.csv   版本适配 on/off 的痕迹损失（对审2-8）
"""

import argparse
import csv
import glob
import json
import os
import statistics as st


def ci95(vals):
    if len(vals) < 2:
        return None
    sd = st.pstdev(vals)
    se = sd / (len(vals) ** 0.5)
    return round(1.96 * se, 3)


def load_runs(path):
    runs = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        atoms = j.get("atoms") or []
        rec = {
            "file": os.path.basename(f),
            "api": j.get("api", -1),
            "scenario": j.get("scenario") or "unknown",
            "scheduler": j.get("scheduler") or "unknown",
            "w": j.get("max_concurrency") or 1,
            "adapter": j.get("adapter", "on"),
            "nodes": j.get("total_nodes"),
            "time": j.get("total_time"),
            "peak": j.get("peak_overlap"),
            "ok": j.get("success_atoms"),
            "rate": j.get("success_rate"),
            "atom_sum": j.get("atom_time_sum"),
        }
        if rec["peak"] is None and atoms:
            events = [(a["timestamp_start"], 1) for a in atoms] + [(a["timestamp_end"], -1) for a in atoms]
            cur = peak = 0
            for _, d in sorted(events, key=lambda x: (x[0], -x[1])):
                cur += d
                peak = max(peak, cur)
            rec["peak"] = peak
        if rec["atom_sum"] is None and atoms:
            rec["atom_sum"] = round(sum(a["duration_ms"] for a in atoms) / 1000.0, 3)
        if rec["rate"] is None and atoms:
            rec["rate"] = round(sum(1 for a in atoms if a["success"]) / len(atoms), 3)
        if rec["time"]:
            runs.append(rec)
    return runs


def group(runs):
    groups = {}
    for r in runs:
        key = (r["api"], r["scenario"], r["scheduler"], r["w"], r["adapter"])
        groups.setdefault(key, []).append(r)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="output/paper/runs")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-missing-api", action="store_true")
    ap.add_argument("--min-n", type=int, default=3)
    args = ap.parse_args()

    runs = load_runs(args.dir)
    if not runs:
        print("目录内没有可用结果:", args.dir)
        return
    out = args.out or args.dir

    rows = []
    for key, rs in sorted(group(runs).items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2], kv[0][3])):
        times = [r["time"] for r in rs if r["time"]]
        rate = [r["rate"] for r in rs if r["rate"]]
        peak = [r["peak"] for r in rs if r["peak"]]
        rows.append({
            "api": key[0], "scenario": key[1], "scheduler": key[2], "w": key[3], "adapter": key[4],
            "n": len(times),
            "mean_s": round(st.mean(times), 2) if times else None,
            "sd_s": round(st.pstdev(times), 2) if len(times) > 1 else 0.0,
            "ci95": ci95(times),
            "peak_overlap_mean": round(st.mean(peak), 2) if peak else None,
            "success_rate": round(st.mean(rate), 3) if rate else None,
            "atom_time_sum": round(st.mean([r["atom_sum"] for r in rs if r["atom_sum"]]), 2),
            "files": ";".join(r["file"] for r in rs),
        })

    summary = os.path.join(out, "summary.csv")
    with open(summary, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("saved:", summary)

    # 表5形式：同 api/scenario/scheduler/adapter 下 W=1 与 W=N 对照
    t5 = []
    for r in rows:
        if r["w"] == 1:
            continue
        base = [b for b in rows if b["api"] == r["api"] and b["scenario"] == r["scenario"]
                and b["scheduler"] == r["scheduler"] and b["adapter"] == r["adapter"] and b["w"] == 1]
        if not base:
            continue
        b = base[0]
        t5.append({"api": r["api"], "scenario": r["scenario"], "scheduler": r["scheduler"],
                   "adapter": r["adapter"], "w1_mean": b["mean_s"], "wn_mean": r["mean_s"],
                   "w": r["w"], "speedup": round(b["mean_s"] / r["mean_s"], 2) if r["mean_s"] else None,
                   "peak_overlap": r["peak_overlap_mean"]})
    t5_path = os.path.join(out, "table5_like.csv")
    if t5:
        with open(t5_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(t5[0].keys()))
            w.writeheader()
            w.writerows(t5)
        print("saved:", t5_path)

    # 版本适配消融：同 api/scenario/scheduler/w 下 on 与 off 的原子成功数之比
    abl = []
    for (api, sc, sched, w, adapter), rs in group(runs).items():
        if adapter != "on":
            continue
        off = [r for r in runs if r["api"] == api and r["scenario"] == sc and r["scheduler"] == sched
               and r["w"] == w and r["adapter"] == "off"]
        if not off:
            continue
        on_rate = st.mean([r["rate"] for r in rs if r["rate"]])
        off_rate = st.mean([r["rate"] for r in off if r["rate"]])
        abl.append({"api": api, "scenario": sc, "scheduler": sched, "w": w,
                    "on_success": round(on_rate, 3), "off_success": round(off_rate, 3),
                    "trace_loss_pct": round((on_rate - off_rate) / on_rate * 100, 1) if on_rate else None})
    if abl:
        p = os.path.join(out, "adapter_ablation.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)
        print("saved:", p)

    print("\napi\tscenario\t\tsched\tW\tmean(s)\tsd\tpeak\tOK")
    for r in rows:
        if r["n"] < args.min_n and not args.allow_missing_api:
            continue
        print("%s\t%-18s\t%-8s\t%s\t%s\t%s\t%s\t%s" % (
            r["api"], r["scenario"], r["scheduler"], r["w"], r["mean_s"], r["sd_s"],
            r["peak_overlap_mean"], r["success_rate"]))


if __name__ == "__main__":
    main()
