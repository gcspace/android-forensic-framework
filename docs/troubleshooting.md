# 故障排查文档

本文档整理了使用本论文研究过程中可能遇到的常见问题及解决方案。


## 一、ADB 连接与设备识别

### 1. adb devices 无设备输出

现象：执行 adb devices 后列表为空。

可能原因及解决：
- USB 调试未开启：进入手机开发者选项，开启 USB 调试
- USB 连接模式错误：选择文件传输或MTP模式，而非仅充电
- ADB 服务异常：adb kill-server && adb start-server
- 重新插拔 USB 线缆后再次执行 adb devices

### 2. adb devices 显示 unauthorized

现象：设备列表中出现 unauthorized 状态。

解决：
- 手机屏幕会弹出 RSA 指纹授权提示，点击允许
- 重新插拔 USB 线缆后再次执行 adb devices
- 若未弹出授权框，尝试 adb kill-server && adb start-server

### 3. error: more than one device/emulator

现象：同时连接了多个设备，ADB 无法确定目标。

解决：
# 指定设备序列号执行命令
adb -s 33061FDH2002UE shell ls

# 或关闭不需要的模拟器
adb -s emulator-5554 emu kill


## 二、模拟器启动与运行

### 4. 模拟器启动卡死，长时间停留在启动动画

现象：emulator -avd avd_api_33 后 5-10 分钟仍无法进入桌面。

可能原因及解决：

- GPU 渲染不兼容：使用软件渲染参数启动
emulator -avd avd_api_33 -no-window -gpu swiftshader_indirect &

- 多个模拟器实例冲突：先关闭所有实例再启动
pkill -9 -f emulator
sleep 3
emulator -avd avd_api_33 -no-snapshot &

- AVD 镜像损坏：删除并重建 AVD
avdmanager delete avd -n avd_api_33
avdmanager create avd -n avd_api_33 -k "system-images;android-33;google_apis;x86_64" --device "pixel" --sdcard 512M

### 5. FATAL | Running multiple emulators with the same AVD

现象：启动模拟器时报错，提示同一 AVD 存在多个实例。

解决：
pkill -9 -f emulator
sleep 3
emulator -avd avd_api_33 -no-snapshot &

### 6. 模拟器在终端关闭后自动退出

现象：关闭终端后模拟器进程终止。

解决：使用 & 后台运行，或使用 nohup：
emulator -avd avd_api_33 -no-snapshot &

# 或
nohup emulator -avd avd_api_33 -no-snapshot > /dev/null 2>&1 &

### 7. 模拟器环境退化，实验数据不可复现

现象：重跑实验后，时序采集抖动值与论文报告值出现较大偏差。

原因：AVD 长期使用后，系统缓存、文件系统元数据、FUSE 层性能状态发生不可逆漂移。

解决：删除 AVD 并重建，从干净状态重新开始：
avdmanager delete avd -n avd_api_33
avdmanager create avd -n avd_api_33 -k "system-images;android-33;google_apis;x86_64" --device "pixel" --sdcard 512M
emulator -avd avd_api_33 -no-snapshot &

建议：每次正式实验前，从全新 AVD 启动并执行一次预热运行（不计入统计），使系统完成必要缓存加载。


## 三、文件操作与原子执行

### 8. FILE_CREATE 原子失败：touch: '/path/': Is a directory

现象：日志显示 touch: '/path/': Is a directory，原子标记为 failed。

原因：YAML 配置中路径末尾带 /，touch 命令无法处理目录路径。

解决：修改 YAML 配置，移除路径末尾的斜杠：
# 错误
params: {path: "private_stolen_data/"}

# 正确
params: {path: "private_stolen_data/.placeholder"}

### 9. FILE_CREATE 原子失败：/data/local/tmp/ 写入失败

现象：文件操作原子在模拟器上执行失败，日志提示权限错误。

原因：部分 AOSP 模拟器镜像中 /data/local/tmp/ 对 ADB shell 可能受限。

解决：确认场景配置中文件操作路径为 /data/local/tmp/[场景名]/ 子目录，当前框架代码已兼容该路径。若仍有问题，改用真机运行。

### 10. NET_DOWNLOAD 原子失败：wget: inaccessible or not found

现象：日志显示 /system/bin/sh: wget: inaccessible or not found。

原因：AOSP 无 GMS 镜像不包含 wget 命令。

解决：当前框架已修改 core/executor/atomic_ops.py 中 NetDownload 类，使用 adb push 替代 wget，无需额外操作。若使用旧版本代码，请更新至最新版本。

### 11. FILE_COPY 原子失败：No such file or directory

现象：文件复制原子失败，提示源文件不存在。

原因及解决：
- 检查 YAML 配置中 src 指向的文件是否在场景中先被创建
- 确认 depends_on 依赖关系已正确设置
- 若源文件由其他原子生成，确保该原子在依赖链中排在前面

### 12. APP_START 原子失败：包名不存在

现象：APP_START 原子执行失败，日志显示包名无法启动。

原因：YAML 中指定的包名在 AVD 中不存在（AOSP 无 GMS 镜像不包含 calculator2、dialer 等应用）。

解决：将包名替换为 AVD 中已安装的应用。论文验证通过的包名包括：
- com.android.settings
- com.google.android.deskclock
- com.google.android.contacts
- com.google.android.calendar
- com.google.android.apps.youtube.music

同时修改对应的 APP_STOP 原子，保持 start/stop 配对一致。

### 13. 目录残留导致原子反复失败

现象：某些原子因残留目录而重复失败。

解决：清理残留目录：
adb shell rm -rf /data/local/tmp/.encrypted
adb shell rm -rf /sdcard/.encrypted
adb shell rm -rf /data/local/tmp/fuse_test


## 四、快照与数据持久化

### 14. 快照保存失败：FATAL | Running multiple emulators...

现象：执行 emulator -snapshot clean_base 报错。

解决：在模拟器运行时通过 ADB 命令保存快照：
adb -s emulator-5554 emu avd snapshot save clean_base

### 15. 从快照启动后 input 命令报错

现象：Exception occurred while executing 'text': android.view.KeyCharacterMap$UnavailableException。

原因：快照保存时输入子系统未完全初始化，恢复后无法加载键盘映射。

解决：放弃快照，每次实验前从干净 AVD 正常启动（-no-snapshot），确保系统服务完整初始化。


## 五、实验脚本与数据处理

### 16. 下游验证脚本报错：ModuleNotFoundError: No module named 'sklearn'

现象：执行下游验证脚本时提示缺少 sklearn。

解决：
source venv/bin/activate
pip install scikit-learn numpy -i https://pypi.tuna.tsinghua.edu.cn/simple

### 17. 实验数据抖动值与论文不一致

现象：重跑实验后，时序采集抖动值与论文报告值出现偏差。

可能原因及排查：

- 检查 input 命令延迟是否正常：
time adb shell input text "test"
# 应在 300-500ms 以内

- 确认模拟器是否完全启动：
adb shell getprop sys.boot_completed
# 应输出 1

- 检查是否使用了干净的 AVD（参考第 7 条）
- 确认实验前已执行预热运行（首次运行不计入统计）

### 18. 分析脚本找不到数据文件

现象：分析脚本报错 文件不存在。

解决：使用最新下游验证脚本：
python3 experiments/downstream_w6_final3.py

如需使用补充分析脚本，检查并修改脚本中数据文件路径，指向实际存在的 groundtruth JSON 文件。


## 六、模拟器创建与配置

### 19. 模拟器创建失败

现象：avdmanager create avd 报错。

解决：
# 删除旧 AVD
avdmanager delete avd -n avd_api_33

# 重新创建
avdmanager create avd -n avd_api_33 -k "system-images;android-33;google_apis;x86_64" --device "pixel" --sdcard 512M

### 20. 模拟器系统镜像下载慢或失败

解决：使用国内镜像源：
# 配置 SDK Manager 使用清华镜像
export SDK_MANAGER_OPTS="-Dhttps.proxyHost=mirrors.tuna.tsinghua.edu.cn -Dhttps.proxyPort=443"

# 或直接修改 ~/.android/repositories.cfg


## 七、真机相关

### 21. 真机连接后 USB 调试无反应

解决：
- 确认 USB 连接模式为文件传输或MTP
- 在开发者选项中重新开关 USB 调试
- 更换 USB 线缆或接口（建议使用原装线缆）

### 22. 真机连接后 adb devices 显示 offline

解决：
adb kill-server
adb start-server
adb devices

# 若仍未恢复，重启手机后重试


## 八、通用检查清单

遇到问题时，建议先按以下清单逐项排查：

检查项：ADB 服务运行
命令/方法：adb devices
预期结果：设备列表正常显示

检查项：模拟器启动完成
命令/方法：adb shell getprop sys.boot_completed
预期结果：输出 1

检查项：Input 命令延迟
命令/方法：time adb shell input text "test"
预期结果：< 500ms

检查项：虚拟环境已激活
命令/方法：which python3
预期结果：显示项目 venv 路径

检查项：代码为最新版本
命令/方法：git pull
预期结果：显示 Already up to date
