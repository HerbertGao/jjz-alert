## 上下文

`JJZService._query_multiple_status` 在批量查询完所有账户的 `stateList` 响应后，要为每个车牌产出两类输出：
1. `results[plate]` — 用于状态推送的最新记录（六环内/六环外不限），按 `apply_time` 取最新。
2. `plate_contexts[plate]` — 用于自动续办派发的上下文六元组 `(response_data, account, renew_status, today_covered, tomorrow_covered, today_anchor)`。

第二类目前的写入条件是"该车牌至少有一条 `jjzzlmc` 包含'六环外'的记录"，且 `renew_status` 必须从该车牌的六环外记录中取最新一条。这是 `b8a8b1a`（首版六环外续办）就有的硬过滤。

但实际续办流程对 `renew_status` 的字段消费集是：
- `renew_decider.decide`：仅读 `sfyecbzxx` / `elzsfkb`（vehicle 层）
- `renew_workflow.run_renew_only_workflow` / `JJZPushService.process_single_plate`：日志读 `elzsfkb` / `sfyecbzxx`（vehicle 层），其余原样下发
- `renew_trigger.schedule_renew`：透传，不读字段
- `auto_renew_service.execute_renew`：读 `vId` / `hpzl` / `cllx` / `elzsfkb` / `ylzsfkb` / `plate`（全是 vehicle 层 + plate 本身）

`jjz_parse.parse_single_jjz_record` 把 `vehicle` 层字段（vId/hpzl/cllx/elzsfkb/ylzsfkb/sfyecbzxx）复制到该车牌**每一条** record 的 `JJZStatus` 上。因此同一辆车的任何 record（无论六环内/六环外）的这些字段值相同。

## 目标 / 非目标

**目标：**
- 让"仅持有六环内进京证（活跃或已过期）但开启了 `auto_renew` 的车牌"能够进入续办决策与派发流程。
- 保留既有覆盖缺口决策矩阵不变。
- 改善"无续办上下文"路径的可观测性（日志提级 INFO）。

**非目标：**
- 不修改决策矩阵的 5 种结果（SKIP / RENEW_TODAY / RENEW_TOMORROW / PENDING / NOT_AVAILABLE）。
- 不引入"续办六环内"的能力（`jjzzl` 仍硬编码 `"02"`）。
- 不修改防重 key、随机延迟、全局锁等续办派发机制。
- 不改 `results[plate]` 的取值口径（仍取所有记录中 apply_time 最新的一条）。

## 决策

### 决策 1：放宽 `outer_triples` 过滤为"全量 triples"

**做法**：在 `_query_multiple_status` 中删除 `outer_triples` 中间变量。`renew_record` 直接用与 `results[plate]` 同源的 `latest_record`（即 `max(triples, key=lambda t: t[0].apply_time or "")`），同时复用其对应的 `response_data` 与 `account`。

```python
latest_triple = max(triples, key=lambda t: t[0].apply_time or "")
latest_record, latest_response, latest_account = latest_triple
results[plate] = latest_record
if latest_record.status != JJZStatusEnum.ERROR.value:
    await self._cache_status(latest_record)
today_covered = any(_is_effective_on(t[0], today) for t in triples)
tomorrow_covered = any(_is_effective_on(t[0], tomorrow) for t in triples)
plate_contexts[plate] = (
    latest_response, latest_account, latest_record,
    today_covered, tomorrow_covered, today,
)
```

**为什么不是"优先六环外，回退六环内"**：vehicle 层字段在所有 record 上一致，不存在"六环外那条更准"的可能。简单取最新即可。强行"优先六环外"会让代码多一条不必要的分支，并和 `results[plate]` 的取值口径不一致。

**替代方案**：保留 `outer_triples` 但在为空时回退到全量。被否决——增加代码复杂度而无收益。

### 决策 2：`renew_decider.decide` 的 `outer_renew_status is None` 分支保留

`outer_renew_status` 仍可能为 `None`（车牌在所有账户响应里都没匹配到记录），此时 `decide` 返回 `SKIP` 是正确的。但这是真正"无上下文"的兜底，并非"无六环外"。注释中"无六环外历史记录 → SKIP（缺 vId 等续办字段）"的说明改为"上下文缺失 → SKIP"。

### 决策 3：`renew_workflow` 的 ctx 缺失日志提级到 INFO

```python
if ctx is None:
    logger.info(f"[renew_only] 车牌 {plate} 缺少续办上下文，跳过")
    continue
```

DEBUG 级在生产 INFO 配置下不可见，这次问题排查的难点之一就是它静默。提级到 INFO 后每天最多 1 条/车（凌晨兜底），对日志体积无压力。

`JJZPushService.process_single_plate` 中类似的 ctx 缺失分支同步检查（如有）。

### 决策 4：spec 修订范围

`openspec/specs/auto-renew/spec.md` 需要在增量规范中：
- **删除**"无六环外记录"场景（lines 12-14），由"无续办上下文"覆盖。
- **修改**"同车牌同时存在六环内/六环外记录时仅取六环外作为续办上下文"场景（lines 166-168）：取所有记录中 `apply_time` 最新一条。
- **更新**"覆盖信号挂载到续办上下文"等表述中"必须有六环外"的隐含前提（如果有）。

## 风险 / 权衡

- **风险**：六环内 record 的 `valid_start/valid_end/blztmc/jjzzlmc` 写入 `renew_status` 后被未来代码误用 → 缓解：本次变更不引入新消费方；新增 unit test 覆盖"renew_status.jjzzlmc 为'六环内'时仍能正常派发"，把约束钉在测试里；spec 中明确 `renew_status` 仅承诺 vehicle 层字段，record 层字段不构成续办契约。
- **风险**：之前"无六环外"被静默跳过的车辆，现在会进入决策器，可能首次触发 `NOT_AVAILABLE` 告警 → 这是预期行为，正是用户最初期望的"主动告警/续办"。如果某车牌尚未具备六环外办理资格（比如新车未注册等场景），告警内容已经明确为"六环外进京证当前不可办理"，用户可据此判断。
- **权衡**：放宽过滤后，仅持有"已过期六环内"记录的车牌每轮 remind 都会进入决策器并大概率走 `RENEW_TODAY` 派发。`schedule_renew` 已有当日防重 key 与全局锁，多触发不会造成重复提交；首轮成功后写入防重 key，当日不再尝试。

## 迁移计划

- 纯代码改动，无数据迁移、无配置迁移、无依赖变更。
- 部署：合并 → 走现有 GHA 镜像构建 → mac-mini 上 `docker compose pull && docker compose up -d`。
- 回滚：直接 revert PR 即可，无副作用残留。
- 验证：合入后下一轮 remind（`06:00` / `08:00` / `12:30` / `19:00` / `23:55`）触发时，目标车牌（仅持有六环内记录的那一辆）应在日志中出现 `[renew] decision plate=<plate> -> ...`。如车辆资格 OK 应进入派发；否则应见 NOT_AVAILABLE 告警通知（明确告知用户该车暂无办理资格）。
