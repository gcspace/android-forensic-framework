#!/usr/bin/env bash
# 建立七套配置一致的 AVD（28/29/30/31/32/33/34）。
# 必须在 Linux 侧执行；同一份镜像参数是跨版本可比的前提。
# 硬件参数取论文 4.1 所述实测配置：1.5 GB 内存、6 GB 数据分区、512 MB SD 卡；
# 虚实对照用的 API 35 AVD 除外，其内存 2 GB、数据分区 8 GB，可按以下环境变量覆盖：
#   APIS_OVERRIDE="35" RAM_MB=2048 DATA_SIZE=8G bash make_avds.sh
set -euo pipefail

SDK="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.android/avd}"
read -r -a APIS <<< "${APIS_OVERRIDE:-28 29 30 31 32 33 34}"
DEVICE="${DEVICE:-pixel_5}"
RAM_MB="${RAM_MB:-1536}"
DATA_SIZE="${DATA_SIZE:-6442450944}"   # 6 GB。API 35 AVD 用 8G
SDCARD_MB="${SDCARD_MB:-512}"

export PATH="$SDK/cmdline-tools/latest/bin:$SDK/platform-tools:$SDK/emulator:$PATH"

for api in "${APIS[@]}"; do
  pkg="system-images;android-${api};google_apis;x86_64"
  echo "== API ${api}: ${pkg}"
  yes | sdkmanager --install "${pkg}" >/dev/null 2>&1 || true
  if avdmanager list avd | grep -q "Name: rev_api${api}$"; then
    echo "   已存在，跳过创建"
  else
    echo no | avdmanager create avd -n "rev_api${api}" -k "${pkg}" -d "${DEVICE}" --force
  fi
  ini="${AVD_HOME}/rev_api${api}.avd/config.ini"
  # 统一硬件参数：内存、存储、GPU、关闭快照，避免版本间被硬件差异污染
  sed -i '/^hw\.ramSize=/d;/^disk\.dataPartition\.size=/d;/^hw\.gpu\.mode=/d;/^hw\.gpu\.enabled=/d;/^fastboot\.forceColdBoot=/d;/^hw\.keyboard=/d;/^sdcard\.size=/d' "$ini"
  cat >> "$ini" <<EOF
hw.ramSize=${RAM_MB}
disk.dataPartition.size=${DATA_SIZE}
sdcard.size=${SDCARD_MB}M
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
fastboot.forceColdBoot=yes
hw.keyboard=yes
EOF
done

echo
echo "已创建："
avdmanager list avd | grep -E "Name:|Based on:" || true
echo
echo "启动示例：emulator -avd rev_api33 -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect &"
echo "就绪判定：adb wait-for-device && adb shell getprop sys.boot_completed 返回 1"
