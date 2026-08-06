#!/usr/bin/env python3
"""
计算时序偏差（简化版）
用法: python3 calc_timing.py <groundtruth.json> <logcat.log> <boot_abs_ms>
"""
import json
import sys
import re
from datetime import datetime, timedelta
import numpy as np

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

def extract_atoms(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    atoms = []
    for ev in data.get('evidence', []):
        ts = ev.get('timestamp')
        dur = ev.get('duration_ms', 0)
        if ts is not None:
            atoms.append((ts, dur))
    return atoms

def extract_logcat_timestamps(logcat_path):
    timestamps = []
    with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts = parse_logcat_time(line)
            if ts is not None:
                timestamps.append(ts)
    return timestamps

def compute_deviations(atoms, log_timestamps, boot_abs_ms):
    deviations = []
    for ts_boot, dur_ms in atoms:
        atom_start = boot_abs_ms + ts_boot * 1000
        atom_end = atom_start + dur_ms
        best_dev = None
        for t in log_timestamps:
            if atom_start <= t <= atom_end:
                dev = abs(t - atom_start)
                if best_dev is None or dev < best_dev:
                    best_dev = dev
        if best_dev is not None:
            deviations.append(best_dev)
    return deviations

def main():
    if len(sys.argv) != 4:
        print("用法: python3 calc_timing.py <groundtruth.json> <logcat.log> <boot_abs_ms>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    logcat_path = sys.argv[2]
    boot_abs_ms = float(sys.argv[3])
    
    atoms = extract_atoms(json_path)
    print(f"加载原子: {len(atoms)} 个")
    
    log_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"加载 logcat: {len(log_timestamps)} 条")
    
    if not log_timestamps:
        print("❌ 未找到日志时间戳")
        sys.exit(1)
    
    deviations = compute_deviations(atoms, log_timestamps, boot_abs_ms)
    
    if deviations:
        print(f"\n=== 时序偏差统计 ===")
        print(f"有效原子数: {len(deviations)}")
        print(f"平均偏差: {np.mean(deviations):.2f} ms")
        print(f"标准差: {np.std(deviations):.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未匹配到任何日志")

if __name__ == "__main__":
    main()
