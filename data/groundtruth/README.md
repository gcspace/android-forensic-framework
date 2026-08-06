# groundtruth.json 数据格式说明

| 字段 | 类型 | 说明 |
|------|------|------|
| scenario | string | 场景名称 |
| api_level | int | Android API 版本 |
| device_serial | string | 设备序列号 |
| total_nodes | int | 原子总数 |
| total_time_seconds | float | 总耗时（秒） |
| evidence | array | 原子执行记录 |

### evidence 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| node_id | string | 原子唯一标识 |
| op_type | string | 操作类型 |
| timestamp | float | CLOCK_BOOTTIME 时间戳（秒） |
| duration_ms | float | 执行耗时（毫秒） |
| success | bool | 是否成功 |
| evidence | object | 具体取证痕迹 |
