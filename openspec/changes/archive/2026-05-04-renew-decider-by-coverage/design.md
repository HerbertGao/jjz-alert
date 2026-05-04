## 上下文

`auto-renew-event-driven` 把续办从 cron 改成事件驱动，但 `RenewDecider` 的判断口径仍然是上一代设计的延续："看六环外那条记录的 `valid_end` + `elzsfkb` + `sfyecbzxx`"。这个口径在两条服务端规则下产生噪音：

1. **互斥规则**：六环内与六环外进京证不能同时生效。当用户从六环外切换到六环内后，服务端把六环外置为失效并把 `elzsfkb` 置为 `False`。决策器看到 `elzsfkb=False` 直接发"续办失败：六环外进京证当前不可办理"——但用户的六环内证件正常工作，告警是纯噪音。
2. **政策窗口**：六环外续办申请只在原证件失效当天 00:00 开放。提前一天即便手动也办不了，服务端会用 `elzsfkb=False` 拒绝。决策器把这种"早了"也当作 NOT_AVAILABLE 告警。

副作用：六环外昨日过期 + 六环内仍有效 30 天的场景，决策器返回 `RENEW_TODAY`、派发续办协程，到 `checkHandle` 必然被服务端拒——白调用 4 次 API 还产生一次失败告警。

## 目标 / 非目标

**目标：**

- 决策器换轴：以"全车牌（六环内 ∪ 六环外）今天/明天的覆盖情况"为主信号，`elzsfkb` 降级为旁路开关。
- 把"政策窗口只在失效当天开放"的语义自然代入决策——通过"今天有覆盖 + `elzsfkb=False` → SKIP"这一规则隐式表达。
- 服务端给出的可办日期与本地覆盖发生交集时（`jjrqs` 全部已被本地覆盖），静默跳过、不打扰用户。
- 真问题（今日断档 + 服务端不让办）继续告警；服务端异常（`jjrqs=[]`）继续告警。
- 不改 `renew-config`、不动配置 schema、不影响多账户上下文隔离与全局错峰串行执行。

**非目标：**

- 不重构 `JJZService.parse` / 状态枚举体系。
- 不调整推送渠道、不改 `push_renew_result` 的消息模板。
- 不为"jjrqs 全部已覆盖"引入新的 `RenewDecision` 枚举值——按用户确认走 `SKIP`，让日志记录承担可观测责任。
- 不处理"无六环外记录但今天断档"——auto_renew 流程依赖六环外 `vId` 等字段，无法在缺少六环外历史记录时执行。

## 决策

### D1. 决策器签名扩展为四参数（keyword-only）

```python
def decide(
    *,
    plate_config: PlateConfig,
    outer_renew_status: JJZStatus | None,
    today_covered: bool,
    tomorrow_covered: bool,
) -> RenewDecision: ...
```

参数全部 keyword-only（`*` 强制）。原因见风险表：调用点改造涉及 4 处，位置参数会让"少传一个 cov 信号"或"参数错位"在运行时静默错路径；keyword-only 让 Python 在调用立刻 `TypeError`，调用方一改即知。

`outer_renew_status` 仍仅用于读取车辆级字段（`elzsfkb`、`sfyecbzxx`、`vId`、`hpzl` 等），**不再读取它的 `valid_end`**——覆盖判断完全交给两个布尔。

**为什么不传 `triples`/`merged_status` 直接进决策器**：决策器只需要最终的 `today_cov` / `tomorrow_cov` 信号，而不需要知道是哪条记录提供了覆盖。把覆盖计算固定在 `JJZService` 一处，决策器保持纯函数、无 I/O，单元测试只造两个布尔即可。

**替代方案：在决策器里用 `merged_jjz_status.status == VALID`**：拒绝。这只能反映"apply_time 最新一条是否生效"，无法处理"最新一条是过期六环外，但还有一条生效中的六环内"。需要遍历全集才准确。

### D2. 覆盖信号在 `JJZService._query_multiple_status` 计算

遍历 `triples`（`[(record, response_data, account), ...]`）时，对每条记录算两个本地布尔：

```python
def _is_effective_on(record, day):
    if not record.valid_start or not record.valid_end:
        return False
    if not (record.valid_start <= day <= record.valid_end):
        return False
    blztmc = record.blztmc or ""
    return "生效中" in blztmc or "待生效" in blztmc  # 已批准未来生效也算 cov
```

`today_cov = any(_is_effective_on(r, today) for r in records)`，`tomorrow_cov` 同。

**为什么用 `blztmc` 字符串匹配而不是 `JJZStatusEnum`**：`JJZStatusEnum.APPROVED_PENDING` 已经覆盖"已批准待生效"，但映射逻辑分散在 `_determine_status`，且不同入口用法不一。直接看 `blztmc` 文本是 stateList API 的契约层，最稳定。

**互斥规则的影响**：同一天最多只有一条记录是"生效中"。不需要去重；任意一条命中就 cov=True。

签名变更：`plate_renew_contexts[plate]` 从 `(response_data, account, renew_status)` 改为 `(response_data, account, renew_status, today_covered, tomorrow_covered)`。或者更整洁，包成 `dataclass PlateRenewContext`——但保持元组以最小化改动面（只两个调用点解包），把 dataclass 重构作为后续清理。

### D3. 决策矩阵（精确版）

记 `today_cov`、`tomorrow_cov`、`elzsfkb`、`sfyecbzxx`、`outer_exists`（六环外记录是否存在）、`auto_enabled`（auto_renew.enabled）。

```
auto_enabled == False ............................... → SKIP
outer_exists == False ............................... → SKIP   (无 vId, 无法 auto_renew)
sfyecbzxx == True ................................... → PENDING (优先级最高)
today_cov ─┬─ Y ─┬─ tomorrow_cov ─┬─ Y .............. → SKIP
           │     │                └─ N ─ elzsfkb ─┬─ T → RENEW_TOMORROW
           │     │                                └─ F → SKIP   (政策窗口未开)
           └─ N ─ elzsfkb ─┬─ T ...................... → RENEW_TODAY
                           └─ F ─ tomorrow_cov ─┬─ Y .. → SKIP   (有兜底)
                                                └─ N .. → NOT_AVAILABLE
```

**为什么"今日断档 + elzsfkb=True"无视 `tomorrow_cov` 都返回 `RENEW_TODAY`**：今天用户上路就会被罚——必须立刻办。如果服务端只给明天而明天已 cov，到 `checkHandle` 后会被 useful 过滤掉，静默 SKIP；若给今天，正好覆盖断档。决策器不替服务端预判。

### D4. `checkHandle` 后增加 useful 过滤

`auto_renew_service.execute_renew(...)` 接收 `today_covered` / `tomorrow_covered`。`checkHandle` 返回 `jjrqs` 后：

```python
def _filter_useful(jjrqs, today_covered, tomorrow_covered, today, tomorrow):
    useful = []
    for d_str in jjrqs:
        try:
            d = date.fromisoformat(d_str)
        except (TypeError, ValueError):
            continue  # 非法日期静默丢弃；调用方用 _has_parseable_date 区分
                      # "全部已被覆盖（静默 SKIP）" vs "全部不可解析（告警）"
        if d == today and not today_covered:
            useful.append(d_str)
        elif d == tomorrow and not tomorrow_covered:
            useful.append(d_str)
        elif d > tomorrow and not tomorrow_covered:
            useful.append(d_str)  # 服务端给后天起的连续日期，仍能填补 tomorrow 后的覆盖缺口
    return useful
```

三种结局：

| `jjrqs` | `useful` | 行动 |
|---|---|---|
| `[]` | `[]` | 推送 `"当前无可选进京日期"` 告警（服务端异常，保留旧语义） |
| 至少一项可解析 / 全部已覆盖 | `[]` | 静默 SKIP；写入当日防重 key 避免下一轮 remind 再派发；返回 `RenewResult(skipped=True)` |
| 全部不可解析（如 `[""]` / `["not-a-date"]`） | `[]` | 视为服务端数据异常，推送 `"服务端返回的进京日期格式异常"` 告警；**不写**防重 key；返回 `RenewResult(success=False, skipped=False, step="check_handle")` |
| 至少一项可解析 / 至少一项 useful | 非空 | 取 `useful[0]` 作 `jjrq` 提交 |

**为什么 `jjrqs=[]` 与 `useful=[]` 区别对待**：前者是"服务端啥都不给"——可能是政策异动、token 失效、服务端 bug，值得人工看一眼；后者是"服务端给的我都不需要"——典型的过渡期 / 待生效冲突，是预期内静默场景。

**为什么"全部不可解析"也告警**：与 `jjrqs=[]` 同源（服务端给的东西不可用），都是异常信号；本地无法判断是返回格式变化还是 token/接口故障，告警让人工判断比静默吞掉安全。

### D5. `RenewResult` 增加 `skipped: bool`

三态语义：

```
success=True,  skipped=False → 续办成功（推"已提交，等待审核"）
success=False, skipped=False → 续办失败（推失败原因，含 NOT_AVAILABLE / Token 失效 / API 链异常）
success=False, skipped=True  → 静默跳过（写防重 key、不推送、记 INFO 日志）
```

`push_renew_result` 在入口处 `if result.skipped: return` 短路。

**为什么不把 `skipped` 编进 `success` 字段**：`success=False` 已绑定到"出问题了"语义并贯穿日志/可观测/上层判断；引入第三个字段比 overload 现有字段更清晰，单元测试也更容易断言。

### D6. 调用点改造

| 调用点 | 改动 |
|---|---|
| `JJZService._query_multiple_status` | 计算并返回两个布尔；扩展 `plate_renew_contexts` 元组 |
| `JJZService.get_multiple_status_with_context` | 返回类型签名同步更新（仅类型注解） |
| `JJZPushService.process_single_plate` | 解包新元组，传给 `decide(...)` 与 `schedule_renew(...)` |
| `renew_workflow.run_renew_only_workflow` | 同上 |
| `renew_trigger.schedule_renew` | 形参增加两个布尔，透传到 `execute_renew` |
| `auto_renew_service.execute_renew` | 形参增加两个布尔；checkHandle 后做 useful 过滤；构造 `RenewResult(skipped=True)` 时短路返回 |

## 风险 / 权衡

| 风险 | 缓解 |
|---|---|
| 决策器签名变化波及多处调用——漏改一处会出现"位置参数错位"或"少传 cov 信号" | 用 keyword-only 参数（`def decide(*, plate_config, outer_renew_status, today_covered, tomorrow_covered)`）。Python 在调用时会立刻 TypeError，避免静默错位 |
| `blztmc` 字符串匹配漏掉边角状态（"待审核"、"审核通过"等） | spec 明确列出"生效中"和"待生效"两类被认作 cov；其它状态显式视作不 cov，不引入隐式判断。覆盖信号由独立单元测试矩阵验证 |
| `useful 过滤`过于激进，把"服务端只给后天但今天断档"也变成 SKIP | 允许"`d > tomorrow` 且 `tomorrow_cov=False`"也进 useful——服务端给后天意味着今天/明天都拿不到，但能填补 day-after-tomorrow 起的真空，仍然有用。今日断档无解的情况由 D3 矩阵的 `RENEW_TODAY` 派发后，若服务端 `jjrqs` 全部 > today，依然会提交一个未来日期的申请（聊胜于无） |
| `today_covered` / `tomorrow_covered` 计算依赖正确解析 `valid_start` / `valid_end`——解析失败会导致漏判 | `_is_effective_on` 在 valid_start/end 缺失时返回 `False`，与"无 cov"对齐——保守策略，宁可派发后被拒也不漏告警 |
| 行为修正"六环外过期 + 六环内仍有效 → 不再续办六环外"——理论上用户可能本来希望"六环内的 7 天到期了能立刻有六环外兜底" | 实测中六环内最多 7 天，过期后 `today_cov=False`，决策器自然回到 `RENEW_TODAY`。本变更不会让任何"原本能续到"的情况变成"续不到"，只会让"原本必败的派发"提前 SKIP |
| 测试覆盖矩阵需要重写——容易遗漏边界 | tasks.md 中按矩阵 9 条核心 + 5 条边界 + 4 条 jjrqs 分支 + 3 条覆盖信号计算明确列出必测用例 |

## 迁移计划

无配置变更，无破坏。代码 + 测试一同合并即可生效：

1. 实现 + 单测全绿。
2. 本地用 mock stateList 响应跑过 push_workflow，验证：
   - 用户津A86X64（六环内活跃）的 `process_single_plate` 不再产生 NOT_AVAILABLE 推送。
   - 模拟"六环外今日到期 + 无六环内"——`RENEW_TOMORROW` 正常派发。
   - 模拟"六环外昨日过期 + 六环内活跃"——决策器返回 `SKIP`，无 API 调用。
3. 灰度：与之前的 auto-renew-event-driven 一样，小流量观察一晚的 cron + 当天的 remind 触发链路日志，确认无 `RENEW_*` 误派发与 `NOT_AVAILABLE` 噪音消失后再放量。

回滚：直接 revert 本变更。决策器签名回退会触发 TypeError，让上层立刻发现回退状态，无静默错路径。
