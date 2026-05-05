## 为什么

某车牌（仅持有六环内进京证记录、从未办过六环外）在配置正确开启 `auto_renew.enabled=true` 的情况下，六环内进京证已过期但**完全没有触发自动续办**，且日志中无任何决策记录。根因是 `_query_multiple_status` 内的硬过滤：当车牌名下没有任何"六环外"历史记录时，直接不写入 `plate_renew_contexts`，决策器从未被调用，连 INFO 日志都不会打。

但拆开续办请求体的字段来源后发现：组装 `insertApplyRecord` 真正需要的字段（`vId` / `hpzl` / `cllx` / `elzsfkb` / `ylzsfkb` / `sfyecbzxx`）都在 vehicle 层（`bzclxx[i]`），同一辆车的所有记录都共享同一份；元数据（`elzqyms` / `ylzqyms` / `elzmc` / `ylzmc`）来自 `data` 顶层；驾驶人信息和 `jjrq` 是独立 API 实时拉取的。**没有一个字段真正依赖"该车牌过去办过六环外"这个前提。** 这条过滤是 `b8a8b1a`（首版六环外续办）遗留的过度防御，沿用至今。

放宽这条过滤后，"仅有六环内进京证（甚至已过期）的车牌"就能正常进入决策器，按既有覆盖缺口逻辑申办六环外。

## 变更内容

- 放宽 `JJZService._query_multiple_status` 的续办上下文写入条件：从"必须有六环外记录"改为"该车牌在任一账户响应中出现过即可"。`renew_status` 取该车牌全部记录中 `apply_time` 最新的一条（六环内/六环外不限），用于读取车辆级字段。
- 同步移除 `renew_decider.decide` 注释中"无六环外历史记录 → SKIP"的分支说明（实际逻辑由 `outer_renew_status is None` 改为"上下文缺失才 SKIP"，语义保持不变但触发条件更窄）。
- 把 `renew_workflow.run_renew_only_workflow` 中 `ctx is None` 的日志从 DEBUG 提升到 INFO，便于运维排查"为什么没续办"。
- 修订 `auto-renew` capability spec：移除"无六环外记录 → SKIP"场景，调整"多账户上下文隔离"中"仅取六环外作为续办上下文"的场景为"取所有记录中 apply_time 最新一条"。

## 功能 (Capabilities)

### 新增功能
（无）

### 修改功能
- `auto-renew`: 续办上下文构建口径从"仅含六环外历史"放宽为"任意进京证记录均可进入续办"；决策器入口的"缺六环外"短路 SKIP 删除；`run_renew_only_workflow` 上下文缺失日志提级到 INFO。

## 影响

- 代码：
  - `jjz_alert/service/jjz/jjz_service.py`（`_query_multiple_status` 上下文写入分支）
  - `jjz_alert/service/jjz/renew_decider.py`（注释与无六环外分支说明）
  - `jjz_alert/service/jjz/renew_workflow.py`（`ctx is None` 日志级别）
- 测试：`tests/unit/service/test_jjz_service.py`、`tests/unit/service/test_renew_decider.py`、`tests/unit/service/test_renew_workflow.py` 需更新或新增覆盖"仅有六环内记录的车牌"场景。
- 行为：之前从未办过六环外的车牌，启用 `auto_renew` 后将首次进入续办流程；六环内+六环外并存的车牌行为不变（vehicle 层字段共享，请求体一致）。
- API/依赖：无变化。
