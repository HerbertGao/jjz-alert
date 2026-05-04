## 1. 覆盖信号计算（JJZService）

- [x] 1.1 在 `jjz_alert/service/jjz/jjz_service.py` 新增内部辅助函数 `_is_effective_on(record, day) -> bool`：解析 `valid_start` / `valid_end` 失败时返回 `False`；`blztmc` 必须包含"生效中"或"待生效"才计入
- [x] 1.2 修改 `_query_multiple_status`：遍历 `triples` 时对今天与明天分别调用 `_is_effective_on`，得到 `today_covered` / `tomorrow_covered`
- [x] 1.3 把两个布尔挂入 `plate_renew_contexts[plate]` 元组，新签名为 `(response_data, account, renew_status, today_covered, tomorrow_covered)`
- [x] 1.4 更新 `get_multiple_status_with_context` 的返回类型注解
- [x] 1.5 新建 `tests/unit/service/test_jjz_service_coverage.py`（或扩展既有 jjz_service 测试）：覆盖以下用例
  - 单条记录 `blztmc="生效中"` + 有效期含今天 → today_cov=Y、tomorrow_cov 视 valid_end 而定
  - 单条记录 `blztmc="待生效"` + valid_start=明天 → today_cov=N, tomorrow_cov=Y
  - 两条记录（六环内已失效 + 六环外生效中），互斥规则下 today_cov 由生效那条决定
  - `valid_start` 解析失败 → 该记录不计 cov
  - 全部记录 `blztmc="已失效"` → today_cov=N, tomorrow_cov=N

## 2. 决策器换轴（renew_decider）

- [x] 2.1 修改 `jjz_alert/service/jjz/renew_decider.py` 的 `decide(...)` 签名为 keyword-only：`decide(*, plate_config, outer_renew_status, today_covered, tomorrow_covered)`
- [x] 2.2 删去对 `outer_renew_status.valid_end` / `JJZStatusEnum.EXPIRED` 的旧分支
- [x] 2.3 实现新决策矩阵（按 design D3）：
  - `auto_renew` 未启用 → SKIP
  - `outer_renew_status is None` → SKIP（无六环外记录）
  - `sfyecbzxx=True` → PENDING
  - `today_cov=Y` 与 `tomorrow_cov` / `elzsfkb` 组合 → SKIP / RENEW_TOMORROW
  - `today_cov=N` 与 `elzsfkb` / `tomorrow_cov` 组合 → RENEW_TODAY / SKIP / NOT_AVAILABLE
- [x] 2.4 重写 `tests/unit/service/test_renew_decider.py`，覆盖矩阵全集：
  - **核心 9 条**：决策树每条叶子各一个用例
  - **边界 5 条**：auto_renew=None、auto_renew.enabled=False、outer_renew_status=None、sfyecbzxx=True 优先级（同时 elzsfkb=False/today_cov=N 应该仍返回 PENDING）、`status=INVALID` 不再单独处理（合并到无 cov 路径）

## 3. 派发器与执行器透传 + useful 过滤

- [x] 3.1 修改 `jjz_alert/service/jjz/renew_trigger.py` 的 `schedule_renew(...)` 签名增加 `today_covered: bool` 与 `tomorrow_covered: bool`，原样透传
- [x] 3.2 修改 `jjz_alert/service/jjz/auto_renew_service.py` 的 `RenewResult` dataclass：新增 `skipped: bool = False`
- [x] 3.3 修改 `execute_renew(...)` 签名增加 `today_covered` / `tomorrow_covered`
- [x] 3.4 在 `execute_renew` 拿到 `jjrqs` 后增加 `_filter_useful(jjrqs, today_covered, tomorrow_covered, today, tomorrow)`：保留 `d==today AND not today_cov`、`d==tomorrow AND not tomorrow_cov`、`d>tomorrow AND not tomorrow_cov`
- [x] 3.5 处理 useful 过滤后的三态（注意：useful=[] 时还需要用 `_has_parseable_date` 区分两种语义）：
  - `jjrqs=[]` → 现有"无可选进京日期"告警，**不写**防重 key
  - `jjrqs` 非空但 useful=[] 且 `_has_parseable_date=False` → 视为服务端数据异常，告警 `"服务端返回的进京日期格式异常"`，**不写**防重 key（`step="check_handle"`, `skipped=False`）
  - `jjrqs` 非空但 useful=[] 且 `_has_parseable_date=True` → 静默 SKIP，写当日防重 key（`skipped=True`）
  - `useful` 非空 → 取 `useful[0]` 作 `jjrq` 提交
- [x] 3.6 修改 `push_renew_result(...)`：入口处 `if result.skipped: 记 INFO 日志后 return`，跳过推送

## 4. 调用点同步

- [x] 4.1 修改 `jjz_alert/service/notification/jjz_push_service.py` 的 `process_single_plate`：解包新元组（5 元素），把 `today_covered` / `tomorrow_covered` 传给 `decide(...)` 与 `schedule_renew(...)`
- [x] 4.2 修改 `jjz_alert/service/jjz/renew_workflow.py` 的 `run_renew_only_workflow`：同上调整
- [x] 4.3 全局搜索 `decide(plate_config, jjz_status)` / `schedule_renew(...)` 旧调用形式，确认无残留

## 5. 测试

- [x] 5.1 扩展 `tests/unit/service/test_auto_renew.py`：新增 4 条 jjrqs 分支用例
  - jjrqs=["今天"] + today_cov=N → 提交今天，写防重 key
  - jjrqs=["明天"] + today_cov=N + tomorrow_cov=Y → useful=[]，skipped=True，写防重 key，无推送
  - jjrqs=["后天"] + today_cov=N + tomorrow_cov=N → useful=["后天"]，提交后天
  - jjrqs=[] → 旧告警路径，不写防重 key
  - jjrqs=[""] / ["not-a-date"] 全部不可解析 → 告警路径，不写防重 key
  - jjrqs=["not-a-date", 明天] + tomorrow_cov=Y → 混合输入，因有可解析日期但被本地覆盖，仍走静默 SKIP
- [x] 5.2 扩展 `tests/unit/service/test_renew_workflow.py`：验证 renew_only 工作流在 NOT_AVAILABLE / SKIP（含静默 SKIP）/ RENEW_* 各分支下的派发与推送行为符合新规则
- [x] 5.3 运行 `pytest tests/unit/service/test_renew_decider.py tests/unit/service/test_auto_renew.py tests/unit/service/test_renew_workflow.py` 全绿
- [x] 5.4 运行完整 `pytest` 确认无回归

## 6. 端到端验证

- [x] 6.1 用 mock stateList 构造津A86X64 复现场景（六环内生效中 + 六环外失效 + elzsfkb=False），跑 push_workflow，确认日志记录 `[renew] decision plate=... -> skip today_cov=True tomorrow_cov=True elzsfkb=False ...` 且无 NOT_AVAILABLE 推送
- [x] 6.2 mock 构造"六环外今日到期 + 无六环内"场景，跑 push_workflow，确认派发 RENEW_TOMORROW 并最终调用 insertApplyRecord
- [x] 6.3 mock 构造"checkHandle 返回 ['明天'] + tomorrow_cov=Y" 场景，确认 useful 过滤后静默 skipped=True 且写入防重 key
- [x] 6.4 mock 构造"checkHandle 返回 [] " 场景，确认推送"当前无可选进京日期"告警且 **不**写防重 key

## 7. 文档与归档

- [x] 7.1 README 与 config.yaml.example 检查（应无需修改，本变更不引入配置项）
- [x] 7.2 运行 `openspec-cn validate renew-decider-by-coverage` 确认提案结构合法
- [ ] 7.3 完成实施后调用 `/opsx:archive` 归档变更
