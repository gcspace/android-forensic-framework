#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E6 完整性闸门：分析前先确认数据齐、口径对，避免又出现"数字对不上"。

检查四件事：
  1) 矩阵是否跑满（每个组合 repeats 次，预热不计）；
  2) 每次运行的原子数是否等于 YAML 节点数（防止场景被改动后仍混用）；
  3) 原子成功率是否低于阈值（失败率高的运行不能进入耗时统计）；
  4) W>1 的运行是否真的出现重叠（峰值重叠数为 1 说明并发没有发生）。

用法：
  python experiments/paper/verify_matrix.py --dir output/paper/runs --repeats 5
退出码 1 表示存在必须补跑或必须解释的缺口。
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from experiments.paper.run_matrix import default_plan, ROOT  # noqa: E402


def yaml_nodes(scenario):
    path = os.path.join(ROOT, "config", "scenarios", scenario)
    try:
        import yaml
        y = yaml.safe_load(open(path, encoding="utf-8"))
        return len(y.get("nodes", []))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(ROOT, "output", "paper", "runs"))
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--min-success", type=float, default=0.95)
    ap.add_argument("--plan", default=None)
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else default_plan()
    files = [f for f in glob.glob(os.path.join(args.dir, "*.json")) if "warmup" not in os.path.basename(f)]
    runs = {}
    for f in files:
        j = json.load(open(f, encoding="utf-8"))
        key = (j.get("api"), j.get("scenario"), j.get("scheduler"), j.get("max_concurrency"), j.get("adapter"))
        runs.setdefault(key, []).append((f, j))

    errors, warnings = [], []
    for combo in plan:
        key = (combo["api"], combo["scenario"], combo["scheduler"], combo["w"], combo["adapter"])
        rs = runs.get(key, [])
        if len(rs) < args.repeats:
            errors.append("缺跑：%s 只有 %d/%d 次" % (str(key), len(rs), args.repeats))
            continue
        expect = yaml_nodes(combo["scenario"])
        for f, j in rs:
            if expect is not None and j.get("total_nodes") != expect:
                errors.append("原子数不符：%s 记录 %s，YAML 为 %s" % (os.path.basename(f), j.get("total_nodes"), expect))
            if (j.get("success_rate") or 0) < args.min_success:
                errors.append("成功率过低：%s 为 %.3f" % (os.path.basename(f), j.get("success_rate") or 0))
            if combo["w"] > 1 and (j.get("peak_overlap") or 0) <= 1:
                warnings.append("并发未发生：%s 峰值重叠=%s（W=%s）" % (
                    os.path.basename(f), j.get("peak_overlap"), combo["w"]))

    print("检查组合 %d 个，命中运行 %d 个" % (len(plan), sum(len(v) for v in runs.values())))
    for e in errors[:40]:
        print("  [缺] " + e)
    for w in sorted(set(warnings))[:10]:
        print("  [警] " + w)
    if errors:
        print("\n结论：数据不齐，先补跑再分析（%d 项）" % len(errors))
        sys.exit(1)
    print("\n结论：矩阵完整，可进入分析与填表")


if __name__ == "__main__":
    main()
