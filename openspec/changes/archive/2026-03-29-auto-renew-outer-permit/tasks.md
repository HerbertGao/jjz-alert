## 1. 配置模型与校验

- [x] 1.1 在 `config_models.py` 中新增 `AutoRenewDestinationConfig`、`AutoRenewAccommodationConfig`、`AutoRenewApplyLocationConfig`、`AutoRenewConfig` 数据类，并在 `PlateConfig` 中添加可选的 `auto_renew` 字段
- [x] 1.2 在 `config_models.py` 中新增 `GlobalAutoRenewConfig` 数据类（`time_window_start`、`time_window_end`），并在 `GlobalConfig` 中添加可选的 `auto_renew` 字段
- [x] 1.3 在 `config.py` 的配置加载逻辑中解析 `plates[].auto_renew` 和 `global.auto_renew` 配置段
- [x] 1.4 在 `validation.py` 中新增续办配置校验规则：启用时必需字段检查、住宿字段检查、时间窗口合法性检查
- [x] 1.5 更新 `config.yaml.example`，添加 `auto_renew` 配置示例和注释说明

## 2. stateList 响应扩展解析

- [x] 2.1 在 `jjz_parse.py` 的 `parse_all_jjz_records` 中，从 `vehicle` 级别提取 `vId`、`hpzl`、`elzsfkb`、`ylzsfkb`、`cllx` 并传入记录构建器
- [x] 2.2 在 `JJZStatus` 数据类中新增可选字段：`vId`、`hpzl`、`elzsfkb`、`ylzsfkb`、`cllx`、`sfyecbzxx`
- [x] 2.3 扩展 `parse_all_jjz_records` 返回值或新增辅助函数，提取 `data` 顶层的 `elzqyms`、`ylzqyms`、`elzmc`、`ylzmc` 供续办使用

## 3. 续办核心服务

- [x] 3.1 新建 `jjz_alert/service/jjz/auto_renew_service.py`，实现 `AutoRenewService` 类框架，包含初始化、配置加载和日志
- [x] 3.2 实现续办触发判断方法 `should_renew(plate, jjz_status) -> bool`：检查剩余天数、ecbzxx 状态、elzsfkb、Redis 当日记录
- [x] 3.3 实现 API 调用链的各步骤封装方法：`_vehicle_check`、`_get_driver_info`、`_driver_check`、`_check_handle`、`_check_road_info`
- [x] 3.4 实现 `_build_apply_request` 方法：从 stateList 响应、getJsrxx 响应、checkHandle 响应和用户配置中组装 `insertApplyRecord` 请求体
- [x] 3.5 实现 `_submit_apply` 方法：调用 `insertApplyRecord` 并处理响应
- [x] 3.6 实现主入口方法 `execute_renew(plate) -> RenewResult`：串联判断 → 调用链 → 结果，包含完整错误处理和 Redis 防重复记录

## 4. 随机时间调度

- [x] 4.1 实现 `_calculate_random_delay` 方法：根据全局 `time_window_start/end` 配置计算随机等待秒数
- [x] 4.2 实现 `run_auto_renew_check` 异步入口函数：随机延迟 → 加载配置 → 遍历启用续办的车牌 → 调用 `execute_renew`
- [x] 4.3 在 `main.py` 的 `schedule_jobs` 中注册续办定时任务：每天 00:00 触发 `run_auto_renew_check`

## 5. 续办结果通知

- [x] 5.1 在 `message_templates.py` 中新增续办相关消息模板：续办成功模板、续办失败模板、Token 失效模板
- [x] 5.2 在 `config_models.py` 的 `MessageTemplateConfig` 中新增续办模板的可选自定义字段
- [x] 5.3 在 `auto_renew_service.py` 中实现续办结果推送方法，复用车牌已配置的通知渠道

## 6. 测试

- [x] 6.1 为配置模型和校验逻辑编写单元测试：合法配置、缺失字段、无效时间窗口等场景
- [x] 6.2 为续办触发判断逻辑编写单元测试：明天到期、已过期、有待审记录、不可办理、有效期充足等场景
- [x] 6.3 为 API 调用链编写单元测试（mock HTTP 请求）：全部成功、中间步骤失败、无可选日期等场景
- [x] 6.4 为请求体组装逻辑编写单元测试：验证各字段来源正确性
- [x] 6.5 为随机延迟计算编写单元测试：默认窗口、自定义窗口、边界情况
