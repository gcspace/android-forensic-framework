#!/bin/bash
set -e

echo "=== 创建多版本 AVD 模拟器 ==="

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
export PATH="$PATH:$ANDROID_SDK_ROOT/tools/bin:$ANDROID_SDK_ROOT/platform-tools"

sdkmanager "system-images;android-28;google_apis;x86_64"
sdkmanager "system-images;android-29;google_apis;x86_64"
sdkmanager "system-images;android-31;google_apis;x86_64"
sdkmanager "system-images;android-33;google_apis;x86_64"

avdmanager create avd -n avd_api_28 -k "system-images;android-28;google_apis;x86_64" --device "pixel" --sdcard 512M
avdmanager create avd -n avd_api_29 -k "system-images;android-29;google_apis;x86_64" --device "pixel" --sdcard 512M
avdmanager create avd -n avd_api_31 -k "system-images;android-31;google_apis;x86_64" --device "pixel" --sdcard 512M
avdmanager create avd -n avd_api_33 -k "system-images;android-33;google_apis;x86_64" --device "pixel" --sdcard 512M

echo "AVD 创建完成！"
echo "启动方法："
echo "  emulator -avd avd_api_28 -no-snapshot &"
echo "  emulator -avd avd_api_29 -no-snapshot &"
echo "  emulator -avd avd_api_31 -no-snapshot &"
echo "  emulator -avd avd_api_33 -no-snapshot &"
