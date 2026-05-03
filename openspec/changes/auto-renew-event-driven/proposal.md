## 为什么

当前自动续办由独立的 cron 任务驱动，固定每天 00:00 触发并在 `time_window_start` ~ `time_window_end`（默认 00:00–06:00）窗口内随机延迟执行。这带来两类问题：

1. **触发时机与状态发现脱钩**：续办判断仅在凌晨窗口运行一次，错过窗口（例如服务在 06:01 后才上线、或 cron 因 misfire 跳过）就要等 24 小时；而 remind 任务在白天明明已经查到"明天没有进京证"，却无法直接触发续办。
2. **重复查询**：remind 任务和续办任务都独立调用一次 `stateList` 接口拿同一份数据，浪费请求且彼此不知情。

将续办从"定时驱动"重构为"事件驱动"——挂在已有的 remind 查询流程上，按当前/次日有效性分场景触发。

## 变更内容

- **改造续办触发机制**：删除独立的自动续办 cron 任务，改为在 `JJZPushService.process_single_plate` 拿到 `jjz_status` 后调用决策器分类，命中即 `asyncio.create_task` 异步派发续办。
- **新增续办决策器** `RenewDecision` 枚举与 `decide()` 函数，按"今日/明日有效性 + `sfyecbzxx` + `elzsfkb`"返回 `SKIP`/`RENEW_TODAY`/`RENEW_TOMORROW`/`PENDING`/`NOT_AVAILABLE`。
- **新增续办派发器** `schedule_renew()`：随机延迟（拟人化反爬，默认 30–180s）+ 全局 `asyncio.Semaphore(1)` 串行（多车牌错峰）+ 复用现有 Redis 当日防重 key。
- **抑制冲突提醒**：决策命中 `RENEW_TODAY` / `RENEW_TOMORROW` 时跳过原本的 `push_jjz_reminder`，改由续办协程结束后通过 `push_renew_result` 单独通知。
- **简化失败重试**：`checkHandle` 返回空 `jjrqs` 时本次失败但**不写**当日防重 key，下一个 remind 时刻自然重试。
- **BREAKING** 删除 `global.auto_renew.time_window_start` 和 `global.auto_renew.time_window_end` 配置项；新增 `global.auto_renew.min_delay_seconds`（默认 30）和 `global.auto_renew.max_delay_seconds`（默认 180）。
- **删除遗留代码**：`run_auto_renew_check()`、`should_renew()`、`calculate_random_delay()`、`main.py` 中的自动续办 cron 注册分支、`_validate_auto_renew_time_window` 校验。

## 功能 (Capabilities)

### 新增功能

无。

### 修改功能

- `auto-renew`: 触发判断从"端到端 cron + 凌晨随机窗口"改为"事件驱动 + 分场景决策 + 拟人化延迟 + 全局错峰"；新增"提醒抑制"语义；失败重试改为下一个 remind 时刻重试。
- `renew-config`: 删除"全局续办时间窗口配置"需求；新增"全局续办延迟配置"需求（`min_delay_seconds` / `max_delay_seconds`）。

## 影响

**代码**

- 新增：`jjz_alert/service/jjz/renew_decider.py`（`RenewDecision` 枚举 + `decide()`）、`jjz_alert/service/jjz/renew_trigger.py`（`schedule_renew()` + 全局信号量）。
- 修改：`jjz_alert/service/jjz/auto_renew_service.py`（删 `run_auto_renew_check` / `should_renew` / `calculate_random_delay`，保留 `execute_renew` 与 `push_renew_result`）。
- 修改：`jjz_alert/service/notification/jjz_push_service.py`（`process_single_plate` 末尾接入决策与派发；`response_data` 与 `accounts` 需要从 `JJZService` 传出）。
- 修改：`main.py`（删除自动续办 cron 注册；`has_auto_renew` 启动判断简化）。
- 修改：`jjz_alert/config/config_models.py`、`jjz_alert/config/config.py`、`jjz_alert/config/validation.py`（配置字段替换 + 校验调整）。

**配置**

- BREAKING: `config.yaml` 中 `global.auto_renew.time_window_start` / `time_window_end` 无效；用户需替换为 `min_delay_seconds` / `max_delay_seconds`（启动时若检测到旧字段，给出 WARN 日志并使用默认值）。
- 更新 `config.yaml.example`。

**测试**

- 新增 `tests/test_renew_decider.py`（决策矩阵覆盖）。
- 更新 `tests/test_auto_renew.py`（删除旧触发链路测试，新增 `schedule_renew` 集成测试，包括信号量串行行为）。
- 更新 `tests/test_config.py`（配置字段替换覆盖）。

**运行时**

- 续办派发为 `asyncio.create_task` fire-and-forget；进程在 sleep 期间收到 SIGTERM 时未完成的续办会丢失，但下一个 remind 时刻会重新决策并重试。
- 续办协程的随机延迟 + 全局信号量替代了原本的"凌晨窗口"语义。
