## Why

`GET /permit` 已经能按令牌查询一辆车最新的进京证，但调用方还要另找剩余办理次数、审核不通过原因，以及这辆车今天是否限行。这三项都已经在现有进京证状态和限行服务里算过，查询接口没有把它们带出来。

## What Changes

- 成功响应在原有字段之后增加 `remaining_count`、`reject_reason`、`traffic_limited_today`。原有字段的名字和类型不变。
- `remaining_count` 来自 `JJZStatus.sycs`（车辆级剩余次数），解析为整数；空白或不能解析时为 `null`。
- `reject_reason` 来自已经解析好的 `JJZStatus.reject_reason`；没有原因时为 `null`。
- `traffic_limited_today` 复用同步到 Home Assistant 时使用的限行服务。限行查询失败或没有规则时为 `null`，进京证结果仍返回。
- 401、403、404、503 的含义不变。新字段不参与这些状态码的判定，鉴权失败或没有进京证记录时不查询限行。

## Capabilities

### New Capabilities

- `permit-query`: 已鉴权的 `GET /permit` 成功响应如何暴露剩余次数、审核原因和当日限行。

### Modified Capabilities

（无）

## Impact

- 代码：`jjz_alert/service/jjz/permit_lookup.py`、`rest_api.py`。限行服务的异步取数改为在现有 HTTP 工作线程中执行，避免查询接口堵住事件循环。
- 测试：`tests/unit/app/test_permit_api.py`、`tests/unit/service/test_permit_lookup.py`，以及限行异步取数不阻塞事件循环的用例。
- 文档：README 中该接口的成功字段说明，以及 OpenAPI `PermitResponse`。
- 配置、缓存结构和 Home Assistant 属性不变。限行查询失败时 HA 仍按既有服务结果同步，本变更只改变查询接口对外如何表示“无法判断”。
