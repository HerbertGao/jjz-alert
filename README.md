# JJZ-Alert 进京证提醒工具

## 简介

JJZ-Alert 是一个自动化进京证有效期提醒工具，支持多用户配置。系统会定时查询北京交警网站，获取进京证状态，并通过 Bark 推送通知到你的手机。

## 功能特性

- 多用户、多 Token 支持
- 自动查询进京证状态
- Bark 推送（支持加密）
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

```ini
# 定时提醒相关配置
REMIND_ENABLE=true         # true=定时提醒，false=只执行一次
REMIND_TIMES=7:00,19:00   # 每天几点提醒，多个时间用英文逗号分隔

USER1_JJZ_URL=https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList
USER1_JJZ_TOKEN=你的进京证Token
USER1_BARK_SERVER=https://api.day.app/你的deviceKey
USER1_BARK_ENCRYPT=false
# 如需加密推送
# USER1_BARK_ENCRYPT_KEY=16位密钥
# USER1_BARK_ENCRYPT_IV=16位IV
# 可继续添加 USER2_... USER3_... 等
```

### 3. 运行

```bash
python main.py
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
