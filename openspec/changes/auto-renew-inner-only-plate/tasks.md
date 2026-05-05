## 1. 代码改动

- [x] 1.1 修改 `jjz_alert/service/jjz/jjz_service.py:_query_multiple_status`：删除 `outer_triples` 中间过滤，将 `renew_record/renew_response/renew_account` 直接复用 `latest_record/latest_response/latest_account`（即 `max(triples, key=apply_time)`）；保留 `today_covered`/`tomorrow_covered`/`today` 写入；非 ERROR 才缓存逻辑保留。
- [x] 1.2 修改 `jjz_alert/service/jjz/renew_decider.py`：更新模块顶部 docstring 与 `decide` 内 `outer_renew_status is None → SKIP` 分支的注释，将"无六环外历史记录"改为"上下文缺失"；逻辑分支本身保持不变。
- [x] 1.3 修改 `jjz_alert/service/jjz/renew_workflow.py:run_renew_only_workflow`：把 `ctx is None` 时的 `logger.debug` 改为 `logger.info`，文案"缺少续办上下文，跳过"保留。
- [x] 1.4 检查 `jjz_alert/service/jjz/jjz_push_service.py:process_single_plate` 是否存在类似 `ctx is None` 的 DEBUG 跳过分支，如有同步提级到 INFO；如无则跳过此项。（实际位于 `service/notification/jjz_push_service.py`：原本无日志，补充了一条 INFO 日志，仅当车牌启用了 auto_renew 才打，避免噪音；注释同步更新。）
- [x] 1.5 在 `jjz_alert/service/jjz/jjz_utils.py` 新增 `normalize_response_parens(text)` 字符串工具：把全角 `（` / `）` 替换为半角 `(` / `)`；normalize 时机推到 parse 层（`parse_single_jjz_record` / `parse_jjz_response` 在写入 `JJZStatus` 前对 `jjzzlmc` / `blztmc` 调用），raw response 完全透传，不影响 `insertApplyRecord` 的 metadata 字段（`elzqyms` / `ylzqyms` / `elzmc` / `ylzmc`，由 `extract_renew_metadata` 取出后原样回传）。配套加单元测试覆盖字符串规范化、空值、parse 层规范化与 `check_jjz_status` 透传边界护栏。

## 2. 测试

- [x] 2.1 修改 `tests/unit/service/test_jjz_service.py`：把 `test_get_multiple_status_with_context_no_outer`（或同名等价测试）从"断言无六环外车牌不在 plate_contexts"改为"断言仍写入 plate_contexts，且 renew_status 是该车牌全部记录中 apply_time 最新一条"。
- [x] 2.2 在 `tests/unit/service/test_jjz_service.py` 新增 `test_get_multiple_status_with_context_inner_only_renew_record`：构造仅有六环内记录的响应，断言 plate_contexts 写入、renew_status.jjzzlmc 含"六环内"、`vId`/`elzsfkb`/`ylzsfkb`/`cllx` 字段从 vehicle 层正确填充。
- [x] 2.3 在 `tests/unit/service/test_renew_decider.py` 新增 `test_decide_inner_only_record_renew_today`：传入 `outer_renew_status` 为六环内记录（`jjzzlmc="进京证（六环内）"`，但 `elzsfkb=True`、`sfyecbzxx=False`），`today_covered=False` → 期望 `RENEW_TODAY`。
- [x] 2.4 在 `tests/unit/service/test_renew_workflow.py` 新增/修改 case 覆盖"仅有六环内记录车牌进入 run_renew_only_workflow 时正常派发"。
- [x] 2.5 全量运行 `pytest tests/unit/service/` 确认 873 测试（或更多）全绿；记录新覆盖率不低于现状（96%）。（实际：`tests/unit/service/` 497 全绿；`tests/unit/` 全套 874 全绿，超过基线 873。）

## 3. Codex Review 循环

- [x] 3.1 编码与测试（章节 1、2）完成后，调用 `/codex:rescue` 对本次改动做 review，输入范围聚焦在 `jjz_alert/service/jjz/jjz_service.py`、`renew_decider.py`、`renew_workflow.py`、`jjz_push_service.py` 以及对应测试文件。
- [x] 3.2 解析 codex review 反馈：若返回 clear（无需修复），跳到章节 4；若指出问题，整理为待修清单。（第 1 轮反馈：Critical CLEAR；Major 1 项：`process_single_plate` 主路径未覆盖；Minor 2 项：①`get_multiple_status_with_context` docstring 过时；②新增 INFO 日志在锁外可能重复打印——后者可接受不动。）
- [x] 3.3 按问题性质指派合适的 subagent 执行修复（实现类用 general-purpose 或 code-simplifier；定位类用 Explore；规划类用 Plan）；修复后先本地跑一遍 `pytest tests/unit/service/` 自检。（修复内容：① Major - 新增 `tests/unit/service/test_jjz_push_service.py` 覆盖 `execute_push_workflow` 的 process_single_plate 主路径派发；② Minor 1 - 修正 `get_multiple_status_with_context` docstring；③ Minor 2 - 评估为可接受日志噪音不动。tests/unit/ 882 全绿。）
- [x] 3.4 修复完成后回到 3.1 重新交给 `/codex:rescue` review；如此循环直到 codex 明确给出 "clear / 无需进一步修改" 的结论才认为本次实现交付完成。（第 2 轮反馈：Critical CLEAR、Major CLEAR；3 条 Minor 注释/文档/异常路径一致性已顺手清理；codex 明确判定 "CLEAR，无 merge-blocking 问题"。）
- [ ] 3.5 在 PR 描述里附上最终一轮 codex review 的链接或摘要，作为审计留痕。

## 4. 验证与文档

- [x] 4.1 本地用 `cli_tools.py`（如有 dry-run 入口）或 mock stateList 响应（仅含六环内）跑一次 `run_renew_only_workflow`，确认日志出现 `[renew] decision plate=<plate> -> ...`（占位符代表测试用车牌号）。（实测：在 `test_jjz_push_service.py` 与 `test_renew_workflow.py::test_run_renew_only_workflow_dispatches_for_inner_only_plate` 两条 e2e 测试中加 `--log-cli-level=INFO` 已实际看到 `[renew] decision plate=京A12345 -> renew_today` 与 `[renew_only] decision plate=京A12345 -> renew_today` 输出，等价验证完成。）
- [ ] 4.2 部署 mac-mini 后观察次日 `06:00`/`08:00` remind 触发，从 `docker logs jjz-alert-jjz-alert-1` 确认目标车牌（仅持有六环内记录的那一辆）进入决策日志；按车辆资格情况验证：进入派发或收到 NOT_AVAILABLE 通知。
- [ ] 4.3 提 PR：标题 `fix(auto-renew): 放宽续办上下文限制，允许仅有六环内记录的车牌进入决策`；描述链接到 openspec 变更目录。
- [ ] 4.4 PR 合并并验证生效后，运行 `openspec-cn archive auto-renew-inner-only-plate`（或 `/opsx:archive`）将变更归档到 `openspec/specs/auto-renew/spec.md`。
