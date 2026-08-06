#!/usr/bin/env python3
"""
窗口匹配版：只在原子时间 ±50ms 内找日志，计算偏差
用法: python3 calc_timing_window.py <experiment_log> <logcat.log>
"""

import sys
import re
from datetime import datetime, timedelta
import numpy as np

WINDOW_MS = 50  # 时间窗口（毫秒）

def parse_experiment_log(log_path):
    atoms = []
    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO -   Executing: (\w+)'
    with open(log_path, 'r') as f:
        for line in f:
            match = re.search(pattern, line)
            if match:
                time_str = match.group(1)
                node_id = match.group(2)
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
                atoms.append((node_id, dt.timestamp() * 1000))
    return atoms

def parse_logcat_time(line):
    pattern = r'^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})'
    match = re.search(pattern, line)
    if not match:
        return None
    month, day, hour, minute, sec, msec = map(int, match.groups())
    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month, day, hour, minute, sec, msec * 1000)
        if dt > now + timedelta(days=1):
            dt = dt.replace(year=year-1)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)

def extract_logcat_timestamps(logcat_path):
    timestamps = []
    with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts = parse_logcat_time(line)
            if ts is not None:
                timestamps.append(ts)
    return timestamps

def main():
    if len(sys.argv) != 3:
        print("用法: python3 calc_timing_window.py <experiment_log> <logcat.log>")
        sys.exit(1)
    
    log_path = sys.argv[1]
    logcat_path = sys.argv[2]
    
    atoms = parse_experiment_log(log_path)
    print(f"找到 {len(atoms)} 个原子")
    if not atoms:
        sys.exit(1)
    
    log_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"找到 {len(log_timestamps)} 条日志时间戳")
    if not log_timestamps:
        sys.exit(1)
    
    deviations = []
    for node_id, atom_time in atoms:
        # 找时间窗口内的日志
        in_window = [t for t in log_timestamps if abs(t - atom_time) <= WINDOW_MS]
        if in_window:
            closest = min(in_window, key=lambda t: abs(t - atom_time))
            dev = abs(closest - atom_time)
            deviations.append(dev)
    
    if deviations:
        print(f"\n=== 窗口匹配时序偏差统计 ===")
        print(f"窗口大小: ±{WINDOW_MS} ms")
        print(f"匹配原子数: {len(deviations)} / {len(atoms)}")
        print(f"平均偏差: {np.mean(deviations):.2f} ms")
        print(f"标准差: {np.std(deviations):.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未匹配到任何原子")

if __name__ == "__main__":
    main()
