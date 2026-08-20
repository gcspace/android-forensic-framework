#!/usr/bin/env python3
"""
分析勒索加密场景中各类型原子的耗时分布
对比模拟器 vs 真机
"""

import json
import numpy as np
import os

SIMULATOR_FILE = "output/groundtruth/real_execution_20260818_091837.json"  # 模拟器勒索加密
PHONE_FILE = "output/groundtruth/real_execution_20260806_105652.json"       # 真机勒索加密

def analyze_file(file_path, label):
    if not os.path.exists(file_path):
        print(f"⚠️ {label} 文件不存在: {file_path}")
        return {}
    with open(file_path, 'r') as f:
        data = json.load(f)
    results = {}
    for ev in data.get('evidence', []):
        op_type = ev.get('op_type', 'UNKNOWN')
        duration = ev.get('duration_ms', 0)
        if op_type not in results:
            results[op_type] = []
        results[op_type].append(duration)
    return results

def print_stats(results, label):
    print(f"\n{'='*50}")
    print(f"{label}")
    print(f"{'='*50}")
    total_ms = 0
    total_count = 0
    for op_type, durations in sorted(results.items(), key=lambda x: sum(x[1]), reverse=True):
        if durations:
            mean_dur = np.mean(durations)
            std_dur = np.std(durations)
            count = len(durations)
            total = sum(durations)
            total_ms += total
            total_count += count
            print(f"{op_type:20s}: n={count:3d}, 均值={mean_dur:6.2f}ms, 标准差={std_dur:6.2f}ms, 合计={total/1000:6.2f}s")
    print(f"{'-'*50}")
    print(f"总计: n={total_count:3d}, 总耗时={total_ms/1000:6.2f}s")
    return total_ms

print("="*60)
print("勒索加密场景：各原子类型耗时分析")
print("="*60)

sim_results = analyze_file(SIMULATOR_FILE, "模拟器 (API 33)")
phone_results = analyze_file(PHONE_FILE, "真机 (Pixel 7)")

if sim_results:
    sim_total = print_stats(sim_results, "模拟器 (API 33)")
if phone_results:
    phone_total = print_stats(phone_results, "真机 (Pixel 7)")

# 对比
if sim_results and phone_results:
    print(f"\n{'='*50}")
    print("对比分析")
    print(f"{'='*50}")
    print(f"模拟器总耗时: {sim_total/1000:.2f}s")
    print(f"真机总耗时:   {phone_total/1000:.2f}s")
    print(f"差异:         {((sim_total - phone_total)/phone_total*100):.1f}%")
