## 上下文

**当前状态**

自动续办作为独立 cron 任务运行：APScheduler 每天 00:00 触发 → `calculate_random_delay()` 在 `time_window_start`–`time_window_end`（默认 00:00–06:00）窗口内随机一个时刻 → `run_auto_renew_check()` 重新调用 `stateList` → 对每辆启用续办的车牌调用 `should_renew()` 判断（条件：六环外 + 无待审 + `valid_end <= tomorrow`）→ 调续办 6 步 API 链。

与此同时，提醒推送（remind）作为另一个独立 cron 任务（默认 07:00 / 12:30 / 19:00 / 23:55）也在调用 `stateList`，并在 `process_single_plate` 内已有"次日有效性"判断（`jjz_push_service.py:419-469`），但仅用来发送 `push_jjz_reminder` 文字提醒，不参与续办。

**约束**

- 续办 API 链每步耗时数百 ms 至 1 s，且对北京交管接口需要拟人化以避免风控。
- `JJZService.get_multiple_status_optimized()` 对每辆车返回 `max(records, key=apply_time)` 的"最新一条"——不一定是六环外，但 `vId`/`elzsfkb`/`sfyecbzxx` 等续办所需字段是 vehicle 级，与具体记录类型无关。
- 续办接口以 `jjzzl="02"` 固定提交六环外，与 `jjz_status` 的具体记录类型解耦。
- 服务可能在任意时间被重启（容器重部署、SIGTERM）。

**利益相关者**

- 终端用户：希望"快到期/已过期就立即办"，而不是死等凌晨窗口。
- 开发者：维护成本低，配置项语义清晰。
- 北京交管接口：低频、拟人化、错峰。

## 目标 / 非目标

**目标：**

- 把续办触发与"发现状态"的时刻对齐：任意 remind 时刻发现"明天没证 / 今天没证"都可以立即派发续办。
- 复用 remind 已经查到的 `stateList` 数据，避免重复调用。
- 多车牌触发时通过随机延迟 + 全局信号量错峰，避免并发请求。
- 失败重试的语义降级到"等下一个 remind 时刻自然重试"，不引入额外重试机制。
- 删除冗余配置（`time_window_*`），引入语义清晰的延迟范围配置。

**非目标：**

- 不实现"服务启动即触发"——继续依赖 remind cron 的自然节奏。
- 不为"完全无六环外历史"的车牌做特殊路径——这种情况 `vId` 为空，续办流程会在 `validate_fields` 步骤自然失败并通知，无需额外分支。
- 不引入分布式锁——单进程部署 + Redis 当日防重 + `sfyecbzxx` 二次校验已经足够。
- 不改变续办 API 调用链本身（6 步 API 顺序、字段组装、Token 失效识别等保持不变）。
- 不调整 remind 的 cron 时刻——用户已有的 `remind.times` 配置不变。

## 决策

### 决策 1：决策器返回枚举，而非布尔

**选择**：新建 `RenewDecision(Enum)`，包含 `SKIP` / `RENEW_TODAY` / `RENEW_TOMORROW` / `PENDING` / `NOT_AVAILABLE`。

**理由**：

- 旧 `should_renew()` 返回布尔，无法区分"为什么不办"——`PENDING`（已有待审）与 `NOT_AVAILABLE`（六环外不可办）需要不同处理（前者静默，后者发告警）。
- `RENEW_TODAY` / `RENEW_TOMORROW` 的区分让日志和通知更精准，也让未来的策略调优（例如对 `RENEW_TODAY` 缩短延迟）成为可能。

**替代方案**：

- *保留 `should_renew()` 返回 bool，调用方自己拆条件* — 拆分条件会散落在多处，难以测试。
- *返回 dataclass 携带更多上下文* — 当前只需要枚举级信息，dataclass 是过度设计。

### 决策 2：决策矩阵以 `valid_end` 为唯一时间字段

**选择**：

```
SKIP                : valid_start <= today AND today < tomorrow <= valid_end
RENEW_TOMORROW      : valid_start <= today <= valid_end AND tomorrow > valid_end
RENEW_TODAY         : valid_end < today  OR  status == EXPIRED / INVALID
PENDING             : sfyecbzxx == True
NOT_AVAILABLE       : elzsfkb == False
```

优先级：`PENDING` > `NOT_AVAILABLE` > `RENEW_*` > `SKIP`。

**理由**：

- `jjz_status.valid_end` 是 push_workflow 已经在用的字段（`jjz_push_service.py:455-464`），新决策器与现有"次日提醒"判断完全等价，避免引入第二套真值判断。
- 不需要识别"哪条记录是六环外"——`vId` 等续办字段是 vehicle 级的，已经统一。

**替代方案**：

- *用 `days_remaining` 字段* — 该字段是接口返回的 `sxsyts`，依赖接口侧时区/计算口径，不如本地比 `today` 可靠。
- *按"六环外历史 vs 六环内历史"分别判断* — 用户已确认不区分，简化逻辑。

### 决策 3：派发用 `asyncio.create_task` fire-and-forget

**选择**：在 `process_single_plate` 内决策命中 `RENEW_*` 时执行：

```python
asyncio.create_task(schedule_renew(plate_config, jjz_status, response_data, accounts, decision))
```

不 await，让 push_workflow 主流程立刻返回。

**理由**：

- `schedule_renew` 内部要 `sleep(30~180s)`，await 会把 push_workflow 整体阻塞到分钟级。
- 续办失败/成功都通过独立通知告知用户，不需要主流程感知结果。

**替代方案**：

- *await 直接执行* — 阻塞主流程；多车牌串行后总耗时不可接受。
- *写入 Redis 队列由独立 worker 消费* — 引入额外组件，单进程场景过度。

**风险**：进程在 sleep 期间被 SIGTERM 时任务丢失 → 由"下一个 remind 时刻自然重试"兜底。

### 决策 4：错峰用 `asyncio.Semaphore(1)` 全局串行

**选择**：模块级 `RENEW_GLOBAL_SEMAPHORE = asyncio.Semaphore(1)`，`schedule_renew` 在 sleep 醒来后 `async with` 抢锁，再调 `execute_renew`。

**理由**：

- 多车牌同时命中场景②时，即便随机延迟有重叠（30~180s 内有概率撞），信号量保证任意时刻只有 1 条续办 API 链在跑。
- API 链耗时数秒，4 辆车串行也只多花十几秒，可接受。
- 比"按车牌索引分配偏移"实现更简单、更稳健。

**替代方案**：

- *只靠随机延迟* — 4 辆车随机到接近时刻的概率不低，单纯依赖 30~180s 区间错峰不够强。
- *Redis 分布式锁* — 单进程足够，分布式锁是过度工程。

### 决策 5：抑制冲突的 reminder 通知

**选择**：`process_single_plate` 命中 `RENEW_TODAY` / `RENEW_TOMORROW` 时跳过 `push_jjz_reminder("请注意及时办理...")`，把 `push_result` 设为 `{"success": True, "skipped": "renew_dispatched"}`。续办协程结束时通过 `push_renew_result` 单独发结果通知。

**理由**：

- 旧实现下用户在场景①会同时收到"请注意及时办理"和"续办成功"两条通知，互相矛盾。
- 命中 `NOT_AVAILABLE`（六环外不可办）时**仍发**告警——这是机器无法处理的情况，必须让用户知晓。
- 命中 `PENDING` 时**保留**正常通知（已有待审记录其实是"好消息"）。

**替代方案**：

- *永远抑制提醒，只看续办结果* — 决策为 `NOT_AVAILABLE` 时用户会沉默，不可接受。

### 决策 6：失败重试 = 等下一个 remind 时刻

**选择**：`checkHandle` 返回空 `jjrqs`（接口未放号）时：

- `RenewResult.success = False`、`step = "check_handle"`
- **不写**当日防重 Redis key
- 通过 `push_renew_result` 通知用户
- 下一个 remind 时刻 push_workflow 会重新决策并派发

**理由**：

- 北京交管"明日额度"通常 0 点放号，但偶有延迟。在 23:55 触发时若未放号，等 5 分钟后的下一个 cron 自然就过 0 点了。
- 不需要在续办协程内做指数退避或多次轮询，简化逻辑。

**替代方案**：

- *续办协程内重试 N 次* — 增加复杂度，且阻塞信号量更长时间。
- *写入 Redis 标记"待重试"由后台扫描* — 与 remind cron 重试等价但更复杂。

### 决策 7：配置字段替换 + 旧字段降级警告

**选择**：

- BREAKING 删除 `global.auto_renew.time_window_start` / `time_window_end`。
- 新增 `global.auto_renew.min_delay_seconds`（默认 30）/ `max_delay_seconds`（默认 180）。
- 配置加载时若检测到旧字段，记录 WARN 日志（"已废弃，将被忽略"），不阻塞启动。

**理由**：

- 旧字段语义在新模型下完全失效，无法 graceful 映射为新字段（窗口起止与延迟范围不是同一概念）。
- WARN + 默认值兜底，避免用户升级后服务直接挂掉。

**替代方案**：

- *保留旧字段作为别名* — 语义不一致，徒增混乱。
- *在 validation 里硬错* — 用户升级体验差。

### 决策 8：`response_data` / `accounts` 从 `JJZService` 传出

**选择**：扩展 `JJZService.get_multiple_status_optimized()` 的返回值（或新增配套方法）让调用方拿到原始 `response_data` 与 `accounts`，而不是让 `schedule_renew` 内部重新查 `stateList`。

**理由**：

- 重新查会多一次接口调用，增加风控风险，且 push_workflow 已经查过了。
- `response_data` 是 `extract_renew_metadata`（`elzqyms` / `elzmc` 等）的来源，必须传递。

**替代方案**：

- *renew 内重查* — 浪费请求 + 多走一次反爬延迟。
- *把 `response_data` 缓存到 Redis 让 renew 读取* — 跨进程不需要，纯内存传递更简单。

实现细节：可以让 `get_multiple_status_optimized` 增加一个 out 参数，或者新增 `get_multiple_status_with_raw()` 方法返回元组。具体方式在实现阶段决定，但接口契约是"调用方能拿到 raw response_data 和 accounts"。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| 进程在 sleep 期间被 SIGTERM，续办丢失 | 下一个 remind 时刻 push_workflow 重新决策并派发；用户最差等 4–6 小时（按默认 remind.times） |
| `checkHandle` 返回的日期不是预期的（场景①拿到今日、场景②拿到明日） | `execute_renew` 仍按 `jjrqs[0]` 提交；与现状一致，不增加新风险 |
| 多车牌错峰下信号量抢不到导致 sleep 超过 max_delay | 信号量 acquire 不设超时，最坏情况 N 辆车依次跑，总耗时 N × (random_delay + api_chain) ≈ N × 3 分钟，可接受 |
| 用户升级后未更新配置，旧字段 `time_window_*` 仍写在 yaml 里 | 启动 WARN 日志 + 默认值兜底，行为正确但用户能看到提示 |
| `RENEW_TOMORROW` 在 23:55 触发时接口未放号导致首次失败 | 失败仅一次提醒（`push_renew_result`），下一个 cron（00:00 之后）自然重试，用户体验可接受 |
| 现有 push_workflow 内并发调用 `process_single_plate`，多个车牌同时 `create_task` | 信号量保证 API 链串行；`asyncio.create_task` 本身线程安全 |
| 移除旧 `should_renew` 后单元测试覆盖中断 | 在 `tests/test_renew_decider.py` 里完整覆盖决策矩阵；`tests/test_auto_renew.py` 调整为新派发器的集成测试 |

## 迁移计划

**部署步骤**

1. 合并代码后，启动时若检测到旧 `time_window_*` 字段，输出 WARN 日志。
2. 用户在升级文档中按指引把 `global.auto_renew.time_window_start/end` 替换为 `min_delay_seconds/max_delay_seconds`（或直接删除，使用默认值）。
3. 验证：观察首日 remind 触发时是否有续办派发日志（检索 `[renew] decision=...` 与 `[renew] dispatched plate=...`）。

**回滚策略**

- 单 commit revert 即可恢复旧 cron 行为；旧 `time_window_*` 配置字段仍在 yaml 里时不影响 revert（旧代码会重新读到它们）。
- 用户的 Redis dedup key (`auto_renew:{plate}:{date}`) 与新旧实现兼容，无需清理。

## 待解决问题

无。所有决策点已与用户对齐确认。
