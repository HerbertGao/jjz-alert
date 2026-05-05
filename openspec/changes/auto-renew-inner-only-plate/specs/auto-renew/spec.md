## 修改需求

### 需求:续办触发判断
系统必须在每次提醒（remind）查询完成后，对每个启用了自动续办且具备 `plate_renew_contexts` 中续办上下文的车牌调用决策器进行分场景判断，并按返回的 `RenewDecision` 派发后续动作。决策必须基于全车牌覆盖信号 `today_covered` / `tomorrow_covered` 与车辆级字段 `sfyecbzxx` / `elzsfkb`，覆盖以下五种结果：`SKIP` / `RENEW_TODAY` / `RENEW_TOMORROW` / `PENDING` / `NOT_AVAILABLE`。优先级为 `PENDING > 决策矩阵`。决策器禁止读取六环外记录的 `valid_end` 来判断覆盖。

#### 场景:auto_renew未启用
- **当** 车牌的 `auto_renew` 配置为 `None` 或 `enabled=False`
- **那么** 决策器必须返回 `SKIP`，系统不得派发续办

#### 场景:无续办上下文
- **当** 车牌在所有账户的 stateList 响应中均未匹配到任何记录（`plate_renew_contexts` 中无对应条目）
- **那么** 系统必须在工作流入口跳过该车牌并以 INFO 级日志记录"缺少续办上下文，跳过"，决策器不得被调用

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

#### 场景:仅有六环内记录的车牌进入决策
- **当** 车牌当前在 stateList 中只有六环内类型的进京证记录（包括已失效），且 `auto_renew.enabled=True`，车辆 `sfyecbzxx=False`、`elzsfkb=True`、`today_covered=False`
- **那么** 决策器必须返回 `RENEW_TODAY`，系统必须正常派发六环外续办流程；禁止以"无六环外历史"为由短路返回 `SKIP`

### 需求:多账户上下文隔离
当配置了多个 JJZ 账户时，系统必须按车牌记录每条记录对应的 (response_data, account) 上下文，并在派发续办时使用该车牌专属的账户 token 与原始响应，禁止跨账户混用。续办上下文中的 `renew_status` 必须仅承诺车辆级字段（`vId` / `hpzl` / `cllx` / `elzsfkb` / `ylzsfkb` / `sfyecbzxx`）的语义稳定性，record 级字段（`jjzzlmc` / `valid_start` / `valid_end` / `blztmc`）不构成续办契约。

#### 场景:不同账户车牌使用各自账户上下文
- **当** 车牌 A 的进京证记录来自账户 1，车牌 B 的进京证记录来自账户 2
- **那么** 系统派发 A 的续办协程时必须使用账户 1 的 token、URL 与原始 stateList 响应；派发 B 时必须使用账户 2 的对应数据

#### 场景:车牌缺少账户上下文时跳过派发
- **当** 某车牌在所有账户响应中都未匹配到记录（即 plate_contexts 中无对应项）
- **那么** 系统必须跳过该车牌的续办派发并记录 INFO 级日志，不得使用其他车牌的上下文回退

#### 场景:同车牌出现在多账户时使用最新记录所在账户
- **当** 车牌 A 同时出现在账户 1 和账户 2 的 stateList 响应中
- **那么** 系统必须以 `apply_time` 最新的记录来源账户作为续办上下文，禁止使用首个匹配账户与最新记录混用

#### 场景:续办上下文取所有记录中最新一条
- **当** 车牌名下存在多条进京证记录（六环内、六环外或两者并存）
- **那么** 系统必须在续办上下文 `plate_contexts` 中以全部记录中 `apply_time` 最新一条作为 `renew_status`，无论该记录类型是六环内还是六环外；下游消费方仅可读取车辆级字段

## 移除需求

### 需求:无六环外记录场景下短路 SKIP
**Reason**: 续办请求所需字段（`vId` / `hpzl` / `cllx` / `elzsfkb` / `ylzsfkb` / `sfyecbzxx`）均来自 vehicle 层，每条 record 复制自同一辆车的相同字段；元数据来自 stateList 响应 `data` 顶层；驾驶人信息与 `jjrq` 由独立 API 实时拉取。组装 `insertApplyRecord` 不依赖"该车牌过去办过六环外"这一前提，原过滤是首版实现的过度防御，导致仅持有六环内记录的车牌（如新启用 `auto_renew` 的车）即使具备办理资格也无法触发续办。

**Migration**: 决策器入口的"`outer_renew_status is None` → `SKIP`"分支语义改为"上下文真正缺失才 SKIP"——`_query_multiple_status` 现在为任何在 stateList 响应中出现过的车牌写入 `plate_renew_contexts`，`renew_status` 取所有记录中 apply_time 最新一条。仅当车牌在所有账户响应中都未匹配到记录时才命中"无续办上下文"分支。无需用户操作。
