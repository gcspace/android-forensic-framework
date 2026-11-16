# 论文数据映射表（PAPER_DATA_MAP）

本表把《多版本 Android 分区存储下原子化取证数据集生成方法》正文中的每个表、图和关键数字，映射到仓库内的脚本、数据文件和复算命令。**表里的“复算值”由 `experiments/paper/verify_paper_claims.py` 自动核对，对外发布前必须跑通。**

统一口径：
- 运行时统一入口 `experiments/paper/run_parallel.py`（并发引擎）。旧的 `experiments/run_real_device.py` 为串行入口，不产生并发，其输出不得与本文数据混用。
- `W=1` 指并发上限为 1，不是旧串行入口。
- 每组重复 5 次，前两轮为冷启动预热；**表4 取后三轮中位数**，**图3、表6、表7 取 5 轮均值±样本标准差**（表6 ④组为 20 轮合并）；**图4 取 5 轮中位数，误差棒为四分位距**（同批热态采集，不用均值±标准差）。

| 论文位置 | 数字 | 脚本 | 数据（仓库内路径） | 复算命令 | 说明 |
|---|---|---|---|---|---|
| 表3 抖动分解 | 10.26±1.90、14.82±0.84、0.66、29.60±3.15、合计 54.68 | `experiments/paper/measure_jitter.py`（复测用）；表3 定值出自 2026-08-22 的 W=6 采集 | `output/jitter_w6/measurement_result.txt`（汇总值，含三项均值±标准差与 kernel_jitter）、`clock_read_100.txt`（读取窗原始 100 次） | `python experiments/paper/verify_paper_claims.py`（表3 段） | 合计＝前二项＋读取窗长；内核调度噪声（kernel_jitter）单列“—”，不参与合计与占比。**两项缺口**：① 1000 次原始采样日志当时未写盘，未归档，只能核到汇总值；② 另有 2026-11-13 的一次重测，含 host overhead 扣除、api33 出现负值，方法本身不成立，已移出发布集，不用于核对表3 |
| 表4 版本×耗时 | 11.27/10.79/24.11/7.12/8.67/6.93/7.74（W=1，n=3 中位） | `run_parallel.py`、`version_policy.py`、`run_matrix.py` | `output/paper/table4_version_matrix/session_v2/runs/api{28..34}_on_r{3,4,5}.json/<同名运行记录>.json`；适配关闭组 `api*_off_r1.json` | 同上（表4 段） | 逐轮原始耗时随本仓库公开，正文表4 注所指即此 |
| 图3 / 4.3.1 W 敏感性 | 6.86、6.39、6.61、6.51、6.48、6.53、6.48 | `run_parallel.py --max-concurrency W` | `output/paper/table5_6_and_fig3_timing/timing_v2/api33_baseline_50_priority_w{1,2,3,4,6,8,12}_on_wm*_r1..5.json` | 同上（图3 段） | W=1 含冷启动，取后三轮均值；W≥2 取五轮均值 |
| 表6 消融 | ①43.47 ②15.34 ③13.65 ④42.35 | ①②③ `run_parallel.py`（`--scheduler priority/fifo`）；④ `run_parallel.py --atomic-mode single` | ①②③ `output/paper/table5_6_and_fig3_timing/timing_v2/api33_high_parallel_120_*`；④ `output/paper/table5_ablation_group4/hp120_single_1436_api33`、`_1447_api33`、`_1454_api33`、`_1502_api34`（共 20 轮） | 同上（表6 段） | ②即 FIFO 就绪顺序对照，`--scheduler basic` 为兼容别名，落盘统一记 fifo |
| 表7 恶意场景 | 隐私 36/2.39±0.31、钓鱼 46/2.85±0.11、勒索 35/2.32±0.02 | `run_parallel.py`（W=1，同会话 5 轮） | `output/paper/table5_6_and_fig3_timing/timing_v2/api33_malicious_{privacy,phishing,ransomware}_priority_w1_on_*_r1..5.json` | 同上（表7 段） | 原子数为 `total_nodes`，耗时为 5 轮均值 |
| 表8 虚实对比 | 模拟器(API35) 2.06±0.26/100%、Pixel 7 真机(API35) 1.53±0.05/100% | `run_parallel.py`（同一勒索场景，两侧各 11 轮、剔首轮取 10 轮，`--serial` 显式绑定设备） | `output/paper/table7_virtual_real/{sim,real}/`（真机侧 `serial` 已脱敏） | 不计入自动校验 | 逐类原子比例与复现命令见同目录 `README.md` |
| 表9 场景完整执行率 | ADB断开 100%（20/20）9.89 s；SAF拒绝 100% 6.83 s；池占满 100% 6.81 s；环依赖 0%（20/20拒绝加载）0.00 s | `experiments/paper/fault_inject.py`、`run_parallel.py`（加载期环检测）、`package_results.sh` | `output/paper/table8_fault_adb_saf_pool/{adb_disconnect,saf_deny,pool_exhaust}/`＋`output/paper/table8_fault_dag_cycle/` | `python experiments/paper/verify_paper_claims.py`（表9 段，6 项断言） | API35、W=1、baseline_50、各 20 次；环依赖为预期拒绝加载，`completion_rate=0` 不表示机制失效 |
| 4.3.7 下游验证 | 93.55%/87.06%/89.41%；78.90%/75.45%/77.25%；四分类 47.31% | `experiments/paper/recalc_downstream_grouped.py` | **训练样本集不随仓库公开**（1185 条含 600 正常、175 勒索、585 恶意；已定口径见 `docs/DATA_CARD.md` 缺口第 4 条）；仓库内 `output/groundtruth/`（58 条）与 `data/groundtruth/`（85 条）为真实执行轨迹，不含原子级字段 | `python experiments/paper/recalc_downstream_grouped.py --dir <样本目录> [--four-class]` | 分类器为 numpy 自实现 CART 随机森林（200 树，depth=8，min_split=5，max_features=sqrt，gini），不依赖 sklearn；分组键定义见 `output/paper/downstream_split/split_summary.json` |
| 4.3.9 故障注入 | 四类各 20 次；ADB 断开单轮中位 9.89 s（最长 12.36 s），基线约 6.8 s | `experiments/paper/fault_inject.py` | 同表9 路径 | 同表9 | 边方向语义为 `A.depends_on:[B]` ⇒ 边 B→A，构造真环须把尾节点追加到首节点 `depends_on`；旧批 `dag_cycle`（指纹 `60d7d6dd45de4eb4`）未成环，已作废 |
| 表5 策略分支与痕迹检出（1-2 证据） | `policy_target` 与四档分支 | `version_policy.py`、`storage_probe.py` | `output/paper/policy_target_snapshots/api{28..34}/`（每版 2 个 JSON）；路径常量与目录快照见 `output/paper/appendix_policy_evidence/api{28..34}/`（每版 11 个文件，`collect_policy_evidence.sh` 生成） | 不计入自动校验 | 应用内 MediaStore/SAF 行为需另配原型应用，见 `experiments/paper/README.md` 第五节；`/data/media/0` 在 shell 下报 Permission denied 属预期，以 `/storage/emulated/0` 与 `/mnt/user/0/primary` 为准 |
| 4.3.8 峰值内存 | **0.82~1.45 GB**（API28 818.7–833.1 MB 最低，API34 1447.3 MB 最高；各版 3 次采样取峰；GB 按 1000 MB 计） | `run_parallel.py`（记忆采样模式） | `output/paper/table4_version_matrix/mem_v2/api{28..34}_baseline_50_priority_w1_on_mem_{1,2,3}.json` 的 `mem_peak_mb`（21 个采样） | `python experiments/paper/verify_paper_claims.py`（4.3.8 段） | 正文已按实测改为“0.82~1.45 GB（最低 API28、最高 API34）”，结论“未超 2 GB”成立；早期稿写的 1.22~1.45 只覆盖 API32–34 |
| 表2 原子清单 | 4 类原子、共 20 种操作 | `core/executor/atomic_ops.py` | 无独立数据，定义即代码 | 不计入自动校验 | 数量与场景 yaml 的节点类型一致 |
| 图1 / 图2 | 调度流程与四层架构示意 | — | 示意图，无数据依赖 | 不计入自动校验 | 两图均按实现绘制，不承载数值 |
| 图4 规模扩展性 | 20/30/50/80/100 原子五档：2.094/4.048/6.146/10.866/11.948 s（中位数）；拟合 0.126 s/原子、R²≈0.98 | `run_parallel.py`（`--max-concurrency 6 --scheduler priority --adapter on --serial emulator-5554`） | `output/paper/fig4_scale_family/scale_stats.json`（五档各 5 轮原始值、中位数、四分位距、峰值重叠与拟合，场景为 `config/scenarios/baseline_{20s,30,50,80,100s}.yaml`） | `python experiments/paper/verify_paper_claims.py`（图4 段，14 项断言） | 五档由同一 50 步基准场景按 UI∶文件∶应用≈60∶24∶16 配置，20、30、80 步按原子数取整、偏差不超过 1 个原子；API33、W=6、同一会话连续采集（不重启以保热轨迹连续），整批前一轮预热。原生 `baseline_20.yaml`／`baseline_100.yaml` 构成比例与本族不同（100 步另含 4 个网络下载原子），不用于图4 |
| 4.3.6 重复运行抖动 | 预热后三轮同原子耗时标准差：中位 8.9 ms；文件类原子 0.4~3.9 ms；UI 与进程启停类最高 68.0 ms | `run_parallel.py`（5 轮） | `output/paper/table5_6_and_fig3_timing/timing_v2/api33_baseline_50_priority_w1_on_*_r1..5.json` | `python experiments/paper/verify_paper_claims.py` 输出对应 INFO 行（不做判定） | 正文已据实改写。“≤2.7 ms”在五轮（含冷启动）口径下不成立——全 5 轮标准差中位 55.4 ms、最大 1949 ms，主因是文件类与 UI_INPUT 首轮冷启动；故改按预热后三轮统计并分操作类型说明，与表3 的 1000 次抖动分解口径不同 |

## 一键校验

```bash
python experiments/paper/verify_paper_claims.py
```

输出逐项 PASS/FAIL；退出码 0 表示正文数字与仓库数据完全一致。任何 FAIL 都应先改数据或改文，不允许调小容差。
