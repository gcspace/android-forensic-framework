# 实验复现分步清单

## 前置条件
- Ubuntu 22.04 LTS
- Python 3.10+
- Android SDK (含 adb, emulator, avdmanager)
- OpenJDK 17+

## 第1步：克隆仓库
git clone https://github.com/guoce5920/android-forensic-framework.git
cd android-forensic-framework

## 第2步：安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

**预期结果**：无报错

## 第3步：创建并启动模拟器
avdmanager create avd -n avd_api_33 -k system-images;android-33;google_apis;x86_64 --device pixel --sdcard 512M
emulator -avd avd_api_33 -no-snapshot &
adb wait-for-device
adb shell getprop sys.boot_completed

**预期结果**：输出 1

## 第4步：运行基准场景
python3 experiments/run_real_device.py 33 config/scenarios/baseline_50.yaml --scheduler priority --max-concurrency 6

**预期结果**：输出总耗时和 JSON 文件路径

## 第5步：运行恶意场景
python3 experiments/run_real_device.py 33 config/scenarios/malicious_ransomware.yaml --scheduler priority --max-concurrency 6

**预期结果**：输出总耗时，标注完整率 100%

## 第6步：下游验证
python3 experiments/downstream_w6_final3.py

**预期结果**：输出分类准确率

## 第7步：查看结果
ls -la output/groundtruth/

**预期结果**：显示 JSON 文件

## 故障排查
参见 docs/troubleshooting.md
