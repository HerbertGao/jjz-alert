## Why

进京证审核不通过时，上游在记录里已经给出了具体原因（记录级 `shsbyyms` / `shsbyy`，车辆级 `bnbzyy`），但解析层从不读取这些字段，推送正文最终只剩状态枚举值 `invalid`，用户看到「车牌X的进京证(六环内)状态：invalid。」却不知道到底哪里不通过。原因文本本来就在响应里，属于纯透传缺失，不需要任何推断或模型。

## What Changes

- 解析层透传审核不通过原因：新增 `JJZStatus.reject_reason`，取值优先级为记录级 `shsbyyms` → 记录级 `shsbyy` → 车辆级 `bnbzyy`，三者均空时保持为空。该字段只承载上游业务原因，不参与、也不改变状态判定结果。
- `parse_jjz_response` 在目标车辆无 `bzxx` 记录但存在车辆级 `bnbzyy` 时，仍返回 `INVALID` 状态并携带该原因。
- 推送文案：状态为 `INVALID` 且 `blztmc` 非空时，正文的状态文本改为 `blztmc` 原文（如「失败(审核不通过)」）而非枚举值 `invalid`；原因部分优先用 `reject_reason`，为空时回退到既有 `error_message`。无 `blztmc` 时完全保持现有兜底文案。
- 明确 `reject_reason` 与 `error_message` 分工：`error_message` 继续只承载系统/解析级错误，`reject_reason` 只承载上游业务原因。这是为了避免上游原因文本意外命中 `_is_system_error` 的关键词表（其中含「未配置」「配置错误」等），把用户推送误降级成只通知管理员。

## Capabilities

### New Capabilities

- `jjz-status-reporting`: 进京证记录解析结果（`JJZStatus`）如何承载上游原因字段，以及状态推送正文如何呈现状态与原因原文。

### Modified Capabilities

（无）

## Impact

- 代码：
  - `jjz_alert/service/jjz/jjz_status.py`（新增 `reject_reason` 字段与 `to_dict` 输出）
  - `jjz_alert/service/jjz/jjz_parse.py`（`parse_single_jjz_record` / `parse_jjz_response` 透传原因）
  - `jjz_alert/service/notification/push_helpers.py`（`push_jjz_status` 的 INVALID 分支文案）
  - `jjz_alert/service/jjz/jjz_utils.py`（`format_jjz_body_and_priority` 的 INVALID 分支文案）
- 测试：`tests/unit/service/test_jjz_parse.py`、`tests/unit/service/test_jjz_utils.py`、`tests/unit/service/test_push_helpers.py` 需新增审核不通过场景用例。
- 行为：审核不通过车牌的推送正文由「状态：invalid。」变为「状态：失败(审核不通过)。<原因原文>」；VALID / EXPIRED / PENDING / APPROVED_PENDING / ERROR 的推送文案不变；无原因字段的 INVALID 记录保持现有兜底文案。
- API/依赖/配置：无变化。`config.yaml` 与模板不需要改动。
- 缓存：`reject_reason` 随 `JJZStatus` 一起写入 Redis 缓存；缓存中的旧记录没有该字段，读取后表现为空，回退到现有 `error_message` 行为。
