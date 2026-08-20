# Android 取证数据集生成框架

面向多版本 Android 分区存储的原子化取证数据集生成框架

## 环境要求

- Ubuntu 22.04 LTS
- Python 3.10.12
- ADB 1.0.41
- OpenJDK 17

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动模拟器（API 33）

```bash
emulator -avd avd_api_33 -no-snapshot &
```

### 运行实验

```bash
# 50 步基准场景
python3 experiments/run_real_device.py 33 config/scenarios/baseline_50.yaml

# 勒索加密场景
python3 experiments/run_real_device.py 33 config/scenarios/malicious_ransomware.yaml

# 其他基准规模
python3 experiments/run_real_device.py 33 config/scenarios/baseline_20.yaml
python3 experiments/run_real_device.py 33 config/scenarios/baseline_100.yaml

# 其他恶意场景
python3 experiments/run_real_device.py 33 config/scenarios/malicious_privacy.yaml
python3 experiments/run_real_device.py 33 config/scenarios/malicious_phishing.yaml
```

### 补充分析脚本

```bash
# 下游任务验证（勒索加密 vs 50步基准）
python3 experiments/supplement/train_detector_clean.py

# 原子类型耗时分析（模拟器 vs 真机）
python3 experiments/supplement/analyze_atomic_types.py

# 时序抖动分量测量
python3 experiments/supplement/measure_jitter_components.py
```

### 查看结果

```bash
ls output/groundtruth/
```

## 多版本适配

框架支持 API 28/29/31/33 四个版本的分区存储策略：

| API Level | 版本分支模式 | 说明 |
| :--- | :--- | :--- |
| 28 | `global_file` | 全局文件模式 |
| 29 | `legacy_mode` | 兼容过渡模式 |
| 31/33 | `saf_only` | 纯 SAF 强制模式 |

## 论文附录对应文件

| 内容 | 仓库路径 |
| :--- | :--- |
| 场景配置 | `config/scenarios/` |
| 核心执行引擎 | `core/` |
| 实验入口脚本 | `experiments/run_real_device.py` |
| 补充分析脚本 | `experiments/supplement/` |
| groundtruth 数据 | `output/groundtruth/` |
| 故障排查指南 | `docs/troubleshooting.md` |

## 开源许可证

Apache License 2.0
