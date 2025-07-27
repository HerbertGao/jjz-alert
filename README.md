# JJZ-Alert 进京证提醒工具

## 简介

JJZ-Alert 是一个自动化进京证有效期提醒工具，支持多用户配置。系统会定时查询北京交警网站，获取进京证状态，并通过 Bark 推送通知到你的手机。

## 功能特性

- 多用户、多 Token 支持
- **新功能：支持一个jjz_token对应多个bark配置**
- 自动查询进京证状态
- Bark 推送（支持加密）
- **新功能：自动添加推送图标**
- **新功能：智能状态显示格式**
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

### 2. 配置 `.env` 文件

#### 基础配置（单bark）
```ini
# 定时提醒相关配置
REMIND_ENABLE=true         # true=定时提醒，false=只执行一次
REMIND_TIMES=7:00,19:00   # 每天几点提醒，多个时间用英文逗号分隔

# Bark推送默认图标（可选）
BARK_DEFAULT_ICON=https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256

USER1_JJZ_URL=https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList
USER1_JJZ_TOKEN=你的进京证Token
USER1_BARK_SERVER=https://api.day.app/你的deviceKey
USER1_BARK_ENCRYPT=false
# 如需加密推送
# USER1_BARK_ENCRYPT_KEY=16位密钥
# USER1_BARK_ENCRYPT_IV=16位IV
# 可继续添加 USER2_... USER3_... 等
```

#### 高级配置（多bark支持）
```ini
# 定时提醒相关配置
REMIND_ENABLE=true
REMIND_TIMES=7:00,19:00

# Bark推送默认图标（可选）
BARK_DEFAULT_ICON=https://pp.myapp.com/ma_icon/0/icon_42285886_1752238397/256

# 用户1配置
USER1_JJZ_URL=https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList
USER1_JJZ_TOKEN=你的进京证Token

# 用户1的多个bark配置
USER1_BARK1_SERVER=https://api.day.app/你的deviceKey1
USER1_BARK1_ENCRYPT=false

USER1_BARK2_SERVER=https://api.day.app/你的deviceKey2
USER1_BARK2_ENCRYPT=true
USER1_BARK2_ENCRYPT_KEY=16位密钥
USER1_BARK2_ENCRYPT_IV=16位IV

USER1_BARK3_SERVER=https://api.day.app/你的deviceKey3
USER1_BARK3_ENCRYPT=false
```

### 3. 运行

```bash
python main.py
```

## 多Bark配置说明

现在支持为每个用户配置多个bark推送服务，这样可以：
- 同时向多个设备推送通知
- 配置不同的推送策略（如一个用于紧急通知，一个用于日常提醒）
- 提高通知的可靠性

配置格式：`USER{n}_BARK{m}_SERVER`，其中：
- `n` 是用户编号（1, 2, 3...）
- `m` 是该用户的bark配置编号（1, 2, 3...）

详细配置说明请参考 [CONFIG_GUIDE.md](CONFIG_GUIDE.md)

## 推送图标功能

所有Bark推送都会自动添加默认图标，让通知更加美观：
- 默认使用进京证相关的图标
- 可通过 `BARK_DEFAULT_ICON` 环境变量自定义图标URL
- 支持任何可访问的图片URL

## 状态显示格式

系统采用智能状态显示格式，让通知更加简洁：

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

## 定时提醒说明

- `REMIND_ENABLE=true` 时，程序会在 `REMIND_TIMES` 指定的时间点每天自动提醒。
- `REMIND_ENABLE=false` 时，程序启动后只会立即执行一次提醒，不再定时。
- `REMIND_TIMES` 格式为 `HH:MM,HH:MM`，如 `7:00,19:00` 表示每天 7:00 和 19:00 各提醒一次。

## Docker 部署

```bash
# 使用 docker-compose
docker-compose up -d
```

## GitHub Actions 自动构建

推送到 main/master 分支或手动触发 workflow，会自动构建并推送多平台镜像到 `ghcr.io/herbertgao/jjz-alert`。

## 镜像信息

- 镜像仓库：`ghcr.io/herbertgao/jjz-alert`
- 支持平台：`linux/amd64`, `linux/arm64`

## 进京证接口与 Bark 推送说明

- 北京交警接口需配置有效 Token 和 URL（北京交警App和微信小程序的URL端口不同，须区分）
- Bark 推送格式及加密方式详见 [Bark 官方文档](https://bark.day.app/#/tutorial)

## 其他

如需自定义推送内容、定时策略或有其它需求，请修改 `main.py` 或联系作者。
