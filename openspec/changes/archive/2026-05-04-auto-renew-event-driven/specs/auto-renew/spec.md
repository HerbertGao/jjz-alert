## 新增需求

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
系统必须使用全局 `threading.Lock()` 串行执行（兼容跨事件循环/线程的 cron 与 REST API 触发），保证任意时刻最多只有一条续办 API 调用链在执行，以实现多车牌之间的错峰。

#### 场景:多车牌并发触发
- **当** 同一次 push_workflow 内有多辆车牌命中续办决策
- **那么** 系统必须在每条续办协程内通过全局 `threading.Lock()`（配合 `asyncio.to_thread` 抢锁）串行执行 `execute_renew`，前一条 API 链结束后才允许下一条进入

#### 场景:信号量等待不设超时
- **当** 多条续办协程同时争抢全局锁
- **那么** 系统必须按醒来顺序排队，不得为锁获取设置超时时间，以避免因排队过久误判失败

## 修改需求

### 需求:续办触发判断
系统必须在每次提醒（remind）查询完成后，对每个启用了自动续办的车牌调用决策器进行分场景判断，并按返回的 `RenewDecision` 派发后续动作。决策必须基于 `jjz_status.valid_end`、`sfyecbzxx`、`elzsfkb` 三个字段，覆盖以下五种结果：`SKIP` / `RENEW_TODAY` / `RENEW_TOMORROW` / `PENDING` / `NOT_AVAILABLE`。优先级为 `PENDING > NOT_AVAILABLE > RENEW_* > SKIP`。

#### 场景:今日有效且明日有效
- **当** `valid_start <= today` 且 `tomorrow <= valid_end`，且 `sfyecbzxx=False`，且 `elzsfkb=True`
- **那么** 决策器必须返回 `SKIP`，系统不得派发续办

#### 场景:今日有效但明日无效（场景①）
- **当** `valid_start <= today <= valid_end` 且 `tomorrow > valid_end`，且 `sfyecbzxx=False`，且 `elzsfkb=True`
- **那么** 决策器必须返回 `RENEW_TOMORROW`，系统必须派发续办流程，目标是续办明日的进京证

#### 场景:今日已过期（场景②）
- **当** `valid_end < today` 或 `status=EXPIRED`，且 `sfyecbzxx=False`，且 `elzsfkb=True`
- **那么** 决策器必须返回 `RENEW_TODAY`，系统必须派发续办流程，目标是续办今日的进京证

#### 场景:状态INVALID且无有效期跳过
- **当** `status=INVALID` 且 `valid_end` 为空（无法解析有效期）
- **那么** 决策器必须返回 `SKIP`，因为缺乏续办所需的 vId/有效期上下文，旧 should_renew 行为亦如此；用户已确认"无续办上下文"边缘 case 不处理

#### 场景:已有待审记录
- **当** 车辆 `sfyecbzxx=True`
- **那么** 决策器必须返回 `PENDING`（无论 valid_end 状态），系统不得派发续办

#### 场景:六环外不可办理
- **当** `elzsfkb=False`
- **那么** 决策器必须返回 `NOT_AVAILABLE`，系统不得派发续办，但必须推送"六环外进京证当前不可办理"告警

#### 场景:非六环外记录跳过
- **当** jjz_status.jjzzlmc 不包含"六环外"或为空
- **那么** 决策器必须返回 `SKIP`，因为续办流程固定 `jjzzl="02"` 仅支持六环外续办

#### 场景:auto_renew未启用
- **当** 车牌的 `auto_renew` 配置为 `None` 或 `enabled=False`
- **那么** 决策器必须返回 `SKIP`，系统不得派发续办

### 需求:续办随机时间调度
系统必须在续办派发时为每条协程生成 `[min_delay_seconds, max_delay_seconds]` 区间内的随机延迟（默认 30–180 秒），用于拟人化反爬。延迟期间不得占用全局信号量，sleep 醒来后才抢占信号量并执行 API 链。

#### 场景:派发后随机延迟
- **当** 决策命中 `RENEW_TODAY` 或 `RENEW_TOMORROW`，系统通过 `asyncio.create_task` 派发续办协程
- **那么** 协程必须先 `await asyncio.sleep(random.randint(min_delay_seconds, max_delay_seconds))`，再尝试获取信号量

#### 场景:使用默认延迟范围
- **当** 用户未配置 `global.auto_renew.min_delay_seconds` 与 `max_delay_seconds`
- **那么** 系统必须使用默认值 30 秒（min）与 180 秒（max）

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
