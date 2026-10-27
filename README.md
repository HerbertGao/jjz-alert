# JJZ-Alert 🚗

进京证智能提醒系统：多通道推送、Redis 缓存、Home Assistant 集成、REST API。

## ⚡ 快速开始

### 🐳 Docker 部署（推荐）

```bash
# 复制并编辑配置
cp config.yaml.example config.yaml

# 启动
docker compose up -d
```

### 🔧 本地运行

```bash
# 建议使用虚拟环境
python -m venv .venv && source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置
cp config.yaml.example config.yaml

# 运行
python main.py
```

## ✨ 功能概览

- **多通道推送**：基于 Apprise，支持 80+ 服务（Bark/Telegram/邮件/企业微信/钉钉 等）
- **Redis 缓存**：缓存 JJZ 与限行数据，支持统计与健康检查
- **Home Assistant 集成**：支持 REST 与 MQTT Discovery 两种模式
- **REST API**：/health、/metrics、/query
- **定时提醒**：按 `global.remind.times` 自动执行

## 🧩 配置（摘自 `config.yaml.example`）

```yaml
global:
  log:
    level: INFO
  remind:
    enable: true
    times: ["07:00", "12:30", "19:00", "23:55"]
    api:
      enable: true
      host: "0.0.0.0"
      port: 8000
  redis:
    host: localhost
    port: 6379
    db: 0
  homeassistant:
    enabled: false
    integration_mode: mqtt  # rest 或 mqtt

jjz_accounts:
  - name: "示例账户"
    jjz:
      token: "your_token"
      url: "https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList"

plates:
  - plate: "京A12345"
    display_name: "我的车"
    notifications:
      - type: apprise
        urls:
          - "barks://api.day.app/device_key?level={level}&group={plate}&icon={icon}"
          - "tgram://bot_token/chat_id"
```

更多可选项与完整示例见 `config.yaml.example`。

## 🏠 Home Assistant（可选）

两种集成模式：
- **REST**：提供 `rest_url` 与 `rest_token`
- **MQTT**：提供 `mqtt_host/port/username/password`

启用示例（MQTT）：
```yaml
global:
  homeassistant:
    enabled: true
    integration_mode: mqtt
    mqtt_host: "mqtt-broker.local"
    mqtt_port: 1883
    mqtt_username: "user"
    mqtt_password: "pass"
```

运行主程序或调用 API `/query` 会自动同步/发布实体与状态。

## 🌐 REST API

- `GET /health`：系统健康状态
- `GET /metrics`：运行与性能指标
- `POST /query`：触发查询与推送，示例：

```bash
curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"plates":["京A12345"]}'
```

注：需在配置中开启 `global.remind.enable=true` 且 `global.remind.api.enable=true`。

## 🛠️ CLI 工具

```bash
# 配置验证
python cli_tools.py validate

# 推送测试（所有车牌/指定车牌）
python cli_tools.py test-push
python cli_tools.py test-push --plate 京A12345

# 查看系统状态（含支持的 Apprise 服务预览）
python cli_tools.py status -v

# Home Assistant 相关
python cli_tools.py ha test
python cli_tools.py ha sync -v
python cli_tools.py ha cleanup --force
```

## 🧪 测试

```bash
python tests/tools/run_tests.py --unit         # 单元测试
python tests/tools/run_tests.py --performance  # 性能测试
```

或通过 tox 快速切换测试环境（推荐先在 `.venv` 中安装开发依赖）：

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt

tox -e py311              # 默认 pytest 套件
tox -e unit -- --fast     # 只跑单测，可传递额外参数
tox -e integration        # 集成测试
tox -e coverage           # 生成覆盖率报告
tox -e format             # 使用 Black 格式化代码
```

## 🚀 发布

推送到 `master` 后，若自最近的 `vX.Y.Z` 以来有需要发版的提交（`feat` / `fix` / `perf` / `refactor` / 破坏性变更），Actions 会打开或更新**一个**开发版 PR（`chore(release): 版本统一到 X.Y.Z`）。Dependabot 和纯文档 / chore 不会单独触发。

合并该 PR 会打 annotated tag、发布 GitHub Release，并构建 `ghcr.io/herbertgao/jjz-alert:vX.Y.Z`（以及 `latest`）。本地预览：`scripts/release.sh --dry-run`。规则与补救步骤见 [RELEASE.md](RELEASE.md)。

## 📁 项目结构

```
├── main.py
├── cli_tools.py
├── requirements.txt
├── config/
│   ├── config.py
│   ├── migration.py
│   ├── validation.py
│   └── redis/
├── service/
│   ├── cache/
│   ├── homeassistant/
│   ├── jjz/
│   ├── notification/
│   └── traffic/
├── utils/
└── tests/
```

## 📄 许可证

MIT License - 详见 `LICENSE` 文件
