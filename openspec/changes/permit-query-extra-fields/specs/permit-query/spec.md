## ADDED Requirements

### Requirement: 成功响应包含剩余次数与审核原因

已鉴权且找到进京证记录时，系统 MUST 在原有字段之外返回 `remaining_count` 与 `reject_reason`。`remaining_count` MUST 来自该状态已保存的车辆级剩余次数，并且 MUST 是整数或 `null`。`0` MUST 保留。空白、布尔值或不能按整数解析的值 MUST 为 `null`。`reject_reason` MUST 来自该状态已保存的审核不通过原因；没有原因或只有空白时 MUST 为 `null`。原有字段的名字和类型 MUST 保持不变。

#### Scenario: 有剩余次数且没有审核原因

- **WHEN** 进京证查询成功，车辆级剩余次数可解析为整数，且审核原因为空
- **THEN** 响应 MUST 为 200，`remaining_count` MUST 等于该整数，`reject_reason` MUST 为 `null`，原有进京证字段 MUST 与增加这两个字段之前一致

#### Scenario: 剩余次数为零且存在审核原因

- **WHEN** 进京证查询成功，剩余次数为 0，且状态中已有审核不通过原因
- **THEN** `remaining_count` MUST 为 0，`reject_reason` MUST 等于该原因原文

#### Scenario: 两项都没有

- **WHEN** 进京证查询成功，但剩余次数缺失、为空白或不能解析，且审核原因缺失或为空白
- **THEN** `remaining_count` 与 `reject_reason` MUST 都为 `null`

### Requirement: 当日限行复用现有限行服务

系统 MUST 用现有限行服务判断该车牌当日是否限行，并把结果放在 `traffic_limited_today`。服务返回确定规则时，该字段 MUST 为布尔值。服务没有返回状态、没有规则、带有错误信息，或调用抛出异常时，该字段 MUST 为 `null`。这种缺失 MUST NOT 把本次进京证查询改为失败。系统 MUST NOT 为该字段另建限行数据源。

#### Scenario: 限行服务给出结论

- **WHEN** 进京证查询成功，且限行服务返回一条没有错误信息的当日规则
- **THEN** `traffic_limited_today` MUST 等于该规则对该车牌的限行结论

#### Scenario: 限行服务无法判断

- **WHEN** 进京证查询成功，但限行服务失败、没有规则或抛出异常
- **THEN** 响应 MUST 仍为 200，进京证字段 MUST 保持可用，`traffic_limited_today` MUST 为 `null`，响应 MUST NOT 包含限行服务的内部错误文本

#### Scenario: 进京证查询未成功

- **WHEN** 请求因缺少或错误令牌返回 401，因车牌不在令牌范围返回 403，因范围内没有进京证记录返回 404，或因进京证查询失败返回 503
- **THEN** 系统 MUST NOT 为了新字段查询限行，并且这些状态码与既有错误正文 MUST 保持不变
