## 新增需求

### 需求:全局续办延迟配置
系统必须支持在 `global.auto_renew` 中配置续办派发的随机延迟范围。`min_delay_seconds` 与 `max_delay_seconds` 均为整数（单位：秒），未配置时必须使用默认值 30 与 180。配置必须满足 `min_delay_seconds >= 0` 且 `min_delay_seconds <= max_delay_seconds`。

#### 场景:自定义延迟范围
- **当** 用户配置 `global.auto_renew.min_delay_seconds: 60` 与 `max_delay_seconds: 300`
- **那么** 系统必须在每条续办协程派发后，于 60 至 300 秒之间随机选择一个延迟值进行 `asyncio.sleep`

#### 场景:使用默认延迟范围
- **当** `global.auto_renew` 未配置 `min_delay_seconds` 与 `max_delay_seconds`
- **那么** 系统必须使用默认值 `min_delay_seconds=30`、`max_delay_seconds=180`

#### 场景:无效延迟范围
- **当** `min_delay_seconds < 0` 或 `min_delay_seconds > max_delay_seconds`
- **那么** 系统必须在配置校验阶段报错，提示"续办延迟最小值必须 >= 0 且不大于最大值"

#### 场景:检测到已废弃字段
- **当** 用户配置文件中仍存在 `time_window_start` 或 `time_window_end` 字段
- **那么** 系统必须在配置加载阶段输出 WARN 级日志，提示这些字段已废弃将被忽略，不得阻塞启动

## 移除需求

### 需求:全局续办时间窗口配置
**Reason**: 触发模型从"凌晨 cron 窗口"改为"事件驱动 + 拟人化延迟"，时间窗口语义不再适用。

**Migration**: 用户应将 `global.auto_renew.time_window_start` 与 `time_window_end` 从配置文件中移除。如需控制反爬延迟范围，改用新增的 `min_delay_seconds`（默认 30 秒）与 `max_delay_seconds`（默认 180 秒）。系统在加载到旧字段时会输出 WARN 日志但不阻塞启动。
