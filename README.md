# JJZ-Alert 进京证提醒工具

## 简介

JJZ-Alert 是一个自动化进京证有效期提醒工具，支持多用户配置。系统会定时查询北京交警网站，获取进京证状态，并通过 Bark 推送通知到你的手机。

## 功能特性

- 多用户、多 Token 支持
- 支持一个jjz_token对应多个bark配置
- **支持为每个用户配置单独的推送图标**
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

# 用户配置（数组形式）
users:
  # 用户1配置
  - name: "user1"
    jjz:
      token: "your_jjz_token_here"
      url: "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"
    
    bark_configs:
      # Bark配置1 - 使用自定义图标
      - server: "https://api.day.app/your_device_key_1"
        encrypt: false
        icon: "https://example.com/user1_icon1.png"
      
      # Bark配置2 - 使用自定义图标
      - server: "https://api.day.app/your_device_key_2"
        encrypt: true
        encrypt_key: "your_16_char_key"
        encrypt_iv: "your_16_char_iv"
        icon: "https://example.com/user1_icon2.png"

  # 用户2配置
  - name: "user2"
    jjz:
      token: "your_jjz_token_2_here"
      url: "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"
    
    bark_configs:
      # 用户2的bark配置 - 使用自定义图标
      - server: "https://api.day.app/your_device_key_4"
        encrypt: false
        icon: "https://example.com/user2_icon.png"
```

### 3. 运行

```bash
python main.py
```

## 简洁数组格式优势

YAML配置使用简洁的数组格式，具有以下优势：
- **更规范的配置结构**：标准的数组格式，便于程序处理
- **支持动态数量**：可以轻松添加或删除用户和bark配置
- **便于遍历**：程序可以轻松遍历所有配置项
- **支持配置验证**：便于进行类型检查和验证
- **版本控制友好**：配置变更更容易跟踪和比较
- **简洁易读**：移除冗余字段，配置更加简洁

## 多Bark配置说明

### 配置格式

每个用户可以有多个bark配置，使用数组格式：

```yaml
users:
  - name: "user1"
    jjz:
      token: "your_token"
      url: "https://api.example.com"
    bark_configs:
      - server: "https://api.day.app/key1"
        encrypt: false
        icon: "https://example.com/icon1.png"
      - server: "https://api.day.app/key2"
        encrypt: true
        encrypt_key: "your_key"
        encrypt_iv: "your_iv"
        icon: "https://example.com/icon2.png"
```

### 使用场景

1. **多设备推送**：同时向手机、平板等多个设备推送
2. **不同推送策略**：一个用于紧急通知，一个用于日常提醒
3. **提高可靠性**：多个推送服务互为备份
4. **个性化图标**：为不同设备配置不同的推送图标

## 推送图标功能

### 图标优先级

1. **用户特定图标**：`users[].bark_configs[].icon`（最高优先级）
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

### 用户配置 (users[])

- `name`: 用户名称
- `jjz.token`: 进京证查询token
- `jjz.url`: 进京证查询API地址
- `bark_configs[]`: bark配置数组

### Bark配置 (bark_configs[])

- `server`: bark服务器地址
- `encrypt`: 是否启用加密（true/false）
- `encrypt_key`: 加密密钥（仅在启用加密时需要）
- `encrypt_iv`: 加密向量（仅在启用加密时需要）
- `icon`: 推送图标（可选）

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
    icon: "https://example.com/icon.png"
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
