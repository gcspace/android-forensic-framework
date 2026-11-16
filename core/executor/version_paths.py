#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本落盘路径策略（当前实现，替代 atomic_ops 里未被使用的三档分支）。

与 experiments/paper/version_policy.py 的分档保持一致，但这里只负责“文件落到哪”：
  api<=28  legacy_global   /sdcard
  29       legacy_optout   /sdcard/Download
  30-32    scoped_enforced /sdcard/Android/data
  33       granular_media  /sdcard/Pictures
  34-35    granular_photo  /sdcard/DCIM

adapter="off" 表示未启用版本适配：所有相对路径一律按旧全局路径 /sdcard 落盘，
用于量化“未适配时按新策略检索会漏掉多少痕迹”。
"""

BRANCH = {
    28: "legacy_global",
    29: "legacy_optout",
    30: "scoped_enforced",
    31: "scoped_enforced",
    32: "scoped_enforced",
    33: "granular_media",
    34: "granular_photo",
    35: "granular_photo",
}

TARGET = {
    28: "/sdcard",
    29: "/sdcard/Download",
    30: "/sdcard/Android/data",
    31: "/sdcard/Android/data",
    32: "/sdcard/Android/data",
    33: "/sdcard/Pictures",
    34: "/sdcard/DCIM",
    35: "/sdcard/DCIM",
}

LEGACY_TARGET = "/sdcard"


def branch_for(api_level):
    api = int(api_level)
    if api not in BRANCH:
        raise ValueError("未定义 API %d 的路径分支" % api)
    return BRANCH[api]


def target_dir(api_level, adapter="on"):
    api = int(api_level)
    if adapter != "on":
        return LEGACY_TARGET
    if api not in TARGET:
        raise ValueError("未定义 API %d 的落盘目录" % api)
    return TARGET[api]


def media_path(api_level, subpath, adapter="on"):
    """相对路径按版本策略落盘；绝对路径调用方自行绕过本函数。"""
    sub = str(subpath).lstrip("/")
    base = target_dir(api_level, adapter).rstrip("/")
    return base + "/" + sub if sub else base


def expected_files(nodes, api_level, adapter="on"):
    """从场景 YAML 的节点列表推期望文件集合，供 trace_audit 与正文口径共用。

    nodes: DAGBuilder 节点列表，或含 op_type/params 的字典列表。
    返回 {'expected': [...], 'deleted': [...]}，路径均为设备绝对路径。
    """
    created, deleted = set(), set()
    for n in nodes:
        op = getattr(n, "op_type", None) or (n.get("op_type") if isinstance(n, dict) else None) \
            or (n.get("type") if isinstance(n, dict) else None)
        params = getattr(n, "params", None) or (n.get("params") if isinstance(n, dict) else {}) or {}
        target = None
        if op == "FILE_CREATE":
            target = params.get("path")
        elif op == "FILE_COPY":
            target = params.get("dst")
        elif op == "FILE_DELETE":
            target = params.get("path")
        if not target:
            continue
        full = target if str(target).startswith("/") else media_path(api_level, target, adapter)
        if op == "FILE_DELETE":
            deleted.add(full)
        else:
            created.add(full)
    return {"expected": sorted(created - deleted), "deleted": sorted(deleted)}


if __name__ == "__main__":
    import sys
    api = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    for ad in ("on", "off"):
        print("api=%d adapter=%s branch=%s target=%s" % (api, ad, branch_for(api), target_dir(api, ad)))
