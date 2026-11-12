## 1. 响应字段

- [x] 1.1 `to_permit_payload` 增加 `remaining_count` 与 `reject_reason`，空白和无法解析的次数为 `null`
- [x] 1.2 `PermitResponse` 与 README 写上三个新字段，原有字段保持不变

## 2. 当日限行

- [x] 2.1 成功查询进京证后调用现有 `TrafficService.check_plate_limited`
- [x] 2.2 限行失败、无规则、异常或超过 12 秒总等待时 `traffic_limited_today` 为 `null`，响应仍为 200
- [x] 2.3 401/403/404/503 不查询限行
- [x] 2.4 异步限行 HTTP 在现有工作线程中执行，不堵住事件循环

## 3. 测试

- [x] 3.1 成功载荷覆盖三个字段的有值与 `null`，包括剩余次数为 0
- [x] 3.2 401/403/404/503 的状态码与响应正文保持原样
