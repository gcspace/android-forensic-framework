#!/usr/bin/env python3
"""
从实验日志中提取原子开始时间，与 logcat 比对计算时序偏差
用法: python3 calc_timing_v2.py <experiment.log> <logcat.log>
"""

import sys
import re
from datetime import datetime, timedelta
import numpy as np

def parse_time_from_log(line):
    # 匹配格式: 2026-08-06 10:51:05.308 - INFO - Executing: click_1
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) - INFO - Executing: (\S+)'
    m = re.search(pattern, line)
    if m:
        dt_str = m.group(1)
        node_id = m.group(2)
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')
        return int(dt.timestamp() * 1000), node_id
    return None, None

def parse_logcat_time(line):
    pattern = r'^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})'
    m = re.search(pattern, line)
    if not m:
        return None
    month, day, hour, minute, sec, msec = map(int, m.groups())
    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month, day, hour, minute, sec, msec * 1000)
        if dt > now + timedelta(days=1):
            dt = dt.replace(year=year-1)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)

def extract_atom_timestamps(log_path):
    atoms = []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts, node = parse_time_from_log(line)
            if ts is not None:
                atoms.append((node, ts))
    return atoms

def extract_logcat_timestamps(logcat_path):
    timestamps = []
    with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts = parse_logcat_time(line)
            if ts is not None:
                timestamps.append(ts)
    return timestamps

def compute_deviations(atoms, logcat_timestamps):
    deviations = []
    for node, start_abs in atoms:
        # 在 logcat 中寻找与 start_abs 最接近的时间戳（允许前后 100ms 窗口）
        best_dev = None
        for t in logcat_timestamps:
            diff = abs(t - start_abs)
            if diff < 100:  # 100ms 窗口
                if best_dev is None or diff < best_dev:
                    best_dev = diff
        if best_dev is not None:
            deviations.append(best_dev)
    return deviations

def main():
    if len(sys.argv) != 3:
        print("用法: python3 calc_timing_v2.py <experiment.log> <logcat.log>")
        sys.exit(1)
    
    log_path = sys.argv[1]
    logcat_path = sys.argv[2]
    
    atoms = extract_atom_timestamps(log_path)
    print(f"从实验日志提取 {len(atoms)} 个原子")
    
    logcat_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"从 logcat 提取 {len(logcat_timestamps)} 个时间戳")
    
    if not logcat_timestamps:
        print("❌ logcat 中无有效时间戳")
        sys.exit(1)
    
    deviations = compute_deviations(atoms, logcat_timestamps)
    if deviations:
        print(f"\n=== 时序偏差统计 ===")
        print(f"匹配原子数: {len(deviations)}")
        print(f"平均偏差: {np.mean(deviations):.2f} ms")
        print(f"标准差: {np.std(deviations):.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未匹配到任何原子与 logcat 时间")

if __name__ == "__main__":
    main()
