## 上下文

系统当前通过 APScheduler 的 `BlockingScheduler` 在固定时间点执行 `main()` 完成进京证状态查询和推送。自动续办需要在此调度体系中增加一条独立的任务链路：判断是否需要续办 → 随机延迟 → 执行续办 API 调用链 → 推送结果通知。

进京证 API 基于 `jjz.jtgl.beijing.gov.cn:2443`，使用 `curl_cffi` 模拟 Chrome TLS 指纹。续办涉及 6 个 API 端点，所有请求复用同一 Authorization token 和相同的 HTTP 基础设施。

## 目标 / 非目标

**目标：**
- 六环外进京证到期前一天自动提交续办申请
- 续办触发时间在用户可配置的时间窗口内随机选择，避免固定模式
- 续办前执行全部前置校验（车辆校验、驾驶人校验、日期获取等），任何校验失败则中断并通知
- 续办结果（成功/失败）通过该车牌已配置的通知渠道推送
- 续办配置在 `config.yaml` 中声明，支持按车牌独立开关

**非目标：**
- 不支持六环内进京证自动续办（有次数限制，需用户手动决策）
- 不实现自动登录/Token 刷新（Token 失效时通知用户手动更新）
- 不实现续办申请的取消功能
- 不处理审核被拒后的自动重新申请

## 决策

### 1. 续办调度：独立定时任务 + asyncio 随机延迟

**选择**：在 APScheduler 中新增一个固定时间点的 cron job（如每天 00:00），任务执行时先计算随机延迟（在配置的时间窗口内），通过 `asyncio.sleep` 等待后再执行续办逻辑。

**替代方案**：
- 在每次 `main()` 执行时顺带检查续办 → 拒绝：`main()` 一天执行多次，会导致重复判断和不必要的复杂度
- 使用 APScheduler 的 `DateTrigger` 动态创建一次性任务 → 拒绝：需要持久化调度状态，且 `BlockingScheduler` 不方便动态添加任务

**理由**：每天固定触发一次续办检查任务，通过 `asyncio.sleep(random_seconds)` 实现随机化，简单可靠，无需修改现有调度架构。

### 2. 续办服务：新建 `auto_renew_service.py`

**选择**：在 `jjz_alert/service/jjz/` 下新建 `auto_renew_service.py`，封装完整的续办 API 调用链。

**理由**：续办逻辑与查询逻辑职责不同，独立模块便于测试和维护。复用现有的 `http_post`、`jjz_parse` 和通知基础设施。

### 3. stateList 额外字段：扩展解析而非新建数据结构

**选择**：在 `parse_all_jjz_records` 的返回结果中附带续办所需的车辆级字段（`vId`, `hpzl`, `elzsfkb`, `cllx`），通过在 `JJZStatus` 上添加可选字段或返回辅助数据结构。

**替代方案**：新建独立的 `VehicleInfo` 数据类 → 拒绝：增加复杂度，这些字段与进京证状态紧密关联

**理由**：续办判断与查询共享同一个 `stateList` 调用，扩展现有数据结构最自然。

### 4. 续办配置：`plates[].auto_renew` 嵌套配置块

**选择**：在 `PlateConfig` 中嵌套 `AutoRenewConfig`，包含续办所需的全部固定信息。

```yaml
plates:
  - plate: "津B15F93"
    auto_renew:
      enabled: true
      purpose: "03"            # 进京目的代码
      purpose_name: "探亲访友"
      destination:
        area: "顺义区"
        area_code: "010"
        address: "仁和街道顺和路64号顺和花园"
        lng: "116.666824"
        lat: "40.085226"
      accommodation:
        enabled: true
        address: "顺和花园"
        lng: "116.666824"
        lat: "40.085226"
      apply_location:
        lng: "116.4"
        lat: "39.9"
```

全局续办时间窗口配置放在 `global` 下：

```yaml
global:
  auto_renew:
    time_window_start: "00:00"  # 随机窗口起始
    time_window_end: "06:00"    # 随机窗口结束
```

**理由**：续办的目的地/目的等信息是车牌级别的（不同车可能去不同地方），而时间窗口是全局策略。

### 5. 防重复提交：基于 stateList 的 ecbzxx 判断

**选择**：续办前调用 `stateList`，检查目标车辆的 `sfyecbzxx` 字段或 `ecbzxx` 数组是否非空，若已有待审记录则跳过。

**理由**：这是 API 本身提供的状态信息，最可靠。同时在 Redis 中记录当天已提交续办的车牌作为二级保护。

### 6. 续办 API 调用链：保守策略，全部校验步骤

**选择**：依次调用全部 6 个 API（applyVehicleCheck → getJsrxx → applyCheckNum → checkHandle → checkInputRoadInfo → insertApplyRecord），任何步骤失败即中断。

**替代方案**：跳过校验步骤，直接调用 insertApplyRecord → 拒绝：无法提前发现车辆被限制等问题

**理由**：多几个请求的成本极低（均为轻量 JSON 接口），但能在提交前发现各类异常。

## 风险 / 权衡

- **Token 失效** → 续办失败时推送告警通知，明确提示用户更新 Token。在通知消息中区分"Token 失效"和"其他错误"。
- **API 结构变更** → 每个校验步骤检查 `code == 200`，非 200 时记录完整响应体用于排查。
- **重复提交** → 双重保护：stateList 的 `sfyecbzxx` + Redis 当日提交记录。
- **随机延迟过长导致窗口溢出** → 在 `asyncio.sleep` 前计算确保延迟不超过窗口结束时间。
- **固定地址模式** → 从 HAR 分析看，官方 App 用户也会复用历史地址，属正常行为。随机时间已提供行为多样性。
- **六环外办证被临时限制** → `checkHandle` 返回空 `jjrqs` 或 `elzsfkb=false` 时中断并通知用户。
