#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""痕迹可得性审计：按版本策略定位，统计“期望痕迹”里有几条真的能按该策略检索到。

两种用法（关键）：
1) 先以 --adapter on 跑场景，再 --adapter on 审计 → 期望=策略目录，验证适配后不漏检（应 0）。
2) 先以 --adapter off 跑场景（文件落在 /sdcard），再 --adapter on 审计
   → 期望=策略目录、而策略目录为空，loss_rate 即“未适配时按目标版本策略检索的漏检比例”。
场景内被 FILE_DELETE 抹掉的文件不计入期望集合。

用法：
  python experiments/paper/trace_audit.py config/scenarios/baseline_50.yaml \
      --api 33 --adapter on --out output/paper/trace_v2/api33_offrun_policysearch.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                or ".")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.scheduler.dag_builder import DAGBuilder            # noqa: E402
from core.executor import version_paths                     # noqa: E402


def adb(serial, cmd, timeout=20):
    argv = ["adb"] + (["-s", serial] if serial else []) + ["shell", cmd]
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml_path")
    ap.add_argument("--api", type=int, required=True)
    ap.add_argument("--adapter", choices=["on", "off"], default="on")
    ap.add_argument("--serial", default=None)
    ap.add_argument("--out", default="output/paper/trace")
    args = ap.parse_args()

    devices = [l.split()[0] for l in subprocess.run(["adb", "devices"], capture_output=True,
                                                    text=True).stdout.splitlines()[1:] if l.strip()]
    if args.serial is None:
        if len(devices) != 1:
            raise SystemExit("检测到 %d 台设备（%s），必须用 --serial 指定审计目标；"
                             "禁止按列表首台自动选择。" % (len(devices), ", ".join(devices)))
        args.serial = devices[0]
    elif args.serial not in devices:
        raise SystemExit("--serial %s 不在当前 adb devices 列表（%s）" % (args.serial, ", ".join(devices)))
    print("审计目标设备: %s" % args.serial)

    dag = DAGBuilder()
    dag.load_yaml(args.yaml_path)
    nodes = [dag.get_node(n) for n in dag.get_all_nodes()]
    exp = version_paths.expected_files(nodes, args.api, args.adapter)
    expected = exp["expected"]
    branch = version_paths.branch_for(args.api)
    target = version_paths.target_dir(args.api, args.adapter)

    listing = {}
    for path in expected:
        dirpath = path.rsplit("/", 1)[0] if "/" in path else "/sdcard"
        if dirpath not in listing:
            listing[dirpath] = adb(args.serial, "ls %s 2>/dev/null" % dirpath).split()

    found, missing = [], []
    for path in expected:
        base = path.rsplit("/", 1)[-1]
        dirpath = path.rsplit("/", 1)[0] if "/" in path else "/sdcard"
        (found if base in listing.get(dirpath, []) else missing).append(path)

    res = {
        "api": args.api,
        "branch": branch,
        "adapter": args.adapter,
        "policy_target": target,
        "expected": len(expected),
        "found": len(found),
        "missing": missing,
        "deleted_in_scenario": len(exp["deleted"]),
        "loss_rate": round(len(missing) / max(1, len(expected)), 3),
        "files_deleted_in_scenario": exp["deleted"],
        "timestamp": datetime.now().isoformat(),
    }
    os.makedirs(args.out, exist_ok=True)
    out = args.out
    if not out.endswith(".json"):
        out = os.path.join(out, "trace_api%d_%s.json" % (args.api, args.adapter))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print("trace_audit api=%d adapter=%s target=%s expected=%d found=%d loss=%.3f" % (
        args.api, args.adapter, target, res["expected"], res["found"], res["loss_rate"]))
    print("saved:", out)


if __name__ == "__main__":
    main()
