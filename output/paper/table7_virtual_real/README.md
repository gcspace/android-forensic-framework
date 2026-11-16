# table7_virtual_real — 表7 虚实对照原始数据（同版本 API 35）

## 口径
- 场景：`config/scenarios/malicious_ransomware.yaml`（35 原子，勒索加密）
- 参数：`--api 35 --max-concurrency 6 --scheduler priority --adapter on`，同一并行执行入口
- 轮次：每侧 11 轮，**剔除首轮冷启**后取 10 轮报 n=10
- 设备绑定：模拟器 `emulator-5554`（AVD `rev_api35`，2 GB 内存 / 8 GB 数据分区），真机 `Pixel 7`（API 35）
- 必须显式传 `--serial`：`run_parallel.py` 与 `trace_audit.py` 在缺省时会取 `adb devices` 首台设备，
  曾导致模拟器批次误落到真机（该批已废弃，未入库）

## 结果（n=10）
| 环境 | 生成耗时 | 文件完整导出 |
|---|---|---|
| API 35 模拟器 | 2.062±0.256 s（首轮 3.761 s） | 100%（27/27） |
| Pixel 7 真机（API 35） | 1.534±0.054 s（首轮 1.597 s） | 100%（27/27） |

逐原子（模拟器 / 真机，真机为模拟器的百分比）：

| 原子 | 模拟器 | 真机 | 比例 |
|---|---|---|---|
| UI_CLICK | 61.2±40.9 ms | 60.4±9.3 ms | 98.7% |
| UI_SWIPE | 396.7±26.5 ms | 371.7±10.4 ms | 93.7% |
| FILE_CREATE | 112.8±46.6 ms | 81.5±19.6 ms | 72.3% |
| UI_INPUT | 408.3±190.2 ms | 83.3±16.1 ms | 20.4% |

差异集中在 UI_INPUT（模拟器经软件渲染输入栈逐字符分发按键事件）。样本量为单场景，比例不作统计推断。

## 复现
```bash
cd ~/aff
python3 experiments/paper/run_parallel.py config/scenarios/malicious_ransomware.yaml \
  --api 35 --max-concurrency 6 --scheduler priority --adapter on \
  --serial emulator-5554 --out output/paper/table7_virtual_real/sim --tag sim_r$i
python3 experiments/paper/trace_audit.py config/scenarios/malicious_ransomware.yaml \
  --api 35 --adapter on --serial emulator-5554 --out output/paper/table7_virtual_real/sim/trace_on.json
```

## 说明
- 真机侧 `serial` 已替换为 `REDACTED_PIXEL7`，其余字段与原始运行记录一致。
- 首轮耗时显著偏高（模拟器 3.761 s、真机 1.597 s），属冷启预热，正文与表7 均按剔首轮口径。
