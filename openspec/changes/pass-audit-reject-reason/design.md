## 上下文

动机见 `proposal.md`。实现前需要知道的现状：

- 进京证状态有两条解析入口：`parse_all_jjz_records`（多账户批量，remind 主流程使用）与 `parse_jjz_response`（单车牌）。两者都通过 `parse_single_jjz_record` 或等价的字段拼装逻辑构造 `JJZStatus`，当前都不读取任何原因字段。
- 推送也有两条路径：`push_helpers.push_jjz_status`（步骤 6 逐车牌推送）与 `format_jjz_body_and_priority`（批量推送）。两条路径的 `INVALID` 分支都调用同一个 `format_jjz_error_content`，只是各自从 `jjz_data` 取值后传参。
- `error_message` 在 `push_helpers.push_jjz_status` 的 `else` 分支上会先经过 `_is_system_error` 判定；命中即跳过用户推送、改为只通知管理员。该判定是一张约 25 个关键词的表，含「未配置」「配置错误」「API错误」等中文词。
- `JJZStatus.to_dict()` 的输出被推送与 HA 同步共用；HA 同步按白名单取键，新增键不会自动进入 HA 属性。

## 目标 / 非目标

目标：让审核不通过的原因与上游状态描述原文抵达推送正文，且不改变任何状态判定结果、不影响其他状态的文案。

非目标：不引入模型或规则去解释、归类、改写上游原因；不把原因写入 HA 实体属性或 MQTT Discovery（本变更不涉及 HA contract）；不为原因文本新增配置项或模板变量；不处理 `ecbzxx`（待审记录）原因，待审记录尚无审核结论。

## 决策

**1. 用独立字段 `reject_reason` 承载上游业务原因，不动 `error_message` 语义。**

`error_message` 同时被 `_is_system_error` 用作"是否只通知管理员"的判据。若把上游原因写进 `error_message`，上游文本就有机会命中关键词表（例如真实原因「该车环保信息配置错误」命中「配置错误」），结果是用户收不到自己车牌的审核结论，而管理员收到一条假告警。把业务原因与系统错误分列两个字段，判据表就永远不会看到上游文本，不需要维护第二个关键词黑名单。

代价是 `JJZStatus` 多一个字段与一个 `to_dict` 键（4 行）。

备选：直接写 `error_message`（issue 原建议）——改动更小，但把上游可控文本接进了控制流，属于信任边界问题，故不采用。

**2. 取值优先级 `shsbyyms` → `shsbyy` → 车辆级 `bnbzyy`。**

记录级字段描述的是该条记录本身的审核结论，车辆级 `bnbzyy` 是车辆维度的兜底说明。按"越具体越优先"排序，只有记录级两个字段都为空时才回退到车辆级。

**3. 展示口径统一在 `format_jjz_error_content` 的入参上，而不是各调用点各改一遍。**

两条推送路径的 `INVALID` 分支都先算出「状态文本 = `blztmc` 或 `status`」和「原因 = `reject_reason` 或 `error_message`」，再以现有签名调用 `format_jjz_error_content`。为这两行取值加一个 `jjz_utils` 内的共享小函数，避免两处口径漂移；模板与函数签名都不变。

备选：给 `format_jjz_error_content` 增加 `blztmc` / `reject_reason` 关键字参数——签名增长，且两个调用点仍要各改一次，收益相同。

**4. 原因文本不做全角→半角规范化。**

`normalize_response_parens` 针对的是 `blztmc` / `jjzzlmc` 这类需要参与匹配的结构化字段，原因是自由文本、只用于展示，规范化反而可能改动上游原文。

## 风险 / 取舍

- [缓存里的旧记录没有 `reject_reason`，反序列化后为 `None`] → 展示逻辑对 `None` 与空串同等对待，回退到既有 `error_message`，与变更前行为一致；不需要缓存迁移。
- [上游将来把原因挪到别的字段] → 优先级链是显式白名单，字段改名时表现为原因回到空值并退化为旧文案，不会报错；属于可接受的降级。
- [`reject_reason` 随 `to_dict` 进入推送内部数据流] → 已确认 HA 同步按白名单取键，不会把原因发布成 HA 属性；无额外暴露面。
- [原因文本可能很长，撑大推送正文] → 上游原因为单句式短文本，未做截断；若实际出现超长文本，再考虑加长度上限。

## 迁移计划

无数据迁移、无配置变更。回滚即 revert 代码：`reject_reason` 在新旧代码间只影响展示，旧代码读到含该键的缓存字典会直接忽略。

## 待定问题

（无）
