#!/usr/bin/env bash
# 一键跑完七个版本：开机 → 探针 → 抖动 → 矩阵 → 关机，逐版本串行。
# 用法：bash experiments/paper/run_session.sh
#      bash experiments/paper/run_session.sh --apis "28 33" --probe-repeats 3
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
REPO="${REPO:-${REV_REPO:-$(cd "$HERE/../.." && pwd)}}"
APIS="${APIS:-28 29 30 31 32 33 34}"
BOOT_TIMEOUT=240
PACKAGE=1

while [ $# -gt 0 ]; do
  case "$1" in
    --apis) APIS="$2"; shift 2 ;;
    --boot-timeout) BOOT_TIMEOUT="$2"; shift 2 ;;
    --no-package) PACKAGE=0; shift ;;
    --repo) REPO="$2"; shift 2 ;;
    *) echo "未知参数 $1"; exit 2 ;;
  esac
done

cd "$REPO" || { echo "代码目录不存在：$REPO"; exit 1; }
mkdir -p output/paper/logs
LOG="output/paper/logs/session_$(date '+%Y%m%d_%H%M').log"

say() { echo "$@" | tee -a "$LOG"; }

wait_boot() {
  adb wait-for-device
  for i in $(seq 1 $((BOOT_TIMEOUT / 2))); do
    if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

say "会话开始：$(date '+%F %T')  版本：$APIS"
bash experiments/paper/preflight.sh | tee -a "$LOG" || { say "自检未通过，终止"; exit 1; }

for api in $APIS; do
  say ""
  say "===== API $api ====="
  adb kill-server >/dev/null 2>&1 || true
  emulator -avd "rev_api${api}" -no-snapshot -no-audio -no-boot-anim -no-window \
           -gpu swiftshader_indirect -port 5554 >>"$LOG" 2>&1 &
  if ! wait_boot; then
    say "API $api 启动超时，跳过"
    adb emu kill >/dev/null 2>&1 || true
    continue
  fi
  sdk=$(adb shell getprop ro.build.version.sdk | tr -d '\r')
  say "已启动，设备报告 sdk=$sdk"
  [ "$sdk" = "$api" ] || { say "版本不符（期望 $api），跳过"; adb emu kill; continue; }

  for r in 1 2 3; do
    python3 experiments/paper/storage_probe.py --api "$api" --repeat "$r" \
      --out output/paper/probe 2>&1 | tail -3 | tee -a "$LOG"
  done

  python3 experiments/paper/measure_jitter.py --api "$api" \
    --out output/paper/jitter 2>&1 | tail -5 | tee -a "$LOG"

  python3 experiments/paper/run_matrix.py --only-api "$api" \
    --out output/paper/runs --repeats 5 2>&1 | tail -8 | tee -a "$LOG"

  adb emu kill >/dev/null 2>&1 || true
  sleep 5
  say "API $api 完成：$(date '+%T')"
done

say ""
say "汇总结论："
python3 experiments/paper/verify_matrix.py --dir output/paper/runs 2>&1 | tail -6 | tee -a "$LOG"
python3 experiments/paper/analyze_runs.py --dir output/paper/runs 2>&1 | tail -12 | tee -a "$LOG"

if [ "$PACKAGE" -eq 1 ]; then
  bash experiments/paper/package_results.sh --tag "session_$(date '+%Y%m%d_%H%M')" | tee -a "$LOG"
fi
say "会话结束：$(date '+%F %T')，日志：$LOG"
