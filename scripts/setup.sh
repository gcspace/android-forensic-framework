#!/bin/bash
set -e

echo "=== Android 取证数据集生成框架 安装脚本 ==="

sudo apt update
sudo apt install -y python3.10 python3-pip adb openjdk-17-jdk git curl wget unzip

ANDROID_SDK_ROOT="$HOME/android-sdk"
mkdir -p "$ANDROID_SDK_ROOT"
export ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT"
export PATH="$PATH:$ANDROID_SDK_ROOT/tools/bin:$ANDROID_SDK_ROOT/platform-tools"

if [ ! -f "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]; then
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O /tmp/sdk.zip
    unzip /tmp/sdk.zip -d "$ANDROID_SDK_ROOT"
    mv "$ANDROID_SDK_ROOT/cmdline-tools" "$ANDROID_SDK_ROOT/latest"
    mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools"
    mv "$ANDROID_SDK_ROOT/latest" "$ANDROID_SDK_ROOT/cmdline-tools/"
    rm /tmp/sdk.zip
fi

yes | $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --licenses
$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-33" "system-images;android-33;google_apis;x86_64"

pip3 install -r requirements.txt

echo "安装完成！"
echo "请将以下内容添加到 ~/.bashrc:"
echo "export ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT"
echo "export PATH=\$PATH:\$ANDROID_SDK_ROOT/tools/bin:\$ANDROID_SDK_ROOT/platform-tools"
