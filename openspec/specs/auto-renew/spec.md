## 目的

本能力定义六环外进京证（`jjzzl=02`）自动续办的端到端机制：触发判断、随机延迟与全局错峰、API 调用链、申请数据组装、结果通知、当日防重复、提醒抑制、多账户上下文隔离。续办触发由提醒（remind）查询完成后的事件驱动逻辑发起。
## 需求
### 需求:续办触发判断
系统必须在每次提醒（remind）查询完成后，对每个启用了自动续办且具备六环外历史记录的车牌调用决策器进行分场景判断，并按返回的 `RenewDecision` 派发后续动作。决策必须基于全车牌覆盖信号 `today_covered` / `tomorrow_covered` 与车辆级字段 `sfyecbzxx` / `elzsfkb`，覆盖以下五种结果：`SKIP` / `RENEW_TODAY` / `RENEW_TOMORROW` / `PENDING` / `NOT_AVAILABLE`。优先级为 `PENDING > 决策矩阵`。决策器禁止读取六环外记录的 `valid_end` 来判断覆盖。

#### 场景:auto_renew未启用
- **当** 车牌的 `auto_renew` 配置为 `None` 或 `enabled=False`
- **那么** 决策器必须返回 `SKIP`，系统不得派发续办

#### 场景:无六环外记录
- **当** 车牌不存在六环外历史记录（`plate_renew_contexts` 中无对应 `renew_status`）
- **那么** 决策器必须返回 `SKIP`，原因是续办流程依赖六环外记录的 `vId` 等字段

#### 场景:已有待审记录优先
- **当** 车辆 `sfyecbzxx=True`
- **那么** 决策器必须返回 `PENDING`，无视覆盖信号与 `elzsfkb`，系统不得派发续办

#### 场景:今日明日均有覆盖
- **当** `today_covered=True` 且 `tomorrow_covered=True`，且 `sfyecbzxx=False`
- **那么** 决策器必须返回 `SKIP`，无视 `elzsfkb` 取值

#### 场景:今日有覆盖明日无覆盖且服务端可办
- **当** `today_covered=True` 且 `tomorrow_covered=False`，且 `sfyecbzxx=False`，且 `elzsfkb=True`
- **那么** 决策器必须返回 `RENEW_TOMORROW`，系统必须派发续办流程为明日补缺

#### 场景:今日有覆盖明日无覆盖但服务端不可办
- **当** `today_covered=True` 且 `tomorrow_covered=False`，且 `sfyecbzxx=False`，且 `elzsfkb=False`
- **那么** 决策器必须返回 `SKIP`，原因是政策窗口尚未开放（申请只在原证件失效当天 00:00 开放），系统不得派发续办、不得发送告警；下一轮 remind 时再决策

#### 场景:今日无覆盖且服务端可办
- **当** `today_covered=False`，且 `sfyecbzxx=False`，且 `elzsfkb=True`
- **那么** 决策器必须返回 `RENEW_TODAY`（无论 `tomorrow_covered` 取值），系统必须派发续办流程；明日是否覆盖由 checkHandle 后的 useful 过滤精判

#### 场景:今日无覆盖但有明日兜底且服务端不可办
- **当** `today_covered=False` 且 `tomorrow_covered=True`，且 `sfyecbzxx=False`，且 `elzsfkb=False`
- **那么** 决策器必须返回 `SKIP`，原因是用户已自有明日兜底（例如六环内待生效），不得发送 NOT_AVAILABLE 告警

#### 场景:今日明日均无覆盖且服务端不可办
- **当** `today_covered=False` 且 `tomorrow_covered=False`，且 `sfyecbzxx=False`，且 `elzsfkb=False`
- **那么** 决策器必须返回 `NOT_AVAILABLE`，系统必须推送"六环外进京证当前不可办理"告警

### 需求:续办随机时间调度
系统必须在续办派发时为每条协程生成 `[min_delay_seconds, max_delay_seconds]` 区间内的随机延迟（默认 30–180 秒），用于拟人化反爬。延迟期间不得占用全局信号量，sleep 醒来后才抢占信号量并执行 API 链。

#### 场景:派发后随机延迟
- **当** 决策命中 `RENEW_TODAY` 或 `RENEW_TOMORROW`，系统通过 `asyncio.create_task` 派发续办协程
- **那么** 协程必须先 `await asyncio.sleep(random.randint(min_delay_seconds, max_delay_seconds))`，再尝试获取信号量

#### 场景:使用默认延迟范围
- **当** 用户未配置 `global.auto_renew.min_delay_seconds` 与 `max_delay_seconds`
- **那么** 系统必须使用默认值 30 秒（min）与 180 秒（max）

### 需求:续办API调用链
系统必须按照以下顺序依次调用续办相关 API，每步均须校验 `code==200`，任何步骤失败必须中断整个流程并通知用户。`checkHandle` 返回 `jjrqs` 后必须基于 `today_covered` / `tomorrow_covered` 做 useful 过滤，仅对实际填补覆盖缺口的日期发起 `insertApplyRecord`。

#### 场景:完整调用链成功
- **当** 触发续办流程
- **那么** 系统必须依次调用以下 API 并校验每步成功：
  1. `applyVehicleCheck` — 提交 `{hphm, hpzl}`，校验车辆
  2. `getJsrxx` — 提交 `{}`，获取驾驶人信息 `{jsrxm, jszh, dabh}`
  3. `applyCheckNum` — 提交驾驶人信息，校验驾驶人
  4. `checkHandle` — 提交 `{vId, jjzzl:"02", hphm}`，获取可选进京日期 `jjrqs`
  5. `checkInputRoadInfo` — 提交 `{vId}`，检查是否需填行驶路线
  6. `insertApplyRecord` — 提交完整申请数据

#### 场景:选择首个填补缺口的日期
- **当** `checkHandle` 返回非空 `jjrqs` 数组
- **那么** 系统必须按以下规则过滤出 useful 日期：日期等于今天且 `today_covered=False`，或日期等于明天且 `tomorrow_covered=False`，或日期晚于明天且 `tomorrow_covered=False`；过滤后取首个作为 `jjrq`

#### 场景:服务端返回空数组
- **当** `checkHandle` 返回的 `jjrqs` 为空数组
- **那么** 系统必须中断续办流程并推送"当前无可选进京日期"告警，视为服务端异常；禁止写入当日防重 key

#### 场景:服务端返回的日期全部已被覆盖
- **当** `checkHandle` 返回非空 `jjrqs`，但经 useful 过滤后无任何可用日期（即所有候选日期都已被本地覆盖）
- **那么** 系统必须静默跳过续办，禁止推送任何通知；必须写入当日防重 key 避免下一轮 remind 重复派发；必须以 `RenewResult(success=False, skipped=True)` 终止

#### 场景:服务端返回的日期全部无法解析
- **当** `checkHandle` 返回非空 `jjrqs`，但所有元素都不是合法的 ISO 日期格式（如 `[""]` 或 `["not-a-date"]`）
- **那么** 系统必须推送 `"服务端返回的进京日期格式异常"` 告警，视为服务端数据异常；禁止写入当日防重 key；返回 `RenewResult(success=False, skipped=False, step="check_handle")`

#### 场景:校验步骤失败
- **当** 调用链中任何步骤返回 `code != 200`
- **那么** 系统必须立即中断续办流程，记录失败步骤名称和完整响应体，并通过该车牌配置的通知渠道推送错误信息

### 需求:续办申请数据组装
系统必须从多个数据源自动组装 `insertApplyRecord` 所需的完整请求体，禁止缺少任何必需字段。

#### 场景:正确组装请求体
- **当** 所有前置步骤成功完成
- **那么** 系统必须组装请求体，其中：
  - `vId`, `hphm`, `hpzl`, `ylzsfkb`, `elzsfkb`, `elzqyms`, `ylzqyms`, `elzmc`, `ylzmc`, `cllx` 来自 stateList 响应
  - `jsrxm`, `jszh`, `dabh` 来自 getJsrxx 响应
  - `jjrq` 来自 checkHandle 响应的 `jjrqs[0]`
  - `jjzzl` 固定为 `"02"`（六环外）
  - `jjmd`, `jjmdmc`, `area`, `jjdq`, `xxdz`, `jjdzgdjd`, `jjdzgdwd`, `sfzj`, `zjxxdz`, `zjxxdzgdjd`, `zjxxdzgdwd`, `sqdzgdjd`, `sqdzgdwd` 来自用户配置
  - `txrxx` 固定为 `[]`，`jingState`, `jjlk`, `jjlkmc`, `jjlkgdjd`, `jjlkgdwd` 固定为 `""`

### 需求:续办结果通知
系统必须在续办流程结束后通过该车牌已配置的通知渠道推送结果。`RenewResult` 区分三态：成功（`success=True`）、失败（`success=False, skipped=False`）、静默跳过（`success=False, skipped=True`）。静默跳过禁止触发任何通知。

#### 场景:续办提交成功
- **当** `insertApplyRecord` 返回 `code==200`，`RenewResult(success=True, skipped=False)`
- **那么** 系统必须推送通知，内容包含：车牌号、进京日期、进京证类型（六环外）、"已提交，等待审核"

#### 场景:续办失败
- **当** 续办流程中任何步骤失败，`RenewResult(success=False, skipped=False)`
- **那么** 系统必须推送通知，内容包含：车牌号、失败步骤名称、错误原因摘要

#### 场景:静默跳过不推送
- **当** `RenewResult.skipped` 为 `True`（如服务端返回的日期全部已被本地覆盖）
- **那么** 系统禁止推送任何通知；必须以 INFO 级日志记录跳过原因（含 `jjrqs` 与覆盖信号），便于事后排查

#### 场景:Token失效
- **当** 续办过程中 API 返回 Token 相关错误
- **那么** 系统必须推送通知，明确提示用户"Token 已失效，请手动更新配置中的 token"

### 需求:防重复提交
系统必须防止同一车牌在同一天内重复提交续办申请。当续办成功提交后写入 Redis 当日防重 key（TTL 24 小时）；当续办失败（包括 `checkHandle` 返回空 `jjrqs`）时不得写入防重 key，以便下一个 remind 时刻自然重试。

#### 场景:当日已成功提交过续办
- **当** 系统在 Redis 中检测到该车牌当日已有续办成功记录
- **那么** 系统必须跳过续办，记录日志说明"当日已提交续办，跳过"

#### 场景:成功提交后写入防重key
- **当** `insertApplyRecord` 返回 `code==200`
- **那么** 系统必须在 Redis 中写入 `auto_renew:{plate}:{today}` 记录，TTL 86400 秒

#### 场景:失败时不写防重key允许重试
- **当** 续办流程在任何步骤失败（包括 `checkHandle` 返回空 `jjrqs` 数组、Token 失效、API 报错）
- **那么** 系统禁止写入当日防重 key，下一个 remind 时刻 push_workflow 必须重新决策并允许再次派发

### 需求:续办触发抑制冲突提醒
当某车牌的续办决策为续办今日（`RENEW_TODAY`）或续办明日（`RENEW_TOMORROW`）时，系统必须抑制原本会发送的"明日尚未查询到进京证信息"或同类用户提醒，以避免与续办结果通知形成语义冲突；续办协程结束后必须通过 `push_renew_result` 单独发送结果通知。

#### 场景:命中续办时抑制提醒
- **当** `process_single_plate` 调用决策器返回 `RENEW_TODAY` 或 `RENEW_TOMORROW`
- **那么** 系统必须跳过 `push_jjz_reminder` 调用，且本次车牌处理结果中标记 `skipped=renew_dispatched`
- **并且** 系统必须通过 `asyncio.create_task` 异步派发续办协程，由协程结束时单独推送续办结果通知

#### 场景:命中NOT_AVAILABLE仍发送告警
- **当** 决策器返回 `NOT_AVAILABLE`（六环外不可办）
- **那么** 系统必须按现有逻辑推送"六环外进京证当前不可办理"告警，不得抑制

#### 场景:命中PENDING保留正常通知
- **当** 决策器返回 `PENDING`（已有待审记录）
- **那么** 系统必须按正常分支推送进京证状态通知，不得抑制

### 需求:多账户上下文隔离
当配置了多个 JJZ 账户时，系统必须按车牌记录每条记录对应的 (response_data, account) 上下文，并在派发续办时使用该车牌专属的账户 token 与原始响应，禁止跨账户混用。

#### 场景:不同账户车牌使用各自账户上下文
- **当** 车牌 A 的进京证记录来自账户 1，车牌 B 的进京证记录来自账户 2
- **那么** 系统派发 A 的续办协程时必须使用账户 1 的 token、URL 与原始 stateList 响应；派发 B 时必须使用账户 2 的对应数据

#### 场景:车牌缺少账户上下文时跳过派发
- **当** 某车牌在所有账户响应中都未匹配到记录（即 plate_contexts 中无对应项）
- **那么** 系统必须跳过该车牌的续办派发并记录 WARN 日志，不得使用其他车牌的上下文回退

#### 场景:同车牌出现在多账户时使用最新记录所在账户
- **当** 车牌 A 同时出现在账户 1 和账户 2 的 stateList 响应中
- **那么** 系统必须以 `apply_time` 最新的记录来源账户作为续办上下文，禁止使用首个匹配账户与最新记录混用

#### 场景:同车牌同时存在六环内/六环外记录时仅取六环外作为续办上下文
- **当** 车牌同时有六环内和六环外的进京证记录，且六环内的 apply_time 更新
- **那么** 系统必须在续办上下文 plate_contexts 中仅记录该车牌六环外记录中 apply_time 最新的一条；推送链路（results[plate]）仍可使用所有类型中最新的记录显示

### 需求:全局错峰串行执行
系统必须使用全局 `threading.Lock()` 串行执行（兼容跨事件循环/线程的 cron 与 REST API 触发），保证任意时刻最多只有一条续办 API 调用链在执行，以实现多车牌之间的错峰。锁的获取必须采用协程友好且取消安全的方式：禁止使用 `await asyncio.to_thread(LOCK.acquire)`——协程被取消时工作线程仍可能成功持锁但 try/finally 不可达，导致锁永久泄漏、后续续办全部死锁。

#### 场景:多车牌并发触发
- **当** 同一次 push_workflow 内有多辆车牌命中续办决策
- **那么** 系统必须在每条续办协程内通过全局 `threading.Lock()` 串行执行 `execute_renew`，前一条 API 链结束后才允许下一条进入

#### 场景:取消安全的锁获取
- **当** 续办协程在等待全局锁期间被外部取消（如进程关闭或上层 task.cancel()）
- **那么** 系统必须确保锁未被本协程持有时取消（无泄漏），或本协程已成功持有锁后才进入受 try/finally 保护的临界区；具体实现采用非阻塞 `acquire(blocking=False)` 配合 `await asyncio.sleep(0.1)` 轮询，让取消信号能在每次 sleep 抛出 `CancelledError`，此时本协程从未持锁，自动安全

#### 场景:信号量等待不设超时
- **当** 多条续办协程同时争抢全局锁
- **那么** 系统必须按醒来顺序排队，不得为锁获取设置超时时间，以避免因排队过久误判失败

### 需求:覆盖信号计算
系统必须在批量查询进京证状态阶段为每个车牌计算 `today_covered` 与 `tomorrow_covered` 两个布尔信号，并随续办上下文一同返回。覆盖判定基于车牌名下所有进京证记录（六环内 ∪ 六环外）的 `blztmc`（办理状态名称）与 `valid_start` / `valid_end`，禁止仅以 `apply_time` 最新一条记录的状态做替代。

#### 场景:全量记录参与覆盖判定
- **当** 系统在 `JJZService._query_multiple_status` 遍历某车牌的全部记录 triples 时
- **那么** 系统必须对每条记录调用覆盖检查，对今天与明天分别计算覆盖布尔；任意一条记录命中即认为该日有覆盖

#### 场景:覆盖检查的判定规则
- **当** 检查记录 `r` 在目标日 `d` 是否构成覆盖
- **那么** 系统必须同时满足以下三条才能判定为覆盖：
  - `r.valid_start` 与 `r.valid_end` 均非空且能解析为日期
  - `r.valid_start <= d <= r.valid_end`
  - `r.blztmc` 包含"生效中"或"待生效"任一关键字

#### 场景:有效期缺失时不计覆盖
- **当** 记录的 `valid_start` 或 `valid_end` 为空或解析失败
- **那么** 系统必须将该记录在任何目标日都判定为不覆盖，禁止用业务推断填补缺失

#### 场景:覆盖信号挂载到续办上下文
- **当** 计算完成
- **那么** 系统必须把 `today_covered` 与 `tomorrow_covered` 与 `(response_data, account, renew_status)` 一并写入 `plate_renew_contexts[plate]`；下游 `process_single_plate` 与 `run_renew_only_workflow` 必须从该上下文读取并向决策器与续办派发器传递

