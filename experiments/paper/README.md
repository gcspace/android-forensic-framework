# 实验包（experiments/paper）

用于《多版本Android分区存储下原子化取证数据集生成方法》全部实验数据的生成与核对。
所有脚本读同一套 YAML 与同一套原子实现，输出统一落在 `output/paper/`。

> 论文数字与本包数据的对应关系见 `docs/PAPER_DATA_MAP.md`；一键复核用 `python experiments/paper/verify_paper_claims.py`（退出码 0 表示正文数字与仓库数据一致）。

## 一、先明确两件事

1. **原入口不产生并发。** `run_real_device.py` 逐层逐原子串行执行，`max_concurrency` 只限制层内节点数，因此表5 的 "+2.3%/+7.4%" 是顺序与冷热效应，不是并发收益。要回答审2-11、审1-15，必须换用本包的 `run_parallel.py`。
2. **版本适配已落地到核心代码。** `core/executor/version_paths.py` 提供四档分支（`legacy_global` / `legacy_optout` / `scoped_enforced` / `granular_media` / `granular_photo`），`atomic_ops._get_media_path` 按 `api_level + adapter` 取真实落盘路径，运行记录里同时写出 `policy_branch` 与 `policy_target`，可逐条核对。仍然受限的是**应用内** MediaStore/SAF 行为：系统层证据齐全，应用内细粒度授权需另加原型应用与 instrumentation，做法见本文件第五节。

> 口径说明：`version_paths.py` 的分支与 `atomic_ops` 的落盘路径取值为当前唯一实现口径，`policy_branch` / `policy_target` 可在运行记录中逐条核对，不另设标签式实现。

## 二、实验清单

| 编号 | 实验 | 对应意见 | 设计 | N | 主要产出 | 通过判据 |
|---|---|---|---|---|---|---|
| E1 | 版本证据探针 | 审1-2、审2-5、审1-12 | 7 个版本 × 9 项系统层检查 | 每版 3 次 | `probe/probe_summary.csv` | 三次结果一致；能指出全局路径是否可写、MediaStore 可否查询、细粒度权限是否存在 |
| E2 | 版本×基线耗时 | 表4 扩容 | 7 版 × `baseline_50` × W=1 | 5+1 预热 | `runs/summary.csv` | 原子数=50、成功率≥95%、SD 可报 |
| E3 | 真并发对照 | 表5、表6、审2-11、审1-15、审2-2 | 120 原子 W=1/6；三类恶意场景 W=1/6 | 5+1 | `runs/table5_like.csv` | 峰值重叠数 >1，且加速比可解释 |
| E4 | 抖动重测 | 表3、审1-3/1-4/1-5 | 7 版 × 四类分量 | 1000/200/100/100 | `jitter/jitter_summary.csv` | 分量可加总；29.60ms 类窗口单列，不进占比 |
| E5 | 版本适配消融 | 审1-10、审2-8 | 7 版 × 适配开/关 | 5+1 | `runs/adapter_ablation.csv` | 逐版本给出损失率，而非一句定性 |
| E6 | 完整性闸门 | 全表 | 全矩阵 | — | 终端报告 | 退出码 0 才允许填表 |

暂不在本包内：贡献3（复合指令同步采集）的消融，需要改 `core/collector` 的采集封装；下游分类重跑的冷启动会话分组，沿用 `experiments/downstream_w6_final3.py`，只改分组键。

## 三、执行顺序

依赖：`python -m pip install networkx pyyaml`（DAG 构建依赖 networkx，仓库未附 requirements）。

```bash
# 1. Linux 侧建镜像（一次性，约 1 小时含下载）
bash experiments/paper/make_avds.sh

# 2. 逐个版本启动，只保留一个设备在线
emulator -avd rev_api28 -no-snapshot -no-audio -no-boot-anim &
adb wait-for-device && adb shell getprop sys.boot_completed   # 需为 1

# 3. 版本证据与抖动（每版都做）
python experiments/paper/storage_probe.py --api 28 --out output/paper/probe
python experiments/paper/storage_probe.py --api 28 --repeat 2 --out output/paper/probe
python experiments/paper/storage_probe.py --api 28 --repeat 3 --out output/paper/probe
python experiments/paper/measure_jitter.py --api 28 --out output/paper/jitter

# 4. 一键跑完七个版本（开机→探针→抖动→矩阵→关机→打包）
bash experiments/paper/run_session.sh

# 只想跑部分版本或先冒烟
bash experiments/paper/run_session.sh --apis "33" --no-package

# 5. 先验完整性，再汇总
python experiments/paper/verify_matrix.py --dir output/paper/runs
python experiments/paper/analyze_runs.py --dir output/paper/runs
```

切换版本时必须关闭上一个模拟器，`run_matrix.py` 会校验 `ro.build.version.sdk` 与组合是否一致，不一致直接跳过，不会把数据记错版本。

## 四、脚本职责

| 文件 | 作用 |
|---|---|
| `version_policy.py` | 四档版本策略表（legacy_global / legacy_optout / scoped_enforced / granular_media / granular_photo），统一正文表述 |
| `make_avds.sh` | 七套硬件参数一致的 AVD，禁用快照，避免版本间被硬件差异污染 |
| `storage_probe.py` | 采集 SDK、`/sdcard` 可写性、MediaStore 可查询性、DocumentsUI、`READ_MEDIA_*` 权限定义、重定向观测 |
| `run_parallel.py` | DAG 就绪队列 + 线程池真并发，复用原 ADB 会话池（8 会话，支持多线程取用） |
| `run_matrix.py` | 批量驱动、预热剔除、断点续跑、版本校验、`index.csv` 索引 |
| `measure_jitter.py` | 表3 四类分量，附主机进程开销用于扣减 |
| `analyze_runs.py` | 均值/标准差/95%CI/峰值重叠/加速比/适配损失率 |
| `verify_matrix.py` | 跑满、原子数、成功率、重叠数四项闸门 |

## 五、两处需要补代码的地方（本包不代做）

1. **应用内存储行为。** `adb shell` 对 `/sdcard` 权限较宽，无法复现应用沙箱。要拿到真正的"重定向证据"，需要在被测应用里放一个 instrumentation，分别用 `MediaStore`、`SAF`、`READ_MEDIA_IMAGES` 三条路径写同一份样本，记录成功/失败与最终 URI，再由 `storage_probe.py` 的同一张表汇总。
2. **版本适配的行为差异。** 若要支撑"版本适配"这一贡献，需把 `_get_api_branch` 从标签变成行为：在 `FileCreate/FileCopy/FileDelete` 里按 `version_policy` 选择落盘方案，关闭适配时回落到旧路径，这样 E5 的 on/off 才有真实差异。

## 六、离线自检结果

用假原子（每原子固定 20ms）验证调度器本身，未接设备：

| 场景 | W | 原子数 | 实际完成 | 墙钟 | 峰值重叠 |
|---|---|---|---|---|---|
| high_parallel_120 | 1 | 120 | 120 | 2.50s | 1 |
| high_parallel_120 | 6 | 120 | 120 | 0.43s | 6 |
| baseline_50 | 1 | 50 | 50 | 1.04s | 1 |
| baseline_50 | 6 | 50 | 50 | 1.00s | 3 |

说明：120 原子场景在真并发下确实能压到 1/6 墙钟，而 baseline_50 是链式结构，加速有限。
旧入口的 31.62→30.88 只是顺序执行下的冷热差异，不可用作并发收益对照。

## 七、双系统交接（Windows 写作 / Linux 实验）

代码只在 Linux 原生分区保留一份可执行副本，共享 NTFS 盘只放结果包与文档，流程单向：

1. Linux 开机后直接 `bash experiments/paper/run_session.sh`：自检、逐版本启动、探针三次、抖动、矩阵、打包一次完成，中途不需要人工切换；
2. 只想补某个版本时用 `--apis "33"`；只想跑数据不打包时加 `--no-package`；
3. 回到 Windows，`python experiments\paper\verify_results.py --dir <会话目录>`，校验不过不填表。

详细路径映射与注意事项见《双系统实验交接方案》。

## 九、路径与目录约定

路径不写死盘符或设备名，统一用**卷标**定位。本机实际：数据盘 `D:`，卷标「资源盘」，NTFS 158.1 GB，Linux 侧为 `/dev/sdb1`；Windows 访问 `D:\REV`，Linux 挂到 `/mnt/revshare` 后访问 `/mnt/revshare/REV`。

所有路径集中在 `rev.env`，改一处即可全局生效。

REV 目录树：

| 目录 | 内容 | 写入方 |
|---|---|---|
| `00_handoff` | 实验包、矩阵说明、两边解析出的路径记录 | Windows 放入 |
| `10_results` | 每轮会话一个目录 `rev_时间_tag` | Linux 写，Windows 读 |
| `20_paper` | 论文与图表备份 | Windows 主写 |
| `30_images` | 镜像与 AVD 备份（可选） | 任意 |
| `90_tmp` | 临时交换，可清空 | 任意 |

初始化一次即可（Windows 侧已执行，`D:\REV` 与 `paths_windows.txt` 已生成）：

```bash
sudo bash experiments/paper/setup_share.sh      # Linux：挂载、建目录、验可写
powershell -ExecutionPolicy Bypass -File experiments\paper\setup_paths.ps1   # Windows：定位盘符、建目录
```

两边各自把解析结果写回 `00_handoff`（`paths.resolved` 与 `paths_windows.txt`），交接时不必口头确认盘符。

## 十、与正文表格的对应

- 表3 → `jitter_summary.csv`（每版一行，29.60ms 类窗口单列）
- 表4 → `summary.csv` 中 `scenario=baseline_50, w=1`
- 表5 → `table5_like.csv`
- 表6 → `summary.csv` 中三类恶意场景，W=1 与 W=6 成对
- 表8 → 沿用原故障注入脚本，补 N 与 Wilson 区间
