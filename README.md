# Android 取证数据集生成框架

对应论文《多版本Android分区存储下原子化取证数据集生成方法》的实验代码与数据。

本仓库提供：原子操作库、DAG 与关键路径优先级调度器、多版本（API 28–34）分区存储适配策略、并发执行入口、抖动与故障注入测量脚本，以及论文全部表格对应的原始数据与一键校验脚本。

## 目录结构

```
core/            原子操作库（atomic_ops）、DAG 构建（dag_builder）、调度器（priority_scheduler / basic_kahn_scheduler）、
                 设备管理（adb_manager）、版本路径（version_paths）、文件快照（file_snapshot）
utils/           预留目录（设备操作与日志工具已并入 core/）
config/scenarios/  场景定义（baseline_20s/30/50/80/100s 同族五档、baseline_20/100 原生对照、high_parallel_120、三类恶意场景）
experiments/
  paper/         实验脚本（并发引擎、版本策略、抖动与故障注入、下游复算、校验）
  run_real_device.py       旧串行入口（仅历史对照，不产生并发）
  downstream_w6_final3.py  早期下游验证脚本（sklearn 依赖，机器受限时请改用 paper/recalc_downstream_grouped.py）
docs/            REPRODUCE.md、PAPER_DATA_MAP.md、DATA_CARD.md、pixel7_setup.md、troubleshooting.md
output/          实验输出（含论文引用的全部批次数据）
data/groundtruth/ 早期真实执行轨迹样本
scripts/         分析脚本（论文口径只用 calc_timing_v2.py）
```

## 环境要求

- Ubuntu 22.04 LTS、Python 3.10+
- Android SDK（adb 1.0.41、emulator、avdmanager）、OpenJDK 17
- `pip install -r requirements.txt`，另需 `python -m pip install networkx pyyaml`

## 快速开始（并发引擎）

```bash
# 1. 建七套硬件参数一致的 AVD（一次性）
bash experiments/paper/make_avds.sh

# 2. 启动单版本模拟器并等待开机完成
emulator -avd rev_api33 -no-snapshot -no-audio -no-boot-anim &
adb wait-for-device && adb shell getprop sys.boot_completed   # 需输出 1

# 3. 跑 50 步基准场景（W=6，论文主配置）
python experiments/paper/run_parallel.py config/scenarios/baseline_50.yaml \
  --api 33 --scheduler priority --max-concurrency 6 --atomic-mode dag

# 4. 四类故障注入（API 35、W=1、baseline_50，各 20 次；表8 口径）
#    脚本会按 --device 显式绑定目标设备；多设备环境下 run_parallel.py 也要求 --serial
python experiments/paper/fault_inject.py --fault adb_disconnect --repeat 20 --device emulator-5554 --api 35 --w 1 --scenario baseline_50 --out output/paper/table8_fault_adb_saf_pool/adb_disconnect
python experiments/paper/fault_inject.py --fault saf_deny --repeat 20 --device emulator-5554 --api 35 --w 1 --scenario baseline_50 --pkg com.android.chrome --out output/paper/table8_fault_adb_saf_pool/saf_deny
python experiments/paper/fault_inject.py --fault pool_exhaust --repeat 20 --pool 8 --device emulator-5554 --api 35 --w 1 --scenario baseline_50 --out output/paper/table8_fault_adb_saf_pool/pool_exhaust
python experiments/paper/fault_inject.py --fault dag_cycle --repeat 20 --device emulator-5554 --api 35 --w 1 --scenario baseline_50 --out output/paper/table8_fault_dag_cycle/runs
```

> 故障注入的边方向语义：`A.depends_on: [B]` 表示 B 为 A 的前置（边 B→A）。构造真环须把**尾节点**追加到**首节点**的 `depends_on`（生成回边 app_stop_4→click_1），否则只是重复正向依赖，注入无效。`run_parallel.py` 在场景加载阶段即执行三色标记环检测，命中则拒绝加载并落盘 `refused=true`、`cycle_path`，不执行任何原子。

完整流程（七版本矩阵、抖动、消融、下游复算、打包）见 [`docs/REPRODUCE.md`](docs/REPRODUCE.md)。

## 为什么取 W=6（并发上限）

W 参数敏感性实验（4.3.1 与图3）表明：

1. W=1→2 已有明显收益（6.86 s→6.39 s），W≥2 后进入平台（6.39–6.61 s）；
2. 继续提高并发上限未带来可观测收益，120 原子场景的收益主要来自调度策略（3.18×），而非更大并行宽度；
3. 故障风险随 W 上升：W=8／W=12 批次出现 system_server 无响应、input 服务丢失、adb 端点断开频率明显更高。

因此 W=6 是**容量预留**而非实验最优点：为更长原子链与更宽的并行就绪窗口留余量，同时避免逼近故障阈值。该结论与“W 越大越快”无关，请勿如此引用。

## 统计口径

- 每组重复 5 次，前两轮为冷启动预热；
- 表4 取后三轮中位数；图3、表5、表6 取 5 轮均值±样本标准差；表5 ④组为 20 轮合并；
- 表3 合计为“ADB 传输开销＋系统服务响应＋读取窗长”三项之和，内核噪声单列不参与占比；
- 全部耗时走 `run_parallel.py`；`W=1` 指并发上限 1，与旧串行入口 `run_real_device.py` 的输出不可混算。

## 数据与校验

论文每个表格对应的数据路径、生成脚本与期望值见 [`docs/PAPER_DATA_MAP.md`](docs/PAPER_DATA_MAP.md)；批次清单、字段与已知缺口见 [`docs/DATA_CARD.md`](docs/DATA_CARD.md)。

```bash
python experiments/paper/verify_results.py --dir output/paper/<批次目录>   # 批次完整性
python experiments/paper/verify_paper_claims.py                              # 论文数字一致性
```

第二条命令输出逐项 PASS/FAIL，退出码 0 表示正文数字与仓库数据完全一致。

## 引用

若使用本仓库代码或数据，请引用本论文。仓库版本与论文表格的对应关系固定于 `docs/PAPER_DATA_MAP.md`，正文数据以该版本为准。
