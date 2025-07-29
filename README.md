# JJZ-Alert 进京证提醒工具

## 简介

JJZ-Alert 是一个自动化进京证有效期提醒工具，支持多车牌号配置和跨账号匹配。系统会定时查询北京交警网站，获取进京证状态，并通过 Bark 推送通知到你的手机。

## 功能特性

- 多车牌号、多 Token 支持
- **支持跨账号匹配**：A账户的车牌号可以匹配B账户的进京证信息
- **分离式配置**：用户配置（Bark推送）和进京证账户配置（数据抓取）分离
- **支持为每个车牌号配置单独的推送图标**
- **支持YAML格式配置文件管理（简洁数组格式）**
- 自动查询进京证状态
- Bark 推送（支持加密）
- 自动添加推送图标
- 智能状态显示格式
- 尾号限行提醒
- 推送级别（critical/active/timeSensitive/passive）
- 灵活定时提醒，可配置开关
- 支持 Docker 部署与 GitHub Actions 自动构建

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

创建 `config.yaml` 文件：

```yaml
# 全局配置
global:
  # 定时提醒相关配置
  remind:
    enable: true
    times: ["08:00", "12:00", "18:00"]
  
  # Bark推送默认图标（可选）
  bark_default_icon: "https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256"

# 进京证账户配置（用于抓取数据）
# 每个账户可以绑定多个车牌号，系统会抓取该账户下的所有车辆信息
jjz_accounts:
  # 账户1配置
  - name: "账户1"
    jjz:
      token: "your_jjz_token_1_here"
      url: "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"
  
  # 账户2配置
  - name: "账户2"
    jjz:
      token: "your_jjz_token_2_here"
      url: "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"

# 车牌号配置（用于推送通知）
# 每个车牌号可以配置独立的图标和推送设备
plate_configs:
  # 车牌号1配置
  - plate: "京A12345"
    plate_icon: "https://example.com/plate1_icon.png"  # 车牌号专用图标
    bark_configs:
      # Bark配置1
      - server: "https://api.day.app/your_device_key_1"
        encrypt: false
      
      # Bark配置2
      - server: "https://api.day.app/your_device_key_2"
        encrypt: true
        encrypt_key: "your_16_char_key"
        encrypt_iv: "your_16_char_iv"

  # 车牌号2配置
  - plate: "京B67890"
    plate_icon: "https://example.com/plate2_icon.png"  # 车牌号专用图标
    bark_configs:
      # Bark配置1
      - server: "https://api.day.app/your_device_key_1"
        encrypt: false
      
      # Bark配置2
      - server: "https://api.day.app/your_device_key_2"
        encrypt: true
        encrypt_key: "your_16_char_key"
        encrypt_iv: "your_16_char_iv"

  # 车牌号3配置（使用默认图标）
  - plate: "京C11111"
    # plate_icon: 不设置，将使用全局默认图标
    bark_configs:
      - server: "https://api.day.app/your_device_key_3"
        encrypt: false
```

### 3. 运行

```bash
python main.py
```

## 分离式配置优势

新的配置结构将用户配置和进京证账户配置分离，具有以下优势：

- **职责分离**：数据抓取和推送通知职责明确分离
- **跨账号支持**：支持跨账号匹配，更灵活的车牌号管理
- **配置简化**：避免重复配置，减少维护成本
- **扩展性强**：可以轻松添加新的账户或车牌号配置
- **逻辑清晰**：配置结构更符合实际使用场景

## 跨账号匹配功能

### 工作原理

1. **数据抓取**：遍历所有进京证账户，抓取每个账户下的所有车辆信息
2. **车牌号匹配**：根据查询结果中的车牌号匹配对应的plate_configs配置
3. **独立推送**：为每个匹配的车牌号使用其专用图标进行推送

### 使用场景

- **多账户管理**：不同家庭成员使用不同的进京证账户
- **车牌号分散**：同一家庭的车牌号可能绑定在不同的账户下
- **灵活配置**：可以为每个车牌号配置独立的推送设备和图标

### 示例场景

假设有以下配置：
- **账户1**：绑定车牌号"京A12345"
- **账户2**：绑定车牌号"京B67890"和"京C11111"

系统会：
1. 查询账户1，获取"京A12345"的进京证信息
2. 查询账户2，获取"京B67890"和"京C11111"的进京证信息
3. 根据车牌号匹配对应的plate_configs配置
4. 使用匹配的配置进行推送通知

## 推送图标功能

### 图标优先级

1. **车牌号专用图标**：`plate_configs[].plate_icon`（最高优先级）
2. **全局默认图标**：`global.bark_default_icon`
3. **内置默认图标**：系统内置图标（最低优先级）

### 图标要求

- 必须是可访问的HTTP/HTTPS链接
- 建议使用PNG或JPG格式
- 建议尺寸为256x256像素或更大
- 文件大小建议不超过1MB

## Docker 部署

### 使用 Docker Compose

1. **创建配置文件**：

   ```bash
   cp config.yaml.example config.yaml
   # 编辑 config.yaml 文件
   ```

2. **启动服务**：

   ```bash
   docker-compose up -d
   ```

3. **查看日志**：

   ```bash
   docker-compose logs -f
   ```

### 使用 Docker 命令

```bash
docker run -d \
  --name jjz-alert \
  --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  ghcr.io/herbertgao/jjz-alert:latest
```

## 配置说明

### 全局配置 (global)

- `remind.enable`: 是否启用定时提醒（true/false）
- `remind.times`: 提醒时间列表，格式为 ["HH:MM", "HH:MM"]
- `bark_default_icon`: Bark推送的默认图标URL（可选）

### 进京证账户配置 (jjz_accounts[])

- `name`: 账户名称
- `jjz.token`: 进京证查询token
- `jjz.url`: 进京证查询API地址

### 车牌号配置 (plate_configs[])

- `plate`: 车牌号
- `plate_icon`: 车牌号专用图标URL（可选）
- `bark_configs[]`: bark配置数组

### Bark配置 (bark_configs[])

- `server`: bark服务器地址
- `encrypt`: 是否启用加密（true/false）
- `encrypt_key`: 加密密钥（仅在启用加密时需要）
- `encrypt_iv`: 加密向量（仅在启用加密时需要）

## 推送级别

系统会根据进京证状态自动选择合适的推送级别：

- `critical`: 进京证已过期或即将过期（剩余天数 ≤ 1）
- `active`: 进京证正常（剩余天数 > 1）
- `timeSensitive`: 进京证即将过期（剩余天数 ≤ 3）
- `passive`: 其他情况

## 定时提醒

### 配置说明

- `remind.enable`: 是否启用定时提醒
- `remind.times`: 提醒时间列表，格式为 ["HH:MM", "HH:MM"]

### 示例配置

```yaml
global:
  remind:
    enable: true
    times: ["08:00", "12:00", "18:00"]
```

### 注意事项

- 时间格式为24小时制，如 "08:00", "12:00", "18:00"
- 如果 `remind.enable` 为 false，则不会进行定时提醒
- 程序启动时会立即执行一次查询，然后按配置的时间进行定时提醒

## 加密推送

### 配置说明

如果您的Bark服务启用了加密，需要配置以下参数：

- `encrypt`: 设置为 true
- `encrypt_key`: 16位字符的加密密钥
- `encrypt_iv`: 16位字符的加密向量

### 示例配置

```yaml
bark_configs:
  - server: "https://api.day.app/your_key"
    encrypt: true
    encrypt_key: "your_16_char_key"
    encrypt_iv: "your_16_char_iv"
```

## 故障排除

### 常见问题

1. **配置文件不存在**：
   - 确保 `config.yaml` 文件存在且格式正确
   - 检查文件权限是否正确

2. **推送失败**：
   - 检查Bark服务器地址是否正确
   - 确认网络连接正常
   - 检查加密配置是否正确

3. **查询失败**：
   - 检查进京证token是否有效
   - 确认API地址是否正确
   - 检查网络连接

4. **车牌号不匹配**：
   - 确保配置文件中的车牌号与查询结果中的车牌号完全一致
   - 检查车牌号格式是否正确

5. **跨账号匹配问题**：
   - 确保所有进京证账户配置正确
   - 检查车牌号是否在plate_configs中正确配置

### 日志查看

```bash
# Docker 环境
docker-compose logs -f

# 本地环境
python main.py
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
