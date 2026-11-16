#!/usr/bin/env bash
# 第二轮：痕迹漏检证据 + 同一会话内重采表5/表6/消融
# 前提：一次只挂一台模拟器，脚本会核对 ro.build.version.sdk 与 --api 是否一致。
# 用法：
#   bash experiments/paper/run_v2_round2.sh --step trace
#   bash experiments/paper/run_v2_round2.sh --step timing
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
API_LIST="${API_LIST:-28 29 30 31 32 33 34}"
REP="${REP:-5}"
STEP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    *) shift ;;
  esac
done

RUNS="$REPO/output/paper/runs_v2"
OFFRUNS="$REPO/output/paper/runs_v2_offprobe"
TRACE="$REPO/output/paper/trace_v2"
MEM="$REPO/output/paper/mem_v2"
TIMING="$REPO/output/paper/timing_v2"
ABL="$REPO/output/paper/ablation_v2"

check_sdk() {
  local want="$1" got
  got="$(adb shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r')"
  [ "$got" = "$want" ] || { echo "当前设备 SDK=$got，与 --api $want 不符，已中止"; return 1; }
}

clean_emulator_files() {
  adb shell "rm -f /sdcard/test*.txt /sdcard/Download/test*.txt /sdcard/Pictures/test*.txt /sdcard/DCIM/test*.txt /sdcard/Android/data/test*.txt" >/dev/null 2>&1 || true
}

pkg() { bash "$HERE/package_results.sh" --tag "$1" --only "$2"; }

step_trace() {
  echo "== 痕迹漏检证据 + 内存采样（逐 AVD）=="
  mkdir -p "$OFFRUNS" "$TRACE" "$MEM"
  for api in $API_LIST; do
    check_sdk "$api"
    clean_emulator_files
    for i in 1 2 3; do
      python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
        --api "$api" --max-concurrency 1 --scheduler priority --adapter on \
        --mem-sample --out "$MEM" --tag "mem_${i}"
    done
    # 关键证据：adapter=off 落 /sdcard，但按目标版本策略检索
    python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
      --api "$api" --max-concurrency 1 --scheduler priority --adapter off \
      --out "$OFFRUNS" --tag "offprobe"
    python3 "$HERE/trace_audit.py" config/scenarios/baseline_50.yaml \
      --api "$api" --adapter on --out "$TRACE/api${api}_offrun.json"
    clean_emulator_files
    python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
      --api "$api" --max-concurrency 1 --scheduler priority --adapter on \
      --out "$RUNS" --tag "onprobe"
    python3 "$HERE/trace_audit.py" config/scenarios/baseline_50.yaml \
      --api "$api" --adapter on --out "$TRACE/api${api}_onrun.json"
    clean_emulator_files
    pkg "trace_api${api}" "output/paper/trace_v2/*api${api}_*.json,output/paper/mem_v2/*api${api}_*.json,output/paper/runs_v2_offprobe/*api${api}_*.json"
  done
}

step_timing() {
  echo "== 表5/表6/消融 同一会话重采（仅 API33）=="
    check_sdk 33
    mkdir -p "$TIMING" "$ABL"
    for w in 1 2 3 4 6 8 12; do
      clean_emulator_files
      for i in $(seq 1 "$REP"); do
        python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
          --api 33 --max-concurrency "$w" --scheduler priority --adapter on \
          --out "$TIMING" --tag "wm${w}_r${i}"
      done
    done
    for w in 6; do
      clean_emulator_files
      for i in $(seq 1 "$REP"); do
        python3 "$HERE/run_parallel.py" config/scenarios/high_parallel_120.yaml \
          --api 33 --max-concurrency 1 --scheduler priority --adapter on \
          --out "$TIMING" --tag "hp120_w1_r${i}"
        python3 "$HERE/run_parallel.py" config/scenarios/high_parallel_120.yaml \
          --api 33 --max-concurrency "$w" --scheduler priority --adapter on \
          --out "$TIMING" --tag "hp120_w${w}_r${i}"
        python3 "$HERE/run_parallel.py" config/scenarios/high_parallel_120.yaml \
          --api 33 --max-concurrency "$w" --scheduler fifo --adapter on \
          --out "$TIMING" --tag "hp120_fifo_w${w}_r${i}"
      done
    done
    for sc in malicious_privacy malicious_phishing malicious_ransomware; do
      clean_emulator_files
      for i in $(seq 1 "$REP"); do
        python3 "$HERE/run_parallel.py" config/scenarios/${sc}.yaml \
          --api 33 --max-concurrency 1 --scheduler priority --adapter on \
          --out "$TIMING" --tag "${sc}_r${i}"
      done
    done
    for i in $(seq 1 "$REP"); do
      python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
        --api 33 --max-concurrency 6 --scheduler priority --adapter on \
        --atomic-mode dag --out "$ABL" --tag "dag_${i}"
      python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
        --api 33 --max-concurrency 6 --scheduler priority --adapter on \
        --atomic-mode single --out "$ABL" --tag "single_${i}"
    done
    pkg "timing_v2" "output/paper/timing_v2/*.json,output/paper/ablation_v2/*.json"
}

case "$STEP" in
  trace) step_trace ;;
  timing) step_timing ;;
  *) echo "用法: bash experiments/paper/run_v2_round2.sh --step trace|timing"; exit 2 ;;
esac
