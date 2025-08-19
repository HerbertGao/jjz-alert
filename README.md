# JJZ-Alert v2.0 🚗

进京证智能提醒系统 - Redis缓存 + 多通道推送 + Home Assistant集成

## ⚡ 快速开始

### 🐳 Docker部署（推荐）

```bash
# 配置文件
cp config.yaml.example config.yaml
# 编辑 config.yaml

docker compose up -d
```

### 🔧 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置文件
cp config.yaml.example config.yaml
# 编辑 config.yaml

# 运行程序
python main.py
```

## 📱 v2.0 新特性

### 🌟 多通道推送

- **80+ 推送服务**: Telegram、微信、钉钉、邮件等
- **每车牌多通道**: 一个车牌可配置多种推送方式
- **Apprise多通道**: 支持80+推送服务，包括Bark

### 🗄️ Redis缓存

- **数据持久化**: 进京证、限行规则智能缓存
- **高性能**: 显著提升查询响应速度
- **监控统计**: 缓存命中率、使用统计

### 🏠 Home Assistant集成

- **多车牌设备**: 每个车牌独立设备管理
- **智能状态合并**: JJZ状态优先，限行状态补充
- **动态图标**: 根据状态自动切换图标
- **自动注册**: 设备和实体自动注册到HA
- **批量同步**: 高效的批量数据同步

#### 📨 Home Assistant MQTT Discovery（可选，推荐）

无需在 HA 的 YAML 中声明实体。启用 MQTT 集成后，jjz-alert 会通过 MQTT Discovery 自动注册实体，并通过保留消息（retain）在 HA 重启后自动恢复状态。

- 依赖：`asyncio-mqtt`（已在 `requirements.txt` 中加入）。如果使用 Docker，请重新构建镜像或重启容器以安装依赖。
- 实体命名：所有 `entity_id` 均为小写，形如：`sensor.{base_topic}_{province_pinyin}_{plate_remainder}`，例如 `sensor.jjz_alert_beijing_a12345`。
- 发布策略：Discovery/状态/属性/可用性均使用 QoS1 + retain。

步骤一：在 Home Assistant 启用 MQTT 集成
- 确保 HA 已连接到你的 MQTT Broker（可以通过 HA 前端“设置 -> 设备与服务 -> 添加集成 -> MQTT”完成）。

步骤二：在 jjz-alert 的 `config.yaml` 中开启 MQTT Discovery

```yaml
global:
  homeassistant:
    enabled: true           # 保持现有 HA 集成开启
    mqtt_enabled: true      # 启用 MQTT Discovery
    mqtt_host: "mqtt-broker.local"
    mqtt_port: 1883
    mqtt_username: "user"
    mqtt_password: "pass"
    mqtt_client_id: "jjz_alert"
    mqtt_discovery_prefix: "homeassistant"  # HA 默认
    mqtt_base_topic: "jjz_alert"            # 影响 entity_id 与主题前缀
    mqtt_qos: 1
    mqtt_retain: true
```

步骤三：触发一次推送/同步（会发布 Discovery 与最新状态）
- 运行主程序或执行统一推送工作流（含 HA 同步）：

```bash
python main.py
# 或调用 REST /query 触发一次工作流
# curl -X POST http://<jjz-alert-host>:8000/query -H 'Content-Type: application/json' -d '{"plates":["京A12345"]}'
```

发布的 MQTT 主题（默认 `mqtt_base_topic=jjz_alert`, `mqtt_discovery_prefix=homeassistant`）
- Discovery 配置：`homeassistant/sensor/jjz_alert_{object_id}/config`
- 状态：`jjz_alert/sensor/{object_id}/state`
- 属性：`jjz_alert/sensor/{object_id}/attributes`
- 可用性：`jjz_alert/status`

示例 Discovery payload（JSON）：

```json
{
  "name": "进京证与限行状态 - 我的车",
  "unique_id": "jjz_alert_beijing_a12345",
  "state_topic": "jjz_alert/sensor/beijing_a12345/state",
  "json_attributes_topic": "jjz_alert/sensor/beijing_a12345/attributes",
  "availability_topic": "jjz_alert/status",
  "icon": "mdi:car",
  "device": {
    "identifiers": ["jjz_alert_jinga12345"],
    "name": "进京证监控 我的车",
    "model": "Beijing Vehicle",
    "manufacturer": "JJZ Alert",
    "sw_version": "2.0"
  }
}
```

示例属性 payload（JSON）：

```json
{
  "friendly_name": "我的车 进京证与限行状态",
  "plate_number": "京A12345",
  "display_name": "我的车",
  "jjz_status": "valid",
  "jjz_status_desc": "生效中",
  "jjz_type": "六环外",
  "jjz_valid_start": "2025-08-18",
  "jjz_valid_end": "2025-08-22",
  "jjz_days_remaining": 4,
  "jjz_remaining_count": "2",
  "traffic_limited_today": false,
  "traffic_limited_today_text": "不限行",
  "traffic_rule_desc": "2和7",
  "traffic_limited_tail_numbers": "2和7",
  "icon": "mdi:car"
}
```

常见问题与排查
- 在 MQTT Explorer 等工具中检查上述主题是否存在且为保留消息（Retain）。
- 变更了 `mqtt_base_topic` 或 `object_id` 后，HA 可能残留旧实体；可清理对应的保留消息后重新发布（向相同主题发布空载荷/空 JSON，retain=true）。
- 确认 HA 的 MQTT 集成已连接到同一 Broker（HA 日志与“设置 -> 设备与服务 -> MQTT”页面可见）。

## 🔧 CLI工具

```bash
# 配置迁移（v1.x → v2.0）
python cli_tools.py migrate

# 配置验证
python cli_tools.py validate

# 推送测试
python cli_tools.py test-push --plate 京A12345

# 系统状态
python cli_tools.py status -v

# 测试运行（分类运行）
python tests/tools/run_tests.py --unit     # 单元测试
python tests/tools/run_tests.py --performance  # 性能测试
```

## 📋 配置示例

### v2.0 多通道配置

```yaml
plates:
  - plate: "京A12345"
    display_name: "我的车"
    notifications:
      # Apprise推送（推荐）
      - type: "apprise"
        urls:
          - "barks://api.day.app/device_key?level={level}&group={plate}&icon={icon}"
      
      # Apprise多通道（推荐）
      - type: "apprise"
        urls:
          - "tgram://bot_token/chat_id"     # Telegram
          - "mailto://user:pass@gmail.com"  # 邮件
          - "wxwork://key"                  # 企业微信
          - "dingding://token/secret"       # 钉钉

```

## 📁 项目结构

```
├── 🎯 main.py                    # 主程序
├── 🔧 cli_tools.py              # CLI工具
├── 📦 requirements.txt          # 依赖列表
├── 📁 config/                   # ⚙️ 配置管理
├── 📁 service/                  # 🎯 业务逻辑
│   ├── cache/                   # 缓存服务
│   ├── homeassistant/          # Home Assistant集成
│   ├── jjz/                    # 进京证服务
│   └── notification/           # 推送服务
├── 📁 tests/                    # 🧪 测试文件
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   ├── performance/            # 性能测试
│   └── tools/                  # 测试工具
└── 📁 utils/                    # 🧰 工具函数
```

## 🔄 从v1.x升级

### 自动迁移

```bash
# 系统会自动检测v1.x配置并转换
# 原配置自动备份，零风险升级
python main.py
```

### 手动迁移

```bash
# 使用CLI工具迁移
python cli_tools.py migrate

# 验证新配置
python cli_tools.py validate
```

## 🚀 主要改进

| 功能 | v1.x | v2.0 |
|------|------|------|
| 推送通道 | 单一通道 | Apprise多通道 |
| 数据存储 | 内存 | Redis缓存 |
| 配置管理 | 静态 | 动态+验证 |
| 智能家居 | 无 | HA集成 |
| 车牌推送 | 1对1 | 1对多通道 |
| 错误处理 | 基础 | 管理员通知 |
| 测试覆盖 | 有限 | 完整测试套件 |

## ⭐ v2.0优势

- **🔄 向后兼容**: 现有配置100%兼容
- **📱 推送增强**: 支持更多推送方式
- **🚀 性能提升**: Redis缓存显著提速
- **🛠️ 易于管理**: CLI工具简化操作
- **🏠 智能集成**: Home Assistant支持
- **📊 监控完善**: 详细的状态和统计
- **🚨 错误处理**: 自动管理员通知机制
- **🧪 测试完善**: 76项测试全覆盖

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**快速体验**: `./docker/docker-dev.sh` 一键启动体验 🚀
