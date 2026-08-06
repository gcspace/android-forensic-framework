#!/usr/bin/env python3
"""
计算时序标注精度（原子时间戳 vs logcat 日志时间戳）
用法: python3 scripts/calc_timing_accuracy_final.py <groundtruth.json> <logcat.log> <uptime_sec> <date_ms>
示例: python3 scripts/calc_timing_accuracy_final.py output/groundtruth/real_execution_XXX.json output/.../logcat_privacy_clean_XXX.log 133.63 1785984702516
"""

import json
import sys
import re
from datetime import datetime, timedelta
import numpy as np

def parse_logcat_time(line):
    """
    从 logcat 行首提取时间戳（格式：MM-DD HH:MM:SS.mmm）
    返回对应的 Unix 毫秒时间戳（基于当前年份）
    """
    # 匹配格式 "08-06 10:51:05.308"
    pattern = r'^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})'
    match = re.search(pattern, line)
    if not match:
        return None
    month, day, hour, minute, sec, msec = map(int, match.groups())
    # 构建 datetime（假设年份为当前年份）
    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month, day, hour, minute, sec, msec * 1000)
        # 如果解析出的时间比当前时间晚太多，可能是去年的数据
        if dt > now + timedelta(days=1):
            dt = dt.replace(year=year-1)
    except ValueError:
        return None
    # 转为 Unix 毫秒时间戳
    return int(dt.timestamp() * 1000)

def extract_atoms(json_path):
    """从 groundtruth.json 提取原子开始时间（CLOCK_BOOTTIME，秒）和 duration（毫秒）"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    atoms = []
    for ev in data.get('evidence', []):
        node_id = ev.get('node_id')
        ts = ev.get('timestamp')  # CLOCK_BOOTTIME 秒
        dur = ev.get('duration_ms', 0)
        if ts is not None:
            atoms.append((node_id, ts, dur))
    return atoms

def extract_logcat_timestamps(logcat_path):
    """从 logcat 文件中提取所有日志的 Unix 毫秒时间戳"""
    timestamps = []
    with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts = parse_logcat_time(line)
            if ts is not None:
                timestamps.append(ts)
    return timestamps

def compute_deviations(atoms, log_timestamps, uptime_sec, date_ms):
    """
    计算每个原子的时序偏差（毫秒）
    atoms: list of (node_id, boottime_sec, duration_ms)
    log_timestamps: list of Unix ms timestamps from logcat
    """
    # 将 boottime 转为绝对时间（Unix 毫秒）
    # 换算公式：绝对时间 = date_ms - uptime_sec*1000 + boottime_sec*1000
    shift = date_ms - uptime_sec * 1000.0
    deviations = []
    for node_id, boottime_sec, duration_ms in atoms:
        atom_abs_start = shift + boottime_sec * 1000.0
        atom_abs_end = atom_abs_start + duration_ms
        
        # 在该原子窗口内寻找最接近开始时间的 log 时间戳
        best_dev = None
        for t in log_timestamps:
            if atom_abs_start <= t <= atom_abs_end:
                dev = abs(t - atom_abs_start)  # 偏差（毫秒）
                if best_dev is None or dev < best_dev:
                    best_dev = dev
        if best_dev is not None:
            deviations.append(best_dev)
    return deviations

def main():
    if len(sys.argv) != 5:
        print("用法: python3 scripts/calc_timing_accuracy_final.py <groundtruth.json> <logcat.log> <uptime_sec> <date_ms>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    logcat_path = sys.argv[2]
    uptime_sec = float(sys.argv[3])
    date_ms = float(sys.argv[4])
    
    print(f"加载原子数据: {json_path}")
    atoms = extract_atoms(json_path)
    print(f"  找到 {len(atoms)} 个原子")
    
    print(f"加载 logcat 时间戳: {logcat_path}")
    log_timestamps = extract_logcat_timestamps(logcat_path)
    print(f"  找到 {len(log_timestamps)} 条日志时间戳")
    if not log_timestamps:
        print("❌ 未找到任何有效时间戳，请检查 logcat 格式")
        sys.exit(1)
    
    print(f"基准: uptime={uptime_sec}s, date={date_ms}ms")
    print("计算时序偏差...")
    deviations = compute_deviations(atoms, log_timestamps, uptime_sec, date_ms)
    
    if deviations:
        avg = np.mean(deviations)
        std = np.std(deviations)
        print(f"\n=== 时序标注精度统计 ===")
        print(f"有效比对原子数: {len(deviations)}")
        print(f"平均偏差: {avg:.2f} ms")
        print(f"标准差: {std:.2f} ms")
        print(f"最小值: {min(deviations):.2f} ms")
        print(f"最大值: {max(deviations):.2f} ms")
    else:
        print("❌ 未找到任何匹配的日志，请检查时间窗口或 logcat 覆盖范围")

if __name__ == "__main__":
    main()
