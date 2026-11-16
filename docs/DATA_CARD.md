# 数据卡片（DATA_CARD）

本仓库随论文发布的实验数据说明。所有批次由 Linux 采集侧打包（`package_results.sh`），每个批次目录内含 `files.txt` 与 `SHA256SUMS`（部分批次另附 `manifest.json` 采集元信息），用 `verify_results.py --sums-only` 校验。

## 一、已发布批次

| 目录 | 采集时间 | 内容 | 文件数 | 用途 |
|---|---|---|---|---|
| `output/paper/table4_version_matrix/` | 2026-11-14 17:47 | `session_v2/runs`（API28–34 × 适配开/关 × 5 轮，每 run 一目录）、`session_v2/trace`（14 份 trace 审计）、`mem_v2`（21 份内存采样） | 80 | 表4、4.3.8 峰值内存、1-2 证据 |
| `output/paper/table5_6_and_fig3_timing/` | 2026-11-14 16:29 | `timing_v2/`（W=1…12 扫描、hp120 三组、三类恶意场景各 5 轮）、`ablation_v2/`（dag / single 基线） | 78 | 图3、表6①②③、表7 |
| `output/paper/fig4_scale_family/` | 2026-11-16 02:34 | 五档同族场景（20s/30/50/80/100 原子）各 5 轮与一轮预热的 `total_time`、`peak_overlap`、`success_rate`，汇总为 `scale_stats.json`（中位数、四分位距、单原子摊销、最小二乘拟合） | 1 | 图4（4.3.4 规模扩展性） |
| `output/paper/table5_ablation_group4/` | 2026-11-14 14:36–15:02 | 单原子模式 4 批（API33×3＋API34×1，每批 5 轮） | 20 | 表6 ④组（20 轮合并，42.35±2.50） |
| `output/paper/table8_fault_adb_saf_pool/` | 2026-11-15 19:55 | ADB链路断开／SAF授权拒绝／会话池占满三类单注各 20 次：`inject_log.csv`＋`inject_summary.json`＋60 条 run json | 62 | 表9 前三行（该批 `dag_cycle` 因回边方向错误作废，已剔除） |
| `output/paper/table8_fault_dag_cycle/` | 2026-11-15 21:50 | DAG环形依赖单注 20 次，20/20 拒绝加载（`refused`、`cycle_detected`、`cycle_path` 齐全） | 21 | 表9 第四行 |
| `output/paper/appendix_policy_evidence/` | 2026-11-15 22:30（api33 于 23:19 补采） | 各 SDK 版本路径常量与目录快照：`getprop` 全量/过滤、`/proc/filesystems`、存储 mount、五条路径 `ls -ld`、目录快照、policy 文件、`sm list-volumes`、`policy_target`（每版 11 个文件） | 85 | 表5 策略分支与痕迹检出（1-2 证据）；api33 首采时 FUSE 未就绪（`Transport endpoint is not connected`），已按“等 `/storage/emulated/0` 可列举”的补采覆盖，现无该报错 |
| `output/paper/policy_target_snapshots/` | 2026-11-14 15:21–16:12 | 每版本 `policy_target` 与分支判定 | 14 | 1-2 策略证据 |
| `output/paper/downstream_split/` | 2026-11-13 11:38 | 下游验证的分组键定义（`split_summary.json`） | 1 | 4.3.7 按批次分组 |
| `output/jitter_w6/` | 2026-08-22 | W=6 时段四类抖动分量测量（1000/200/100/100 次） | 2 | 表3 主数据 |
| `output/groundtruth/`、`data/groundtruth/` | — | 真机/模拟器逐次执行轨迹 | 58 / 85 | 4.3.7 训练样本 |

## 二、字段与统计口径

- 运行记录（`*/runs/*/*.json`）：`api`、`scenario`、`scheduler`、`max_concurrency`、`policy_branch`、`policy_target`、`adapter`、`total_nodes`、`total_time`（秒）、`success_atoms`、`success_rate`、`mem_peak_mb`、`atoms[]`（每个原子的 `duration_ms`、`timestamp_start`、`timestamp_end`）。
- 抖动量（`jitter_apiXX.json`）：`adb_roundtrip`、`host_overhead`、`service_resp`、`clock_window`、`kernel_jitter` 各含 `n/mean/sd/p50/p95`，`raw` 保留全部原始样本。
- 统计规则：每组 5 轮，前两轮为冷启动预热；表4 取后三轮中位数，其余取均值±样本标准差；表6 ④组为 20 轮合并；表8 为每侧 11 轮、剔除首轮取 10 轮（冷启首轮耗时显著偏高）；**图4 取 5 轮中位数、误差棒为四分位距**（小规模档初始化占比高、离散度大，中位数口径可抑制单轮离群而不掩盖分布）。
- 故障注入：`inject_summary.json` 给出 `completion_rate`（表9 所需口径）与每轮耗时，`inject_log.csv` 逐次记录注入点、观测结果与恢复动作。表9 口径为 API 35、W=1、`baseline_50`、各 20 次；环依赖行的 `completion_rate=0` 属预期拒绝加载，不代表机制失效。

## 三、已知缺口

1. **表8 两侧批次均已发布**：`output/paper/table7_virtual_real/` 收录模拟器（`emulator-5554`，AVD `rev_api35`）与 Pixel 7 真机（API 35）各 11 轮运行记录及痕迹审计结果，统计口径为剔首轮取 10 轮；真机侧 `serial` 字段已替换为 `REDACTED_PIXEL7`，复现路径见 `docs/pixel7_setup.md`。此前同源批次（未显式指定 `--serial`、模拟器批次误落到真机）已废弃，未入库。
2. **表9 为四类故障单注口径，旧注入批次作废**：`fault_inject.py` 早期的 `dag_cycle` 把首节点加进尾节点 `depends_on`，只生成重复的正向依赖、未构成环，该批 `dag_cycle` 记录（代码指纹 `60d7d6dd45de4eb4`）中 `success_rate=1.0`、50/50 原子跑完，属无效样本，**禁止引用**；这批的 adb_disconnect／saf_deny／pool_exhaust 三类不受影响，仍为表9 前三行来源。修正后的环注入（尾节点回连首节点）与带加载期环检测的 `run_parallel.py` 同批采集于 `output/paper/table8_fault_dag_cycle/`，代码指纹 `448663002fb7cd55`，20/20 拒绝加载。统计只采信 `448663002fb7cd55` 批次的环依赖样本，两套指纹不可混用。
3. **中间批次未入库**：`D:\REV\10_results` 共 55 个批次，仓库只保留口径定稿后的批次；重跑与探针的中间轮次（如 2026-11-13 多次 session、fix01–04、timing_v1）不发布，避免同一数字出现多套口径。
4. **4.3.7 训练样本集不随仓库公开（已定口径）**：正文 1185 条样本（600 正常／175 勒索／585 恶意）由运行记录逐原子抽取的 `duration_ms`、`op_type`、`timestamp%1000` 与场景标签构成，含设备侧时序与场景节奏信息，公开仓库不收录原始明细；仓库改为提供分组键定义（`output/paper/downstream_split/split_summary.json`）与复算实现（`recalc_downstream_grouped.py`，`--dir <样本目录>`），复现请求时按需提供样本包。因此 4.3.7 在仓库内可复现方法、不能直接复算数字。
5. **4.3.7 分类器为 numpy 自实现**：本机 sklearn 受应用控制策略拦截无法导入，故用自实现 CART 随机森林（200 树、depth=8、min_split=5、max_features=sqrt、gini），参数与实现均在 `recalc_downstream_grouped.py` 中，可直接复核。
6. **4.3.6 抖动按预热后三轮统计**：全五轮（含冷启动）算，50 个原子耗时标准差中位 55.4 ms、最大 1949 ms；预热后三轮降为中位 8.9 ms（文件类原子 0.4~3.9 ms，UI 与进程启停类最高 68.0 ms）。正文已按后者表述，`verify_paper_claims.py` 对该项只输出 INFO。
7. **4.3.8 峰值内存为 0.82~1.45 GB**：`mem_v2/` 21 个采样为唯一数据源，最低 API28（818.7 MB）、最高 API34（1447.3 MB）；正文已由 1.22~1.45 改为 0.82~1.45，结论“均未超 2 GB”不变。
8. **表3 只有一套有效数据**：`output/jitter_w6/` 为唯一来源；`experiments/supplement/jitter_components.json`（合计 49.76 ms）与 2026-11-13 的重测（含 host overhead 扣除、出现负值）都不属表3 口径，未随仓库发布。
9. **图4 为五档同族同热态口径，早期三点数据作废**：早期图4 为 20/50/100 三点（3.06/6.44/14.85 s），其中 20/100 档出自 `output/groundtruth/real_execution_20260822_*`（无 `serial` 字段、`total_layers=20`），50 档出自 `timing_v2`（`emulator-5554`），三档设备与引擎口径不一，**不可再用**。现行图4 取 `output/paper/fig4_scale_family/scale_stats.json`：五档场景由同一 50 步基准场景按 UI∶文件∶应用≈60∶24∶16 配置（`config/scenarios/baseline_{20s,30,50,80,100s}.yaml`，20/30/80 步按原子数取整、偏差不超过 1 个原子），统一 `emulator-5554`、API 33、W=6、priority、adapter=on，同一会话内连续采集 5 轮、整批前一轮预热，取中位数并按四分位距给误差棒。采集中的两批作废批次：`rev_20261116_0038_scale_30_80`（`--yaml/--weight/--priority` 参数不存在，12 轮秒退、零 run json）、`rev_20261116_0058_scale_all_5point_w6_api33` 的 20/100 档（原 `baseline_20/100.yaml` 构成比例与派生族不同，仅存档对照）。单原子摊销区间亦随之由 0.129~0.153 s 改为 0.105~0.136 s。

## 四、校验方式

```bash
# 1) 批次完整性（按各批次 files.txt 与 SHA256SUMS 逐文件校验）
python experiments/paper/verify_results.py --dir output/paper/<批次目录> --sums-only
# 2) 论文数字一致性
python experiments/paper/verify_paper_claims.py
```

`round2_trace_all` 批次只覆盖表4 所需的 W=1 适配开/关矩阵，`verify_results.py` 报其它组合“缺跑”属正常；该批 `off` 组仅 1 轮（表4 只用到关闭侧漏检统计）。

## 五、许可

数据随代码采用同一许可（见 `LICENSE`），仅限科研复现与方法对比使用；不含任何真实用户隐私数据，恶意样本均为受控模拟场景生成。
