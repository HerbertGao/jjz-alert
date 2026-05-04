## 目的

本能力定义自动续办相关的配置项格式与校验规则，包括车牌级 `auto_renew` 配置（启用开关、必需字段、住宿、申请地坐标）与 `global.auto_renew` 全局配置（续办派发延迟范围）。配置项缺失或非法时必须在加载阶段拒绝启动或输出明确告警。
## 需求
### 需求:车牌级续办配置
系统必须支持在 `plates[]` 配置中为每个车牌独立声明自动续办配置。配置块 `auto_renew` 为可选，未配置或 `enabled: false` 时该车牌禁止触发自动续办。

#### 场景:完整续办配置
- **当** 用户在 `plates[].auto_renew` 中提供了 `enabled: true` 及全部必需字段
- **那么** 系统必须在续办检查时将该车牌纳入自动续办候选列表

#### 场景:未配置续办
- **当** 车牌配置中不存在 `auto_renew` 字段
- **那么** 系统必须跳过该车牌的自动续办判断

#### 场景:续办已禁用
- **当** `auto_renew.enabled` 为 `false`
- **那么** 系统必须跳过该车牌的自动续办判断

### 需求:续办必需配置字段
`auto_renew` 配置块启用时，以下字段必须存在且不得为空：`purpose`（进京目的代码）、`purpose_name`（进京目的名称）、`destination.area`（目的地区）、`destination.area_code`（地区代码）、`destination.address`（详细地址）、`destination.lng`（经度）、`destination.lat`（纬度）。

#### 场景:缺少必需字段
- **当** `auto_renew.enabled` 为 `true` 但缺少任何必需字段
- **那么** 系统必须在配置校验阶段报错，明确指出缺少哪个字段，并拒绝启动

#### 场景:全部字段完整
- **当** 所有必需字段均已提供且不为空
- **那么** 系统必须通过配置校验

### 需求:住宿配置
`auto_renew.accommodation` 为可选配置块。当 `accommodation.enabled` 为 `true` 时，`address`、`lng`、`lat` 必须存在。当未配置或 `enabled` 为 `false` 时，续办请求中 `sfzj` 必须为 `"0"`。

#### 场景:启用住宿且字段完整
- **当** `accommodation.enabled` 为 `true` 且 `address`, `lng`, `lat` 均已提供
- **那么** 系统必须在续办请求中设置 `sfzj="1"` 及对应的住宿地址和坐标

#### 场景:启用住宿但缺少字段
- **当** `accommodation.enabled` 为 `true` 但缺少 `address`, `lng`, `lat` 中的任何一个
- **那么** 系统必须在配置校验阶段报错

#### 场景:未配置住宿
- **当** `accommodation` 未配置或 `enabled` 为 `false`
- **那么** 系统必须在续办请求中设置 `sfzj="0"`，住宿相关字段设为空字符串

### 需求:申请地坐标配置
`auto_renew.apply_location` 为可选配置块，包含 `lng` 和 `lat`。未配置时必须使用默认值 `lng="116.4"`, `lat="39.9"`（北京市中心附近）。

#### 场景:用户指定申请地坐标
- **当** `apply_location.lng` 和 `apply_location.lat` 已配置
- **那么** 系统必须使用用户配置的坐标作为 `sqdzgdjd` 和 `sqdzgdwd`

#### 场景:未配置申请地坐标
- **当** `apply_location` 未配置
- **那么** 系统必须使用默认值 `lng="116.4"`, `lat="39.9"`

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

