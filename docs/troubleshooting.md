# 故障排查文档

## 一、ADB 连接与设备识别

### 1. `adb devices` 无输出
- 检查 USB 调试是否开启
- 重新插拔 USB 线缆
- `adb kill-server && adb start-server`

### 2. `error: more than one device/emulator`
```bash
adb -s 33061FDH2002UE shell ls
# 或关闭模拟器
adb -s emulator-5554 emu kill
```

### 3. 模拟器在终端关闭后退出
```bash
emulator -avd avd_api_33 -no-snapshot &
```

## 二、文件操作与权限

### 4. `/data/local/tmp/` 写入失败（模拟器）
- 原因：AOSP 模拟器 `/data/local/tmp/` 对 ADB shell 不可写
- 解决：改用真机运行

### 5. `touch: '/path/': Is a directory`
- 原因：路径末尾带斜杠
- 解决：修改 YAML 配置，移除末尾斜杠

### 6. 目录残留导致原子失败
```bash
adb shell rm -rf /data/local/tmp/.encrypted
adb shell rm -rf /sdcard/.encrypted
```

## 三、时序与数据

### 7. 时序偏差巨大
- 原因：实验日志与 logcat 文件配对错误
- 解决：按时间戳配对文件

## 四、场景配置

### 8. `No such file or directory`
```bash
adb shell mkdir -p /data/local/tmp/Documents
for i in {1..15}; do
    adb shell "echo 'test' > /data/local/tmp/Documents/doc_${i}.pdf"
done
```

### 9. 模拟器创建失败
```bash
avdmanager delete avd -n avd_api_33
avdmanager create avd -n avd_api_33 -k "system-images;android-33;google_apis;x86_64" --device "pixel" --sdcard 512M
```

## 五、实验设备

### 10. 真机连接后 `adb devices` 显示 unauthorized
- 手机屏幕会弹出 RSA 指纹授权提示，点击"允许"
- 重新插拔 USB 线缆后再次执行 `adb devices`
