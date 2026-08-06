#!/usr/bin/env python3
"""
计算原子执行时间戳与logcat系统日志时间戳的平均偏差（时序标注精度）
用法: python3 scripts/calc_timing_accuracy.py <groundtruth_json_path> <logcat_log_path>
"""

import json
import sys
import re
import numpy as np

def extract_atom_timestamps(json_path):
    """从 groundtruth.json 中提取每个原子的开始时间戳（CLOCK_BOOTTIME）"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    atoms = {}
    for ev in data.get('evidence', []):
        node_id = ev.get('node_id')
        timestamp = ev.get('timestamp')
        duration_ms = ev.get('duration_ms', 0)
        if node_id and timestamp:
            atoms[node_id] = {
                'start': timestamp,
                'end': timestamp + duration_ms / 1000.0
            }
    return atoms

def extract_logcat_timestamps(logcat_path):
    """从 logcat 日志中提取每条日志的时间戳（CLOCK_BOOTTIME）"""
    timestamps = []
    # 匹配 [ 12345.678] 格式的 CLOCK_BOOTTIME
    pattern_boottime = r'\[\s*([0-9.]+)\s*\]'
    
    try:
        with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = re.search(pattern_boottime, line)
                if match:
                    timestamps.append(float(match.group(1)))
    except FileNotFoundError:
        print(f"❌ 找不到文件: {logcat_path}")
        return []
    
    return timestamps

def find_closest_log_time(atoms, log_timestamps):
    """对每个原子，找其时间窗口内最近的日志时间戳，计算偏差"""
    deviations = []
    for atom_id, times in atoms.items():
        start = times['start']
        end = times['end']
        
        # 找该原子执行区间内的所有日志时间戳
        in_window = [t for t in log_timestamps if start <= t <= end]
        if in_window:
            # 取最小的偏差（相对于原子开始时间）
            dev = min(abs(t - start) for t in in_window)
            deviations.append(dev * 1000)  # 转为毫秒
    
    return deviations

def main():
    if len(sys.argv) < 3:
        print("用法: python3 scripts/calc_timing_accuracy.py <groundtruth.json> <logcat.log>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    logcat_path = sys.argv[2]
    
    print(f"加载原子数据: {json_path}")
    atoms = extract_atom_timestamps(json_path)
    print(f"  找到 {len(atoms)} 个原子")
    
    print(f"加载logcat日志: {logcat_path}")
    log_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"  找到 {len(log_timestamps)} 条日志时间戳")
    
    if not log_timestamps:
        print("⚠️ 警告：未找到有效的logcat时间戳")
        print("请检查 logcat 文件中是否包含 [ 12345.678] 格式的时间戳")
        sys.exit(1)
    
    print("计算时序偏差...")
    deviations = find_closest_log_time(atoms, log_timestamps)
    
    if deviations:
        avg_dev = np.mean(deviations)
        std_dev = np.std(deviations)
        print(f"\n=== 时序标注精度统计 ===")
        print(f"有效比对原子数: {len(deviations)}")
        print(f"平均偏差: {avg_dev:.2f} ms")
        print(f"标准差: {std_dev:.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未找到任何时序匹配，请检查数据格式")

if __name__ == "__main__":
    main()
