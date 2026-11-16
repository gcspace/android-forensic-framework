#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 版本证据探针：逐版本采集存储/权限/重定向的系统层事实。

用法：
  python experiments/paper/storage_probe.py --api 33 --serial emulator-5554 --out output/paper/probe

每次运行输出一个 JSON（probe_api{api}_r{n}.json）并向 probe_summary.csv 追加一行。
判据：同一 api 至少 3 次，三次结果一致才可作为正文证据；任一检查项失败需记录原始错误。
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from experiments.paper.version_policy import policy_for  # noqa: E402


def adb(serial, args, timeout=20):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout after %ss" % timeout


def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def check(serial, name, args, timeout=20, expect_rc=0):
    t0 = time.time()
    rc, out, err = adb(serial, args, timeout=timeout)
    ok = (rc == expect_rc) and (err == "" or rc == 0)
    return {
        "check": name,
        "cmd": " ".join(args),
        "rc": rc,
        "ok": bool(ok),
        "value": first_line(out),
        "lines": len(out.splitlines()) if out else 0,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "error": first_line(err),
    }


def run_probe(serial, api, repeat, out_dir):
    pol = policy_for(api)
    results = []

    results.append(check(serial, "sdk", ["shell", "getprop ro.build.version.sdk"]))
    results.append(check(serial, "release", ["shell", "getprop ro.build.version.release"]))
    results.append(check(serial, "sdcard_link", ["shell", "ls", "-ld", "/sdcard"]))
    # 全局路径可写性：分区存储前后最直接的差别之一
    results.append(check(serial, "legacy_write", ["shell",
                                                  "mkdir -p /sdcard/probe_rev && echo ok > /sdcard/probe_rev/t.txt && cat /sdcard/probe_rev/t.txt"]))
    # MediaStore 是否可查询、条目数是多少
    results.append(check(serial, "mediastore_query", ["shell",
                                                      "content query --uri content://media/external/images/media --projection _id"]))
    # SAF 入口是否存在
    results.append(check(serial, "documentsui", ["shell",
                                                 "pm list packages | grep -i documentsui"]))
    results.append(check(serial, "saf_intent", ["shell",
                                                "cmd package query-activities -a android.intent.action.OPEN_DOCUMENT_TREE"]))
    # 权限模型：细粒度媒体权限、部分照片访问是否在系统中定义
    results.append(check(serial, "read_media_perms", ["shell",
                                                      "pm list permissions -g | grep -E 'READ_MEDIA_IMAGES|READ_MEDIA_VIDEO'"]))
    results.append(check(serial, "visual_user_selected", ["shell",
                                                          "pm list permissions -g | grep READ_MEDIA_VISUAL_USER_SELECTED"]))
    # 重定向观测：写入后能否通过 MediaStore 看到该文件
    results.append(check(serial, "redirect_observe", ["shell",
                                                      "echo x > /sdcard/probe_rev/r.jpg; content query --uri content://media/external/images/media --projection _data | grep probe_rev"]))

    record = {
        "api": api,
        "repeat": repeat,
        "serial": serial,
        "policy": pol,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": results,
        "summary": {r["check"]: ("ok" if r["ok"] else "fail") for r in results},
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "probe_api%d_r%d.json" % (api, repeat))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)

    csv_path = os.path.join(out_dir, "probe_summary.csv")
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["api", "repeat", "branch", "check", "ok", "value", "elapsed_ms", "error"])
        for r in results:
            w.writerow([api, repeat, pol["branch"], r["check"], int(r["ok"]),
                        r["value"][:160], r["elapsed_ms"], r["error"][:160]])
    return path, record


def main():
    ap = argparse.ArgumentParser(description="按版本采集存储与权限证据")
    ap.add_argument("--api", type=int, required=True, help="API 级别，如 30")
    ap.add_argument("--serial", default=None, help="设备序列号，如 emulator-5554")
    ap.add_argument("--repeat", type=int, default=1, help="第几次重复，默认 1")
    ap.add_argument("--out", default="output/paper/probe", help="输出目录")
    args = ap.parse_args()

    path, rec = run_probe(args.serial, args.api, args.repeat, args.out)
    print("saved:", path)
    for r in rec["checks"]:
        print("%-22s %-4s %s" % (r["check"], "OK" if r["ok"] else "FAIL", r["value"][:70]))


if __name__ == "__main__":
    main()
