## 为什么

车牌津A86X64 报告：六环外进京证自动续办失败，失败步骤 `eligibility_check`，原因"六环外进京证当前不可办理"。诊断发现该车牌当前有一张生效中的六环内进京证——根据北京交管服务端规则，**六环内与六环外进京证互斥**：六环内生效时服务端会自动将六环外置为失效状态，并把车辆级字段 `elzsfkb` 置为 `False`。

当前决策器（`renew_decider.decide()`）仅以"六环外最新记录的 `valid_end` + `elzsfkb` + `sfyecbzxx`"为判断依据，命中 `elzsfkb=False` 即返回 `NOT_AVAILABLE` 并通过 `push_renew_result` 推送"续办失败"告警。这把"服务端按规则不让重复办"误判为"系统出错"，**对所有同时持有六环内/六环外进京证（或正在交接中）的用户产生持续性噪音告警**。同时旧逻辑也会在六环外过期但六环内仍有效时白派发续办，必然在服务端被拒——浪费 API 调用且制造另一类失败告警。

## 变更内容

- **决策口径换轴**：从"看六环外那条记录的 `valid_end`"换成"看全车牌（六环内 ∪ 六环外）今天/明天是否有覆盖"。
  - 新增决策输入信号 `today_covered` / `tomorrow_covered`，由 `JJZService._query_multiple_status` 在遍历 triples 时基于"任意进京证 `blztmc` 含'生效中'或'已批准待生效'，且 `valid_start <= 目标日 <= valid_end`"算出。
  - `decide()` 签名扩展为 keyword-only：`decide(*, plate_config, outer_renew_status, today_covered, tomorrow_covered)`（用 `*` 强制 keyword 调用，避免位置参数错位静默走错路径）。
- **将"申请窗口只在失效当天 00:00 开放"政策代入决策**：今天有覆盖 + `elzsfkb=False`（含明天有/无覆盖两种情况）一律返回 `SKIP` 不告警；只有今天断档 + `elzsfkb=False` 才返回 `NOT_AVAILABLE` 推真告警。
- **`checkHandle` 后增加"useful 过滤"**：把 `today_covered` / `tomorrow_covered` 一路透传到 `execute_renew`；拿到 `jjrqs` 后过滤出"实际填补缺口"的日期：
  - 服务端给空数组 `jjrqs=[]` → **保留**现有"无可选进京日期"告警（视作服务端异常）。
  - 服务端给的日期都已被本地覆盖 → 静默 `SKIP`，并写入当日防重 key 避免下一轮 remind 重复派发。
  - 否则取首个填补缺口的日期作为 `jjrq` 提交。
- **`RenewResult` 增加 `skipped: bool`**：区分"成功 / 失败 / 静默跳过"三种结局；`push_renew_result` 在 `skipped=True` 时不发通知。
- **行为修正（非破坏）**——这三条是修复服务端互斥规则下旧逻辑的误判，不是行为破坏：
  - 六环外昨日过期 + 六环内仍有效：旧 `RENEW_TODAY` 派发（必然被拒），新 `SKIP`。
  - 六环外今日到期 + 六环内今/明日都有效：旧 `RENEW_TOMORROW` 派发（必然被拒），新 `SKIP`。
  - `elzsfkb=False` + 今天有覆盖：旧 `NOT_AVAILABLE` 告警（噪音），新 `SKIP`。

## 功能 (Capabilities)

### 新增功能

无。

### 修改功能

- `auto-renew`：
  - 修改"续办触发判断"——决策口径从"六环外 `valid_end`"换成"全车牌覆盖缺口 + `elzsfkb`"，整张场景表重写。
  - 修改"续办API调用链 / 选择最早可用日期"——增加"useful 过滤"语义：从 `jjrqs` 中取首个填补缺口的日期，而非无条件取 `jjrqs[0]`。
  - 修改"续办API调用链 / 无可选日期"——区分"`jjrqs` 全部已被覆盖（静默 SKIP）"与"`jjrqs=[]` 服务端异常（仍告警）"。
  - 修改"续办结果通知 / 续办失败"——`skipped=True` 时不推送任何通知。
  - 新增"已有覆盖时静默不推 NOT_AVAILABLE"场景。
  - 新增"jjrqs 全部已覆盖时静默"场景。

不动 `renew-config`。

## 影响

**代码**

- 修改：`jjz_alert/service/jjz/renew_decider.py` —— `decide()` 签名加 `today_covered` / `tomorrow_covered`；矩阵按新表实现；删去依赖 `outer_renew_status.valid_end` 的旧分支与对 `JJZStatusEnum.EXPIRED` 的硬编码。
- 修改：`jjz_alert/service/jjz/jjz_service.py` —— `_query_multiple_status` 在遍历 triples 时计算 `today_covered` / `tomorrow_covered` 并挂在 `plate_renew_contexts[plate]` 元组上；返回签名相应扩展。
- 修改：`jjz_alert/service/jjz/renew_trigger.py` —— `schedule_renew(...)` 增加两个布尔参数并透传。
- 修改：`jjz_alert/service/jjz/auto_renew_service.py` —— `execute_renew` 接受 `today_covered` / `tomorrow_covered`；`checkHandle` 后做 useful 过滤；`RenewResult` 增加 `skipped` 字段；`push_renew_result` 在 `skipped=True` 时跳过推送。
- 修改：`jjz_alert/service/notification/jjz_push_service.py` —— `process_single_plate` 调用点：`decide(...)` 与 `schedule_renew(...)` 都传入新参数。
- 修改：`jjz_alert/service/jjz/renew_workflow.py` —— renew-only 工作流同步更新调用点。

**测试**

- 重写 `tests/unit/service/test_renew_decider.py`：覆盖新矩阵 9 条核心 + 5 条边界（INVALID 状态、无六环外记录、auto_renew=None、auto_renew.enabled=False、`sfyecbzxx=True` 优先级）。
- 扩展 `tests/unit/service/test_renew_workflow.py` 与 `tests/unit/service/test_auto_renew.py`：新增 `jjrqs` useful 过滤的 4 个分支（today 在内 / 仅 tomorrow / 全部已覆盖未来日 / `jjrqs=[]`）。
- 扩展 `tests/unit/service/test_jjz_service.py`（如存在；否则新增）：覆盖 `today_covered` / `tomorrow_covered` 的计算（多记录共存、待生效记录、互斥状态）。

**配置 / 运行时**

- 无配置项变化。
- 行为上：六环内活跃期间不再产生 NOT_AVAILABLE 噪音；服务端互斥规则被原生处理；六环外过期但六环内仍有效时不再白派发续办，节省 API 调用。
