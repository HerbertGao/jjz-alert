## Why

当前限行服务依赖的北京交管 JSON 接口已返回 502，导致缓存失效后无法获取尾号规则。北京交管官网详情页仍正常提供轮换表，因此需要把该页面作为 API 不可用时的官方备用来源，避免限行提醒中断。

## What Changes

- 新增官网轮换表备用来源，使用北京交管详情页 HTML 提取尾号轮换规则。
- 解析页面中的日期区间、工作日尾号映射和节假日覆盖规则，生成现有 `TrafficRule` 数据。
- 旧 JSON API 失败或返回空规则时切换到官网页面来源。
- 同时覆盖异步主流程和同步兼容流程，并复用现有 Redis/内存缓存。
- 标记备用来源及最终数据来源，便于服务状态和日志识别。
- 不新增第三方 HTML 解析依赖或用户配置项。

## Capabilities

### New Capabilities

- `traffic-rule-source`: 从北京交管官网轮换表提取并提供尾号限行规则，在主 API 不可用时作为降级来源。

### Modified Capabilities

无。

## Impact

- 影响 `jjz_alert/service/traffic/traffic_service.py` 的异步获取、同步兼容获取和来源标记。
- 新增官网 HTML 解析相关单元测试及主 API 失败时的降级测试。
- 不改变对外 REST 接口和现有缓存键格式。
- 不新增运行时依赖、配置项或外部服务。
