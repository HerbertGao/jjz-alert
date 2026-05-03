## 1. 配置层改造

- [x] 1.1 修改 `jjz_alert/config/config_models.py` 中 `GlobalAutoRenewConfig`：删除 `time_window_start` / `time_window_end`；新增 `min_delay_seconds: int = 30` 与 `max_delay_seconds: int = 180`
- [x] 1.2 修改 `jjz_alert/config/config.py` 加载逻辑：读取新字段；检测到旧字段时输出 WARN 日志（"已废弃，将被忽略"）并跳过赋值
- [x] 1.3 修改 `jjz_alert/config/validation.py`：删除 `_validate_auto_renew_time_window`；新增 `_validate_auto_renew_delay`（校验 `min >= 0` 且 `min <= max`）
- [x] 1.4 更新 `config.yaml.example`：移除 `time_window_*` 注释/示例，新增 `min_delay_seconds` / `max_delay_seconds` 注释/示例

## 2. 决策器实现

- [x] 2.1 新建 `jjz_alert/service/jjz/renew_decider.py`：定义 `RenewDecision(Enum)`（`SKIP` / `RENEW_TODAY` / `RENEW_TOMORROW` / `PENDING` / `NOT_AVAILABLE`）
- [x] 2.2 在同文件实现 `decide(plate_config: PlateConfig, jjz_status: JJZStatus) -> RenewDecision`，按优先级 `PENDING > NOT_AVAILABLE > RENEW_* > SKIP` 实现决策矩阵
- [x] 2.3 新建 `tests/test_renew_decider.py`，覆盖所有决策分支：今日有效+明日有效、今日有效+明日到期、今日已过期、`status=INVALID`、`sfyecbzxx=True`、`elzsfkb=False`、`auto_renew.enabled=False`、`auto_renew=None`

## 3. 派发器实现

- [x] 3.1 新建 `jjz_alert/service/jjz/renew_trigger.py`：模块级 `RENEW_GLOBAL_SEMAPHORE = asyncio.Semaphore(1)`
- [x] 3.2 在同文件实现 `async def schedule_renew(plate_config, jjz_status, response_data, accounts, decision, min_delay, max_delay)`：
  - random.randint(min_delay, max_delay) → asyncio.sleep
  - async with RENEW_GLOBAL_SEMAPHORE
  - 检查 Redis 当日防重 key，已存在则跳过并记录日志
  - 调用 `auto_renew_service.execute_renew(...)`
  - 调用 `auto_renew_service.push_renew_result(...)` 推送结果
- [x] 3.3 在 `tests/test_auto_renew.py` 新增 `schedule_renew` 集成测试：mock `asyncio.sleep` 和 `execute_renew`，验证信号量在多协程并发时串行执行

## 4. push_workflow 接入

- [x] 4.1 修改 `JJZService.get_multiple_status_optimized()` 或新增配套方法，使调用方能拿到原始 `response_data` 与 `accounts`（最简实现：返回元组或额外字段）
- [x] 4.2 修改 `jjz_alert/service/notification/jjz_push_service.py` 的 `process_single_plate`：
  - 在拿到 `jjz_status` 后调用 `decide(plate_config, jjz_status)`
  - 决策为 `RENEW_TODAY` / `RENEW_TOMORROW` 时：`asyncio.create_task(schedule_renew(...))`，并把 `push_result` 设为 `{"success": True, "skipped": "renew_dispatched"}`，跳过原有 `push_jjz_reminder` 调用
  - 决策为 `NOT_AVAILABLE` 时：保留现有"六环外不可办"告警逻辑（如果还没有，参照 `auto_renew_service.run_auto_renew_check` 中的告警代码迁移过来）
  - 决策为 `PENDING` / `SKIP` 时：走原有正常推送分支
- [x] 4.3 在 `process_single_plate` 内通过 `app_config.global_config.auto_renew` 读取 `min_delay_seconds` / `max_delay_seconds` 并传给 `schedule_renew`

## 5. 删除遗留代码

- [x] 5.1 删除 `jjz_alert/service/jjz/auto_renew_service.py` 中的 `run_auto_renew_check()` 函数及其全部依赖
- [x] 5.2 删除 `auto_renew_service.py` 中的 `should_renew()` 函数（被 `decide` 替代）
- [x] 5.3 删除 `auto_renew_service.py` 中的 `calculate_random_delay()` 静态方法
- [x] 5.4 修改 `main.py`：删除自动续办 cron 注册分支（`if renew_plates:` 块及 `async_renew_wrapper`）
- [x] 5.5 修改 `main.py`：调整 `has_auto_renew` 启动判断——当只有 auto_renew 启用、无 remind 时，不再单独启动 cron；保留对"无 remind 且无 auto_renew"时执行一次 `main()` 的兜底
- [x] 5.6 删除 `tests/test_auto_renew.py` 中针对 `should_renew` / `run_auto_renew_check` / `calculate_random_delay` 的测试用例
- [x] 5.7 全局搜索 `time_window_start` / `time_window_end` / `run_auto_renew_check` / `should_renew` 的残留引用，确认无悬挂

## 6. 测试与验证

- [x] 6.1 运行 `pytest tests/test_renew_decider.py` 全绿
- [x] 6.2 运行 `pytest tests/test_auto_renew.py` 全绿
- [x] 6.3 运行 `pytest tests/test_config.py`（如存在）覆盖新配置字段
- [x] 6.4 运行完整 `pytest` 确认无回归
- [x] 6.5 本地用真实/mock 配置启动 main.py，观察日志是否输出："已添加自动续办派发"或"决策器命中 RENEW_*"等结构化日志
- [x] 6.6 用伪造的 stateList 响应触发 push_workflow，验证场景①（明日缺）与场景②（今日缺）都能派发并完成 mock 续办，并观察通知抑制行为正确
- [x] 6.7 验证旧字段（`time_window_start`）写在 yaml 中时启动会输出 WARN 但不挂

## 7. 文档与归档

- [x] 7.1 更新 README.md（如有提及自动续办触发机制的章节）— README 未涉及，无需修改
- [x] 7.2 运行 `openspec-cn validate auto-renew-event-driven` 确认提案结构合法
- [ ] 7.3 完成实施后调用 `/opsx:archive` 归档变更
