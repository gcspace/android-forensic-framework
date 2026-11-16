# 实验复现分步清单

面向第三方复现与代码复核。每一步都给出命令与**预期结果**，任何一步不符即停止，不要带着不确定的数据往下走。

统计口径：每组 5 轮，前两轮冷启动预热；表4 取后三轮中位数，图3、表5、表6 取均值±标准差；全部耗时走 `run_parallel.py`，`W=1` 指并发上限 1。

## 前置条件

- Ubuntu 22.04 LTS、Python 3.10+、Android SDK（adb / emulator / avdmanager）、OpenJDK 17
- `python -m pip install networkx pyyaml`（目录 DAG 与场景解析依赖）

## 第1步：克隆仓库

```bash
git clone <本仓库地址> && cd android-forensic-framework-main
```

**预期结果**：目录内可见 `core/ utils/ config/ experiments/ output/ docs/`。

## 第2步：安装依赖

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install networkx pyyaml
```

**预期结果**：无报错；`python -c "import networkx, yaml"` 无输出。

## 第3步：建七套模拟器（一次性，约 1 小时含系统镜像下载）

```bash
bash experiments/paper/make_avds.sh
```

**预期结果**：`avdmanager list avd` 中可见 `rev_api28` … `rev_api34`，七套硬件参数一致、快照禁用。

## 第4步：单版本冒烟（API 33）

```bash
emulator -avd rev_api33 -no-snapshot -no-audio -no-boot-anim &
adb wait-for-device && adb shell getprop sys.boot_completed
python experiments/paper/run_parallel.py config/scenarios/baseline_50.yaml \
  --api 33 --scheduler priority --max-concurrency 6 --atomic-mode dag
```

**预期结果**：`getprop` 输出 `1`；运行记录 JSON 中 `total_nodes=50`、`success_rate=1.0`、`total_time` 落在 6.3–6.8 s 区间（W=6 五轮均值 6.48 s，对应图3）。注意此步是 50 原子基准场景，不要与表5 的 120 原子场景（W=6 约 13.65 s）混淆。

## 第5步：七版本矩阵与抖动（表3、表4、图3）

```bash
bash experiments/paper/run_session.sh            # 开机→探针→抖动→矩阵→关机→打包
python experiments/paper/verify_matrix.py --dir output/paper/runs
python experiments/paper/analyze_runs.py --dir output/paper/runs
```

**预期结果**：`verify_matrix.py` 退出码 0（无缺组合、无版本错标）；`analyze_runs.py` 输出各版本 W=1 后三轮中位数，应与表4 的 11.27/10.79/24.11/7.12/8.67/6.93/7.74 一致（容差 0.02 s）。

W 参数扫描（图3）：

```bash
for W in 1 2 3 4 6 8 12; do
  for r in 1 2 3 4 5; do
    python experiments/paper/run_parallel.py config/scenarios/baseline_50.yaml \
      --api 33 --scheduler priority --max-concurrency $W --tag "wm${W}_r${r}"
  done
done
```

**预期结果**：W=1 后三轮均值 6.86 s，W≥2 进入 6.39–6.61 s 平台。

## 第6步：消融与恶意场景（表5、表6）

```bash
# ① W=1；② FIFO 就绪顺序；③ 完整方法
python experiments/paper/run_parallel.py config/scenarios/high_parallel_120.yaml --api 33 --scheduler priority --max-concurrency 1
python experiments/paper/run_parallel.py config/scenarios/high_parallel_120.yaml --api 33 --scheduler fifo     --max-concurrency 6
python experiments/paper/run_parallel.py config/scenarios/high_parallel_120.yaml --api 33 --scheduler priority --max-concurrency 6
# ④ 单原子模式（跨 4 批 = 3 批 API33 + 1 批 API34，每批 5 轮，合并 20 轮后取均值±标准差）
python experiments/paper/run_parallel.py config/scenarios/high_parallel_120.yaml --api 33 --scheduler priority --max-concurrency 6 --atomic-mode single
python experiments/paper/run_parallel.py config/scenarios/high_parallel_120.yaml --api 34 --scheduler priority --max-concurrency 6 --atomic-mode single

# 三类恶意场景（W=1，各 5 轮）
for s in malicious_privacy malicious_phishing malicious_ransomware; do
  python experiments/paper/run_parallel.py config/scenarios/${s}.yaml --api 33 --scheduler priority --max-concurrency 1
done
```

**预期结果**：表5 四组 43.47／15.34／13.65／42.35（比值 2.83×、3.18×、1.03×）；表6 原子数 36／46／35，耗时 2.39±0.31／2.85±0.11／2.32±0.02。

## 第7步：故障注入（4.3.9、表8 口径）

```bash
for k in adb_disconnect saf_deny pool_exhaust dag_cycle; do
  python experiments/paper/fault_inject.py --fault $k --repeat 20 --out output/paper/fault_inject_new
done
bash experiments/paper/package_results.sh    # 生成 manifest.json / files.txt / SHA256SUMS
```

**预期结果**：每类 `inject_summary.json` 的 `completion_rate` 可读；`adb_disconnect` 每组耗时由约 7 s 升至约 70 s。注意：`saf_deny`、`pool_exhaust`、`dag_cycle` 在 W=1 基线下不会形成阻断（SAF 仅作用于应用内媒体访问、单会话不需要排队、回边为等价冗余边），因此只验证“注入触发与恢复”，不代表完成率下降——表8 的完成率是上一轮混合故障合并统计，两者口径不同。

## 第8步：下游验证（4.3.7）

```bash
python experiments/paper/recalc_downstream_grouped.py --dir <样本目录>
python experiments/paper/recalc_downstream_grouped.py --dir <样本目录> --four-class
```

**预期结果**：勒索 vs 正常 随机 8:2 93.55%、按批次分组 87.06%、去时间戳 89.41%；三类合并 78.90%／75.45%／77.25%；四分类分组 47.31%。分类器为 numpy 自实现 CART 随机森林（200 树、depth=8、min_split=5、max_features=sqrt、gini），不依赖 sklearn。

**注意**：正文使用的 1185 条样本集未随仓库发布，`data/groundtruth/`（85 条）与 `output/groundtruth/`（58 条）都不足以复算该组数字；此处复现的是方法，数字需同口径样本集才能对齐。

## 第9步：与论文数字对齐

```bash
python experiments/paper/verify_results.py --dir output/paper/<你的批次目录>
python experiments/paper/verify_paper_claims.py
```

**预期结果**：第一条按批次内 `files.txt` 与 `SHA256SUMS` 逐文件哈希一致（`--sums-only`，不依赖原始压缩包）；第二条全部 PASS，退出码 0，末尾提示行说明 4.3.6 与 4.3.8 的正文口径。出现 FAIL 先查数据再查文，不要调宽容差。

## 常见问题

模拟器冷启动慢、adb 端点掉线、多版本权限差异等，见 [`troubleshooting.md`](troubleshooting.md)；真机（Pixel 7 / API 35）采集见 [`pixel7_setup.md`](pixel7_setup.md)。
