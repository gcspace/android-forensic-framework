#!/usr/bin/env bash
# 采集 1-2 节的路径常量与目录快照证据：每个 SDK 版本一份 getprop + 存储路径快照。
# 用法：bash experiments/paper/collect_policy_evidence.sh
# 前置：已按四步开机（挂盘 → cd ~/aff → 自检 → ~ 下起 adb），且 AVD 名为 rev_api28…rev_api34
set -u
ADB=adb
# emulator 可执行文件：默认取 PATH 中的 emulator，可用 EMULATOR=/path/to/emulator 覆盖
EMULATOR="${EMULATOR:-emulator}"
OUT_ROOT="output/paper/policy_evidence_$(date +%Y%m%d_%H%M)"
mkdir -p "$OUT_ROOT"

collect_one() {
  local avd="$1" api="$2"
  local dir="$OUT_ROOT/api${api}"
  mkdir -p "$dir"
  # 设备等待设上限，避免某一版本起不来时整批挂死
  timeout 180 "$ADB" -s emulator-5554 wait-for-device || { echo "api${api} wait-for-device 超时，跳过" | tee -a "$OUT_ROOT/collect.log"; return 1; }
  # 等系统的 package manager 就绪，避免 policy 读取到半初始化状态（最多 120 s）
  local n=0
  until [ "$("$ADB" -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    sleep 2; n=$((n + 1))
    if [ "$n" -ge 60 ]; then
      echo "api${api} sys.boot_completed 未置 1，继续采集并在日志留痕" | tee -a "$OUT_ROOT/collect.log"
      break
    fi
  done
  sleep 3

  "$ADB" -s emulator-5554 shell getprop > "$dir/getprop_all.txt" 2>&1
  "$ADB" -s emulator-5554 shell getprop | grep -Ei 'sdk|release|fingerprint|build.type|build.tags|fuse|scoped' > "$dir/getprop_filtered.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'cat /proc/filesystems' > "$dir/proc_filesystems.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'mount | grep -Ei "emulated|fuse|sdcard"' > "$dir/mount_storage.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'ls -ld /sdcard /storage/emulated/0 /storage/emulated /data/media/0 /mnt/user/0/primary 2>&1' > "$dir/path_ls_ld.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'ls -l /storage/emulated 2>&1' > "$dir/storage_emulated_ls.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'ls -ld /sdcard/Android /sdcard/Android/data /sdcard/Android/media /sdcard/DCIM /sdcard/Documents /sdcard/Download 2>&1' > "$dir/dir_snapshot.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'ls -ld /data/system/packages.xml /data/system/storage.xml 2>&1' > "$dir/policy_files.txt" 2>&1
  "$ADB" -s emulator-5554 shell 'sm list-volumes all 2>&1' > "$dir/sm_volumes.txt" 2>&1

  # 与 version_policy.py 同口径的策略表；再按本版本取行，作为快照的对照项
  python3 experiments/paper/version_policy.py > "$dir/policy_table.txt" 2>&1
  awk -F'\t' -v a="$api" '$1 == a' "$dir/policy_table.txt" > "$dir/policy_target.txt" 2>&1

  printf 'api=%s avd=%s finished\n' "$api" "$avd" | tee -a "$OUT_ROOT/collect.log"
}

for pair in "rev_api28:28" "rev_api29:29" "rev_api30:30" "rev_api31:31" "rev_api32:32" "rev_api33:33" "rev_api34:34"; do
  avd="${pair%%:*}"; api="${pair##*:}"
  echo "== boot $avd (API $api) =="
  if "$ADB" devices | grep -q 'emulator-5554'; then
    timeout 30 "$ADB" -s emulator-5554 emu kill >/dev/null 2>&1
    sleep 3
  fi
  nohup "$EMULATOR" -avd "$avd" -no-snapshot -no-audio -gpu swiftshader_indirect -no-boot-anim -memory 1536 -cores 4 > "$OUT_ROOT/emulator_${api}.log" 2>&1 &
  collect_one "$avd" "$api"
  if "$ADB" devices | grep -q 'emulator-5554'; then
    timeout 30 "$ADB" -s emulator-5554 emu kill >/dev/null 2>&1
  fi
  sleep 5
done

# 逐文件哈希与清单，便于 Windows 侧 verify_results.py 校验
( cd "$OUT_ROOT" && find . -type f ! -name files.txt ! -name SHA256SUMS -print | sort | while read -r f; do sha256sum "$f"; done > SHA256SUMS )
( cd "$OUT_ROOT" && find . -type f ! -name files.txt -print | sort > files.txt )
printf '输出目录：%s\n' "$OUT_ROOT"
