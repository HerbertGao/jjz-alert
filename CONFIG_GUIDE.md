# 进京证提醒配置指南

## 新功能：支持一个jjz_token对应多个bark配置

现在支持为每个用户配置多个bark推送服务，这样可以：
- 同时向多个设备推送通知
- 配置不同的推送策略（如一个用于紧急通知，一个用于日常提醒）
- 提高通知的可靠性

## 配置格式

### 基本配置
```bash
# 是否启用定时提醒
REMIND_ENABLE=true

# 提醒时间，格式为 HH:MM，多个时间用逗号分隔
REMIND_TIMES=08:00,12:00,18:00

# Bark推送默认图标（可选）
BARK_DEFAULT_ICON=https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256
```

### 用户配置（新格式）

每个用户可以有多个bark配置，使用数字后缀区分：

```bash
# 用户1的基本信息
USER1_JJZ_TOKEN=your_jjz_token_here
USER1_JJZ_URL=https://api.example.com/jjz/status

# 用户1的多个bark配置
# Bark配置1
USER1_BARK1_SERVER=https://api.day.app/your_bark_key_1
USER1_BARK1_ENCRYPT=false
USER1_BARK1_ENCRYPT_KEY=
USER1_BARK1_ENCRYPT_IV=

# Bark配置2
USER1_BARK2_SERVER=https://api.day.app/your_bark_key_2
USER1_BARK2_ENCRYPT=true
USER1_BARK2_ENCRYPT_KEY=your_encrypt_key_2
USER1_BARK2_ENCRYPT_IV=your_encrypt_iv_2

# Bark配置3
USER1_BARK3_SERVER=https://api.day.app/your_bark_key_3
USER1_BARK3_ENCRYPT=false
USER1_BARK3_ENCRYPT_KEY=
USER1_BARK3_ENCRYPT_IV=

# 用户2配置
USER2_JJZ_TOKEN=your_jjz_token_2_here
USER2_JJZ_URL=https://api.example.com/jjz/status

# 用户2的bark配置
USER2_BARK1_SERVER=https://api.day.app/your_bark_key_4
USER2_BARK1_ENCRYPT=false
USER2_BARK1_ENCRYPT_KEY=
USER2_BARK1_ENCRYPT_IV=
```

### 配置说明

- `REMIND_ENABLE`: 是否启用定时提醒（true/false）
- `REMIND_TIMES`: 提醒时间，格式为 HH:MM，多个时间用逗号分隔
- `BARK_DEFAULT_ICON`: Bark推送的默认图标URL（可选，如果不设置会使用内置默认图标）
- `USER{n}_JJZ_TOKEN`: 第n个用户的进京证查询token
- `USER{n}_JJZ_URL`: 第n个用户的进京证查询API地址
- `USER{n}_BARK{m}_SERVER`: 第n个用户的第m个bark服务器地址
- `USER{n}_BARK{m}_ENCRYPT`: 第n个用户的第m个bark是否启用加密（true/false）
- `USER{n}_BARK{m}_ENCRYPT_KEY`: 第n个用户的第m个bark加密密钥（仅在启用加密时需要）
- `USER{n}_BARK{m}_ENCRYPT_IV`: 第n个用户的第m个bark加密向量（仅在启用加密时需要）

### 兼容性

系统仍然支持旧的配置格式，如果检测到旧格式的配置，会自动转换为新格式：

```bash
# 旧格式（仍然支持）
USER1_BARK_SERVER=https://api.day.app/your_old_bark_key
USER1_BARK_ENCRYPT=false
USER1_BARK_ENCRYPT_KEY=
USER1_BARK_ENCRYPT_IV=
```

## 状态显示格式

系统采用智能状态显示格式，让通知更加简洁易读：

### 状态格式化规则
- **包含"审核通过"的状态**：只显示括号内的内容
  - `审核通过(生效中)` → `生效中`
  - `审核通过(已失效)` → `已失效`
  - `审核通过(待生效)` → `待生效`
- **其他状态**：显示完整状态
  - `审核不通过` → `审核不通过`
  - `审核中` → `审核中`
  - `已取消` → `已取消`

### 消息示例
```
车牌 豫E1R193 的进京证（六环内）状态：已失效。
车牌 京A12345 的进京证（六环外）状态：生效中，有效期 2024-01-01 至 2024-01-31，剩余 15 天。
车牌 津B67890 的进京证（六环内）状态：审核不通过。
```

## 使用场景

1. **多设备通知**: 配置多个bark key，同时向手机、平板等设备推送
2. **不同通知级别**: 一个bark用于紧急通知，另一个用于日常提醒
3. **备用通知**: 配置多个bark服务，提高通知的可靠性
4. **团队协作**: 多个团队成员共享同一个jjz_token，但各自接收通知

## 注意事项

1. 每个用户的bark配置数量没有限制，但建议不要超过5个
2. 所有bark配置都会收到相同的通知内容
3. 如果某个bark推送失败，不会影响其他bark的推送
4. 日志中会显示每个bark的推送结果，便于调试
5. 所有Bark推送都会自动添加默认图标，可以通过`BARK_DEFAULT_ICON`环境变量自定义
6. 状态显示会自动格式化，让通知更加简洁易读 