# experiments/supplement 说明

本目录保存早期（2026-08）的补充测量与下游训练脚本，**不是论文现行口径**：

- `jitter_components.json`：早期抖动分量测量（ADB 传输 10.43、系统服务 21.14、内核噪声 0.44、读取精度 17.76，合计 49.76 ms）。这组数与论文表3（10.26 / 14.82 / 0.66 / 29.60，合计 54.68 ms）**不一致**，是表3 定稿前的方法迭代版本，仅作过程留痕，勿引用。
- `analyze_atomic_types.py`：原子类型分布统计，用于早期章节写作。
- `train_detector.py`、`train_detector_clean.py`：早期基于 sklearn 的检测器训练脚本，本机受策略拦截无法运行；论文 4.3.7 已改用 `experiments/paper/recalc_downstream_grouped.py`（numpy 自实现随机森林）。
- `legacy/`：占位与废弃文件归档。

表3 的正确数据源是 `output/jitter_w6/measurement_result.txt`，见 `docs/PAPER_DATA_MAP.md`。
