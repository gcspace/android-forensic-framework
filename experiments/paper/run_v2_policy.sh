#!/usr/bin/env bash
# 路线 A 一键采集：版本策略真分支 + 痕迹审计 + 贡献1消融 + 内存采样
# 用法（Linux 侧，仓库根目录）：
#   bash experiments/paper/run_v2_policy.sh --step ml
#   bash experiments/paper/run_v2_policy.sh --step matrix
#   bash experiments/paper/run_v2_policy.sh --step ablation
#   bash experiments/paper/run_v2_policy.sh --step mem
#   bash experiments/paper/run_v2_policy.sh --step all
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
SHARE="${SHARE:-${REV_SHARE_LINUX:-/mnt/revshare}}"
API_LIST="${API_LIST:-28 29 30 31 32 33 34}"
REP="${REP:-5}"
W_MATRIX="${W_MATRIX:-1}"
STEP=""

while [ $# -gt 0 ]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    *) shift ;;
  esac
done

RUNS="$REPO/output/paper/runs_v2"
TRACE="$REPO/output/paper/trace_v2"
ABL="$REPO/output/paper/ablation_v2"
MEM="$REPO/output/paper/mem_v2"
ML="$REPO/output/paper/downstream_split"

clean_emulator_files() {
  adb shell "rm -f /sdcard/test*.txt /sdcard/Download/test*.txt /sdcard/Pictures/test*.txt /sdcard/DCIM/test*.txt /sdcard/Android/data/test*.txt" >/dev/null 2>&1 || true
}

package() {
  local tag="$1" only="$2"
  bash "$HERE/package_results.sh" --tag "$tag" --only "$only"
}

step_ml() {
  echo "== [1/4] 分类重做：按文件分组划分 =="
  mkdir -p "$ML"
  ls -1 "$REPO/output/groundtruth"/real_execution_20260818_1[15]*.json >/dev/null 2>&1 || {
    echo "缺少 08-18 groundtruth 文件，请先用 ls 确认文件前缀后改 MAL_GLOB/NRM_GLOB"; return 1; }
  python3 "$HERE/split_by_source.py" \
    --malicious "${MAL_GLOB:-output/groundtruth/real_execution_20260818_165*.json}" \
    --normal "${NRM_GLOB:-output/groundtruth/real_execution_20260818_113*.json}" \
    --out "$ML/split_summary.json"
  package "mlv2" "output/paper/downstream_split/*.json"
}

step_matrix() {
  echo "== [2/4] 版本策略 on/off 矩阵（${API_LIST} × 2 × ${REP}）=="
  mkdir -p "$RUNS" "$TRACE"
  for api in $API_LIST; do
    adb devices | grep -q emulator || { echo "请先启动 API $api 的 AVD"; return 1; }
    for ad in on off; do
      clean_emulator_files
      for i in $(seq 1 "$REP"); do
        python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
          --api "$api" --max-concurrency "$W_MATRIX" --scheduler priority \
          --adapter "$ad" --out "$RUNS" --tag "v2_${i}"
      done
      python3 "$HERE/trace_audit.py" config/scenarios/baseline_50.yaml \
        --api "$api" --adapter "$ad" --out "$TRACE/api${api}_${ad}.json"
    done
    package "policy_api${api}" "output/paper/runs_v2/*api${api}_*.json,output/paper/trace_v2/api${api}_*.json"
  done
}

step_ablation() {
  echo "== [3/4] 贡献1消融：原子拆分 vs 整场景单原子（API33, W=6）=="
  mkdir -p "$ABL"
  clean_emulator_files
  for i in $(seq 1 "$REP"); do
    python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
      --api 33 --max-concurrency 6 --scheduler priority --adapter on \
      --atomic-mode dag --out "$ABL" --tag "dag_${i}"
  done
  for i in $(seq 1 "$REP"); do
    python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
      --api 33 --max-concurrency 6 --scheduler priority --adapter on \
      --atomic-mode single --out "$ABL" --tag "single_${i}"
  done
  package "ablation" "output/paper/ablation_v2/*.json"
}

step_mem() {
  echo "== [4/4] 内存采样（7 版本 × 3 次，独立目录，不进计时口径）=="
  mkdir -p "$MEM"
  for api in $API_LIST; do
    adb devices | grep -q emulator || { echo "请先启动 API $api 的 AVD"; return 1; }
    for i in 1 2 3; do
      python3 "$HERE/run_parallel.py" config/scenarios/baseline_50.yaml \
        --api "$api" --max-concurrency 1 --scheduler priority --adapter on \
        --mem-sample --out "$MEM" --tag "mem_${i}"
    done
  done
  package "memv2" "output/paper/mem_v2/*.json"
}

case "$STEP" in
  ml|matrix|ablation|mem) "step_$STEP" ;;
  all) step_ml; step_matrix; step_ablation; step_mem ;;
  *) echo "用法: bash experiments/paper/run_v2_policy.sh --step ml|matrix|ablation|mem|all"; exit 2 ;;
esac
