#!/usr/bin/env python3
"""
直接从实验日志和 logcat 计算时序偏差
用法: python3 calc_from_log.py <experiment_log> <logcat.log>
"""

import sys
import re
from datetime import datetime, timedelta
import numpy as np

def parse_experiment_log(log_path):
    """提取每个原子的开始时间（宿主机绝对时间）"""
    atoms = []
    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO -   Executing: (\w+)'
    with open(log_path, 'r') as f:
        for line in f:
            match = re.search(pattern, line)
            if match:
                time_str = match.group(1)
                node_id = match.group(2)
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
                atoms.append((node_id, dt.timestamp() * 1000))  # 转为毫秒
    return atoms

def parse_logcat_time(line):
    """从 logcat 行首提取时间（MM-DD HH:MM:SS.mmm）并转为毫秒时间戳"""
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

def find_closest_log(atoms, log_timestamps):
    """对每个原子，找 logcat 中最接近其开始时间的日志，计算偏差"""
    deviations = []
    for node_id, atom_time in atoms:
        # 在 logcat 时间戳中找与 atom_time 最接近的一个
        closest = min(log_timestamps, key=lambda t: abs(t - atom_time))
        dev = abs(closest - atom_time)
        deviations.append(dev)
    return deviations

def main():
    if len(sys.argv) != 3:
        print("用法: python3 calc_from_log.py <experiment_log> <logcat.log>")
        sys.exit(1)
    
    log_path = sys.argv[1]
    logcat_path = sys.argv[2]
    
    print("正在提取原子执行时间...")
    atoms = parse_experiment_log(log_path)
    print(f"  找到 {len(atoms)} 个原子")
    if not atoms:
        print("❌ 未找到任何 'Executing:' 行，请检查日志格式")
        sys.exit(1)
    
    print("正在提取 logcat 时间戳...")
    log_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"  找到 {len(log_timestamps)} 条日志时间戳")
    if not log_timestamps:
        print("❌ 未找到任何时间戳")
        sys.exit(1)
    
    print("计算偏差...")
    deviations = find_closest_log(atoms, log_timestamps)
    
    if deviations:
        print(f"\n=== 时序偏差统计 ===")
        print(f"有效原子数: {len(deviations)}")
        print(f"平均偏差: {np.mean(deviations):.2f} ms")
        print(f"标准差: {np.std(deviations):.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未计算出偏差")

if __name__ == "__main__":
    main()
