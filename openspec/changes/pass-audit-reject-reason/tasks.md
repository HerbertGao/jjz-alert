## 1. 数据模型

- [x] 1.1 `jjz_alert/service/jjz/jjz_status.py`：为 `JJZStatus` 新增可选字段 `reject_reason: Optional[str] = None`（注释说明它只承载上游业务原因，与 `error_message` 分工），并在 `to_dict()` 中输出 `reject_reason`

## 2. 解析层透传

- [x] 2.1 `jjz_alert/service/jjz/jjz_parse.py`：新增模块内取值函数 `_reject_reason(record, vehicle)`，按 `record.get("shsbyyms")` → `record.get("shsbyy")` → `vehicle.get("bnbzyy")` 顺序返回第一个非空值（去空白后为空视为缺失）
- [x] 2.2 `parse_single_jjz_record`：以 `reject_reason=` 传入该值，`status_resolver` 调用与其余字段保持不变
- [x] 2.3 `parse_jjz_response`：主流程（有 `bzxx`）同样传递 `reject_reason`；`bzxx` 为空的分支通过 `_reject_reason({}, target_vehicle)` 携带车辆级原因，`bnbzyy` 为空时维持现状（`error_message="未找到进京证记录"`，`reject_reason=None`）

## 3. 推送文案

- [x] 3.1 `jjz_alert/service/jjz/jjz_utils.py`：新增共享取值函数 `resolve_error_display(jjz_data) -> (状态文本, 原因文本)`，即 `(jjz_data.get("blztmc") or jjz_data.get("status", "unknown"), jjz_data.get("reject_reason") or jjz_data.get("error_message", ""))`
- [x] 3.2 `jjz_alert/service/notification/push_helpers.py`：`push_jjz_status` 的 `else` 分支改用该函数取值后再调用 `format_jjz_error_content`；`_is_system_error` 判定仍只读取 `error_message`
- [x] 3.3 `jjz_alert/service/jjz/jjz_utils.py`：`format_jjz_body_and_priority` 的 `else` 分支同样改用该函数
- [x] 3.4 确认 `format_jjz_error_content` 与消息模板签名不变，`VALID` / `EXPIRED` / `PENDING` / `APPROVED_PENDING` 分支不动

## 4. 测试

- [x] 4.1 `tests/unit/service/test_jjz_parse.py`：新增 `TestRejectReasonPassthrough` 覆盖记录级 `shsbyyms` 优先、`shsbyyms` 空回退 `shsbyy`、两者皆空回退车辆级 `bnbzyy`、三者皆空时 `reject_reason is None` 且 `status` 仍为 `invalid`
- [x] 4.2 `tests/unit/service/test_jjz_parse.py`：新增 `test_parse_jjz_response_no_bzxx_with_vehicle_reason`，覆盖 `bzxx` 为空但 `bnbzyy` 非空时返回 `INVALID` + 原因原文
- [x] 4.3 `tests/unit/service/test_jjz_utils.py`：新增 `TestResolveErrorDisplay` 与 `TestFormatJjzBodyAndPriorityRejectReason`，用真实模板断言最终正文含「失败(审核不通过)」与原因原文、不含 `invalid`；并断言 `blztmc` 为空时仍输出 `status` 与 `error_message`
- [x] 4.4 `tests/unit/service/test_push_helpers.py`：新增 `test_push_jjz_status_reject_reason_not_system_error`，覆盖 `reject_reason` 含「配置错误」时仍走用户推送、未调用管理员告警
- [x] 4.5 回归既有 `INVALID` / 无记录场景断言：既有用例通过 mock `template_manager` 或断言 `error_message`，不受文案变更影响，无需修改期望值

## 5. 验证与交付

- [x] 5.1 `.venv/bin/python -m pytest tests/unit/ -q` 全绿（893 passed）
- [x] 5.2 `tox -e format` 等价命令 `.tox/format/bin/black .` 输出 `101 files left unchanged`，无格式化 diff
- [ ] 5.3 提 PR：标题 `feat(jjz): 透传并推送进京证审核未通过原因`，描述关闭 issue #105 并链接本变更目录
- [ ] 5.4 PR 合并后运行 `openspec-cn archive pass-audit-reject-reason` 归档到 `openspec/specs/jjz-status-reporting/spec.md`
