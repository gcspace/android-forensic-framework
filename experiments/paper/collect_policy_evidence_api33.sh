#!/usr/bin/env bash
# 仅补采 API33（rev_api33）的 policy 证据：等 FUSE 挂载就绪后再取样，覆盖上一批 api33 目录。
# 用法：bash experiments/paper/collect_policy_evidence_api33.sh
set -u
ADB="${ADB:-adb}"
EMULATOR="${EMULATOR:-emulator}"
SERIAL=emulator-5554
AVD=rev_api33
API=33
OUT_ROOT="output/paper/policy_evidence_api33_fix_$(date +%Y%m%d_%H%M)"
DIR="$OUT_ROOT/api33"
mkdir -p "$DIR"

echo "== 启动 $AVD =="
if "$ADB" devices | grep -q "$SERIAL"; then timeout 30 "$ADB" -s "$SERIAL" emu kill >/dev/null 2>&1; sleep 3; fi
nohup "$EMULATOR" -avd "$AVD" -no-snapshot -no-audio -gpu swiftshader_indirect -no-boot-anim -memory 1536 -cores 4 > "$OUT_ROOT/emulator_${API}.log" 2>&1 &

timeout 240 "$ADB" -s "$SERIAL" wait-for-device || { echo "wait-for-device 超时" | tee -a "$OUT_ROOT/collect.log"; exit 1; }
n=0
until [ "$("$ADB" -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 3; n=$((n + 1)); [ "$n" -ge 60 ] && break
done
# 解锁并保持常亮，避免 FUSE/媒体卷因锁屏或休眠未挂载
"$ADB" -s "$SERIAL" shell svc power stayon usb >/dev/null 2>&1
"$ADB" -s "$SERIAL" shell input keyevent 82 >/dev/null 2>&1
"$ADB" -s "$SERIAL" shell input keyevent 224 >/dev/null 2>&1

# 关键：等到 /storage/emulated/0 可列举（FUSE 就绪）再采集，最多等 180 s
m=0
until "$ADB" -s "$SERIAL" shell ls /storage/emulated/0 >/dev/null 2>&1; do
  sleep 3; m=$((m + 1))
  if [ "$m" -ge 60 ]; then echo "FUSE 未就绪（180 s），仍采集并留痕" | tee -a "$OUT_ROOT/collect.log"; break; fi
done
sleep 3

"$ADB" -s "$SERIAL" shell getprop > "$DIR/getprop_all.txt" 2>&1
"$ADB" -s "$SERIAL" shell getprop | grep -Ei 'sdk|release|fingerprint|build.type|build.tags|fuse|scoped' > "$DIR/getprop_filtered.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'cat /proc/filesystems' > "$DIR/proc_filesystems.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'mount | grep -Ei "emulated|fuse|sdcard"' > "$DIR/mount_storage.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'ls -ld /sdcard /storage/emulated/0 /storage/emulated /data/media/0 /mnt/user/0/primary 2>&1' > "$DIR/path_ls_ld.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'ls -l /storage/emulated 2>&1' > "$DIR/storage_emulated_ls.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'ls -ld /sdcard/Android /sdcard/Android/data /sdcard/Android/media /sdcard/DCIM /sdcard/Documents /sdcard/Download 2>&1' > "$DIR/dir_snapshot.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'ls -ld /data/system/packages.xml /data/system/storage.xml 2>&1' > "$DIR/policy_files.txt" 2>&1
"$ADB" -s "$SERIAL" shell 'sm list-volumes all 2>&1' > "$DIR/sm_volumes.txt" 2>&1
python3 experiments/paper/version_policy.py > "$DIR/policy_table.txt" 2>&1
awk -F'\t' -v a="$API" '$1 == a' "$DIR/policy_table.txt" > "$DIR/policy_target.txt" 2>&1

# 采集后自检：path_ls_ld 不得含 "not connected"
if grep -q 'not connected' "$DIR/path_ls_ld.txt"; then
  echo "!! path_ls_ld 仍含 not connected，请检查 emulator_${API}.log" | tee -a "$OUT_ROOT/collect.log"
fi
timeout 30 "$ADB" -s "$SERIAL" emu kill >/dev/null 2>&1

( cd "$OUT_ROOT" && find . -type f ! -name files.txt ! -name SHA256SUMS -print | sort | while read -r f; do sha256sum "$f"; done > SHA256SUMS )
( cd "$OUT_ROOT" && find . -type f ! -name files.txt -print | sort > files.txt )
printf '输出目录：%s\n' "$OUT_ROOT"
