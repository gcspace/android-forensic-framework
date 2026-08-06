# Android 取证数据集生成框架

面向多版本 Android 分区存储的原子化取证数据集生成框架

## 环境要求

- Ubuntu 22.04 LTS
- Python 3.10.12
- ADB 1.0.41
- OpenJDK 17

## 快速开始

### 安装依赖

    pip install -r requirements.txt

### 启动模拟器

    emulator -avd avd_api_33 -no-snapshot &

### 运行实验

    python3 experiments/run_baseline.py
    python3 experiments/run_malicious.py
    python3 experiments/run_real_device.py 33 config/scenarios/baseline_50.yaml

### 查看结果

    ls output/groundtruth/

## 多版本适配

- API 28: global_file
- API 29: legacy_mode
- API 31/33: saf_only

## 开源许可证

Apache License 2.0
