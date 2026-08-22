# Android 取证数据集生成框架

《多版本 Android 分区存储下基于原子操作与 DAG 调度的取证数据集生成方法》的实验代码与数据。

## 环境要求

- Ubuntu 22.04 LTS
- Python 3.10.12
- ADB 1.0.41
- OpenJDK 17

## 快速开始

注意：本文实验配置为 --max-concurrency 6（由 W 参数敏感性实验确定），以下所有命令均使用该配置。

### 安装依赖

pip install -r requirements.txt

### 启动模拟器（API 33）

emulator -avd avd_api_33 -no-snapshot &
adb wait-for-device

### 运行实验

基准场景（20/50/100步）：
python3 experiments/run_real_device.py 33 config/scenarios/baseline_20.yaml --scheduler priority --max-concurrency 6
python3 experiments/run_real_device.py 33 config/scenarios/baseline_50.yaml --scheduler priority --max-concurrency 6
python3 experiments/run_real_device.py 33 config/scenarios/baseline_100.yaml --scheduler priority --max-concurrency 6

恶意场景（隐私窃取 / 钓鱼登录 / 勒索加密）：
python3 experiments/run_real_device.py 33 config/scenarios/malicious_privacy.yaml --scheduler priority --max-concurrency 6
python3 experiments/run_real_device.py 33 config/scenarios/malicious_phishing.yaml --scheduler priority --max-concurrency 6
python3 experiments/run_real_device.py 33 config/scenarios/malicious_ransomware.yaml --scheduler priority --max-concurrency 6

### 消融实验（120原子场景）

串行基线（W=1）：
python3 experiments/run_real_device.py 33 config/scenarios/high_parallel_120.yaml --scheduler basic --max-concurrency 1

基础 Kahn（W=6）：
python3 experiments/run_real_device.py 33 config/scenarios/high_parallel_120.yaml --scheduler basic --max-concurrency 6

优先级调度（W=6）：
python3 experiments/run_real_device.py 33 config/scenarios/high_parallel_120.yaml --scheduler priority --max-concurrency 6

### W 参数敏感性实验

for W in 1 2 4 6 8 10 12 14 16; do
  for run in 1 2 3; do
    python3 experiments/run_real_device.py 33 config/scenarios/high_parallel_120.yaml --scheduler priority --max-concurrency $W
  done
done

### 下游验证

python3 experiments/downstream_w6_final3.py

### 真机运行（Pixel 7）

确保真机已连接并开启 USB 调试：
python3 experiments/run_real_device.py 35 config/scenarios/malicious_ransomware.yaml --scheduler priority --max-concurrency 6

### 查看结果

ls output/groundtruth/

## 多版本适配

框架支持 API 28/29/31/33/35 的分区存储策略：

API Level 28     版本分支模式 global_file     说明 全局文件模式
API Level 29     版本分支模式 legacy_mode      说明 兼容过渡模式
API Level 31 及以上  版本分支模式 saf_only     说明 纯 SAF 强制模式

## 仓库结构

config/scenarios/        场景配置文件（YAML）
core/executor/           原子操作与 ADB 管理
core/scheduler/          DAG 调度器实现
core/collector/          文件快照与痕迹采集
experiments/             实验入口脚本
experiments/supplement/  补充分析脚本
docs/                    故障排查与真机配置
output/groundtruth/      实验输出数据

## 开源许可证

Apache License 2.0
