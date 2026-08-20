#!/usr/bin/env python3
"""
时序抖动四分量测量（API 33 模拟器）
与论文原有总抖动 49.18ms 对标
"""

import subprocess
import time
import numpy as np
import json
import os

DEVICE = "emulator-5554"
N_SAMPLES = 1000
OUTPUT_DIR = "experiments/supplement"

def adb_shell(cmd):
    result = subprocess.run(f"adb -s {DEVICE} shell {cmd}", shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def measure_clock_precision():
    """分量4：CLOCK_BOOTTIME 读取精度"""
    print("  [分量4] CLOCK_BOOTTIME 读精度...")
    readings = []
    for _ in range(N_SAMPLES):
        out = adb_shell("cat /proc/uptime")
        try:
            readings.append(float(out.split()[0]))
        except:
            pass
    if len(readings) < 2:
        return 0, 0
    intervals = [(readings[i+1] - readings[i]) * 1000 for i in range(len(readings)-1)]
    return np.mean(intervals), np.std(intervals)

def measure_adb_roundtrip():
    """分量1：ADB 传输开销（含 shell 启动）"""
    print("  [分量1] ADB 传输开销...")
    delays = []
    for _ in range(N_SAMPLES):
        start = time.perf_counter()
        subprocess.run(f"adb -s {DEVICE} shell true", shell=True, capture_output=True)
        end = time.perf_counter()
        delays.append((end - start) * 1000)
    return np.mean(delays), np.std(delays)

def measure_kernel_noise():
    """分量3：内核调度噪声（用空操作的波动表征）"""
    print("  [分量3] 内核调度噪声...")
    delays = []
    for _ in range(N_SAMPLES):
        start = time.perf_counter()
        subprocess.run(f"adb -s {DEVICE} shell true", shell=True, capture_output=True)
        end = time.perf_counter()
        delays.append((end - start) * 1000)
    # 标准差反映调度噪声
    return np.std(delays)

def measure_system_service():
    """分量2：系统服务响应（用 input 命令延迟减去 ADB 传输）"""
    print("  [分量2] 系统服务响应...")
    # 先测 ADB 纯传输
    adb_delays = []
    for _ in range(200):
        start = time.perf_counter()
        subprocess.run(f"adb -s {DEVICE} shell true", shell=True, capture_output=True)
        end = time.perf_counter()
        adb_delays.append((end - start) * 1000)
    adb_avg = np.mean(adb_delays)
    
    # 测带系统服务的命令
    sys_delays = []
    for _ in range(200):
        start = time.perf_counter()
        subprocess.run(f"adb -s {DEVICE} shell input keyevent KEYCODE_BACK", shell=True, capture_output=True)
        end = time.perf_counter()
        sys_delays.append((end - start) * 1000)
    
    # 系统服务延迟 = 总延迟 - ADB 传输
    service_delays = [d - adb_avg for d in sys_delays]
    service_delays = [d for d in service_delays if d > 0]  # 过滤异常值
    return np.mean(service_delays), np.std(service_delays)

def main():
    print("=" * 60)
    print("时序抖动四分量测量 (API 33 模拟器)")
    print("=" * 60)
    
    # 预热
    print("预热中...")
    for _ in range(10):
        adb_shell("true")
    
    results = {}
    
    # 分量1
    mean1, std1 = measure_adb_roundtrip()
    results["ADB传输开销"] = (mean1, std1)
    print(f"  ✅ ADB 传输: {mean1:.2f} ± {std1:.2f} ms")
    
    # 分量2
    mean2, std2 = measure_system_service()
    results["系统服务响应"] = (mean2, std2)
    print(f"  ✅ 系统服务: {mean2:.2f} ± {std2:.2f} ms")
    
    # 分量3
    std3 = measure_kernel_noise()
    results["内核调度噪声"] = (std3, 0)
    print(f"  ✅ 内核噪声: {std3:.2f} ms")
    
    # 分量4
    mean4, std4 = measure_clock_precision()
    results["CLOCK_BOOTTIME读精度"] = (mean4, std4)
    print(f"  ✅ 时钟读精度: {mean4:.2f} ± {std4:.2f} ms")
    
    total = mean1 + mean2 + std3 + mean4
    print(f"\n合计抖动: {total:.2f} ms")
    print(f"论文原有总抖动: 49.18 ms")
    print(f"差值: {total - 49.18:.2f} ms")
    
    # 保存结果
    output_path = f"{OUTPUT_DIR}/jitter_components.json"
    with open(output_path, 'w') as f:
        json.dump({
            "device": DEVICE,
            "samples": N_SAMPLES,
            "results": {k: {"mean": v[0], "std": v[1]} for k, v in results.items()},
            "total_jitter_ms": total,
            "expected_jitter_ms": 49.18
        }, f, indent=2)
    print(f"\n结果已保存: {output_path}")

if __name__ == "__main__":
    main()
