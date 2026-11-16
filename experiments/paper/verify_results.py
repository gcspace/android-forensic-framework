#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 侧接收校验：确认 Linux 传回的包没损坏、跑数是否齐。

用法（Windows）：
  python experiments\\paper\\verify_results.py --dir output/paper/table4_version_matrix --sums-only

做三件事：
  1) 按 SHA256SUMS 校验 results.tar.gz 与 manifest.json；
  2) 读压缩包内的运行文件，按 API 与场景统计次数；
  3) 对照最小矩阵（28 组合 × 5 次）列出缺跑的格子。
"""

import argparse
import collections
import hashlib
import json
import os
import sys
import tarfile

EXPECT = [
    # (api, scenario, scheduler, w, adapter, times)
    *[(api, "baseline_50", "priority", 1, "on", 5) for api in (28, 29, 30, 31, 32, 33, 34)],
    (33, "high_parallel_120", "fifo", 1, "on", 5),
    (33, "high_parallel_120", "fifo", 6, "on", 5),
    (33, "high_parallel_120", "priority", 1, "on", 5),
    (33, "high_parallel_120", "priority", 6, "on", 5),
    *[(33, sc, "priority", w, "on", 5) for sc in ("privacy", "phishing", "ransomware") for w in (1, 6)],
    *[(33, "baseline_50", "priority", w, "on", 5) for w in (2, 4, 8, 12)],
    *[(api, "baseline_50", "priority", 1, "off", 5) for api in (28, 29, 30, 31, 32, 33, 34)],
]


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def verify_sums(session_dir):
    sums = os.path.join(session_dir, "SHA256SUMS")
    if not os.path.exists(sums):
        return [("缺少 SHA256SUMS", False)]
    results = []
    for line in open(sums, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        expect, name = line.split(None, 1)
        name = name.lstrip("*")
        path = os.path.join(session_dir, name)
        ok = os.path.exists(path) and sha256(path) == expect
        results.append((name, ok))
    return results


def stat_archive(tar_path):
    counts = collections.Counter()
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or not m.name.endswith(".json"):
                continue
            if "/runs/" not in m.name or "warmup" in m.name:
                continue
            try:
                j = json.load(tf.extractfile(m))
            except Exception:
                continue
            key = (j.get("api"), os.path.splitext(j.get("scenario") or "")[0],
                   j.get("scheduler"), j.get("max_concurrency"), j.get("adapter"))
            counts[key] += 1
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="批次目录（含 files.txt 与 SHA256SUMS）")
    ap.add_argument("--sums-only", action="store_true", help="只做按清单的逐文件哈希校验")
    args = ap.parse_args()

    print("== 1. 完整性校验（按 files.txt + SHA256SUMS 逐文件）")
    bad = 0
    for name, ok in verify_sums(args.dir):
        print("  %-18s %s" % (name, "OK" if ok else "损坏"))
        bad += 0 if ok else 1

    if args.sums_only:
        sys.exit(1 if bad else 0)

    tar_path = os.path.join(args.dir, "results.tar.gz")
    if not os.path.exists(tar_path):
        print("本批次未附 results.tar.gz，仅完成清单校验")
        sys.exit(1 if bad else 0)

    print("== 2. 运行计数")
    counts = stat_archive(tar_path)
    by_api = collections.Counter()
    for (api, sc, sched, w, ad), n in counts.items():
        by_api[api] += n
    print("  按 API：" + "  ".join("api%s=%d" % (k, v) for k, v in sorted(by_api.items(), key=lambda x: str(x[0]))))

    print("== 3. 对照最小矩阵")
    missing = []
    for api, sc, sched, w, ad, times in EXPECT:
        got = counts.get((api, sc, sched, w, ad), 0)
        if got < times:
            missing.append((api, sc, sched, w, ad, got, times))
    if missing:
        for m in missing:
            print("  缺跑 api%s/%s/%s/W%s/%s：%d/%d" % m)
    else:
        print("  28 个组合均满 5 次")

    man = os.path.join(args.dir, "manifest.json")
    if os.path.exists(man):
        j = json.load(open(man, encoding="utf-8"))
        print("== 4. 清单")
        print("  打包时间：%s   主机：%s   内核：%s" % (j.get("created"), j.get("host"), j.get("kernel")))
        print("  代码指纹：%s" % (j.get("code_sha256") or "")[:16])
        print("  AVD：%s" % j.get("avds"))

    sys.exit(1 if (bad or missing) else 0)


if __name__ == "__main__":
    main()
