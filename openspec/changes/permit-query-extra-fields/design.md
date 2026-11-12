## 上下文

`GET /permit` 把 `JJZService.get_jjz_status` 的结果经 `to_permit_payload` 映射成公开字段。`JJZStatus.sycs` 与 `JJZStatus.reject_reason` 已经在解析时写好，但没有进入这个映射。

Home Assistant 同步用 `TrafficService.check_plate_limited` 得到 `PlateTrafficStatus`，再由 `HAPlateDevice.from_jjz_and_traffic_data` 读取 `is_limited`。查询失败时该对象仍把 `is_limited` 写成 `False`，并设置 `error_message`、留空 `rule`。HA 按这个布尔值展示。查询接口如果照抄，会把“没查到”说成“今日不限行”。

进京证上游请求已经通过有上限的 HTTP 工作线程执行。限行主接口原先在异步函数里直接调用同步 `http_get`，从查询接口调用时会堵住事件循环。

## 目标 / 非目标

目标：成功响应多返回剩余次数、审核原因和当日是否限行；原有字段与 401/403/404/503 保持不变；限行查不准时字段为 `null` 且不失败整次请求；限行 HTTP 不占用事件循环。

非目标：不新增限行数据源，不改变限行规则解析，不改变 HA 在查询失败时仍发布 `is_limited=false` 的行为，不调整令牌或车牌范围，不发布新版本。

## 决策

**1. 剩余次数和审核原因只在 `to_permit_payload` 里映射。**

`sycs` 是车辆级上游字段，现有类型是字符串。公开字段用整数，和 `days_remaining` 一致；`0` 保留，空白、布尔值和非数字为 `null`。`reject_reason` 已经按记录级 `shsbyyms` / `shsbyy`、再车辆级 `bnbzyy` 解析过，这里只把空白收成 `null`。

**2. 当日限行复用 `TrafficService.check_plate_limited`。**

有规则且没有 `error_message` 时返回 `is_limited`。没有状态、没有规则，或带有错误信息时返回 `null`。服务内部抛出的异常同样变成 `null`，响应仍是 200。限行只在进京证记录已经成功映射之后查询，因此 401、403、404、503 不会因为限行而改变。

**3. 异步限行取数走现有 HTTP 工作线程。**

生产路径的主请求使用与进京证 POST 相同的模式：单次阻塞 IO 进有上限的工作线程，重试等待留在事件循环。测试若替换了同步 `http_get`，异步路径继续调用那个替身。同步兼容接口仍在调用线程里执行，不进入 FastAPI 请求。

## 风险

- 调用方若把缺失的 `traffic_limited_today` 当成 `false`，会重新得到旧的误判。字段保持为 JSON `null`，并在说明里写明无法判断。
- 限行备用请求整段进入工作线程。工作线程数量仍是现有上限，请求在队列里等待，不回到事件循环上阻塞。
