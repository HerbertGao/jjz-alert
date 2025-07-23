# JJZ-Alert 进京证提醒工具

## 项目简介

JJZ-Alert 是一个自动化进京证有效期提醒工具，支持多用户配置。系统会定时查询北京交警网站，获取进京证状态，并通过 Bark 推送通知到你的手机。

## 功能特性
- 支持多用户、多 Token 配置
- 自动请求北京交警接口，获取进京证状态
- 支持 Bark 推送（含加密推送）
- 支持推送级别（critical/active/timeSensitive/passive）
- 支持 Docker 部署与 GitHub Actions 自动构建

## 环境变量配置（.env 示例）
```ini
USER1_JJZ_TOKEN=你的进京证Token
USER1_BARK_SERVER=https://api.day.app/你的deviceKey
USER1_BARK_ENCRYPT=false
# 如需加密推送
# USER1_BARK_ENCRYPT_KEY=16位密钥
# USER1_BARK_ENCRYPT_IV=16位IV

# 可继续添加 USER2_... USER3_... 等
```

## 本地运行
1. 安装依赖
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. 配置 `.env` 文件
3. 运行
   ```bash
   python main.py
   ```

## Docker 部署
1. 构建镜像
   ```bash
   docker build -t ghcr.io/herbertgao/jjz-alert:latest .
   ```
2. 或使用 docker-compose
   ```bash
   docker-compose up -d
   ```

## GitHub Actions 自动构建
- 推送到 main/master 分支或手动触发 workflow，会自动构建并推送多平台镜像到 `ghcr.io/herbertgao/jjz-alert`
- 详见 `.github/workflows/docker-image.yml`

## 镜像信息
- 镜像仓库：`ghcr.io/herbertgao/jjz-alert`
- 支持平台：`linux/amd64`, `linux/arm64`

## 进京证接口与 Bark 推送说明
- 北京交警接口：`https://jjz.jtgl.beijing.gov.cn:2443/pro/applyRecordController/stateList`，需配置有效 Token
- Bark 推送格式及加密方式详见 [Bark 官方文档](https://bark.day.app/#/tutorial)

## 其他
- 如需自定义推送内容、定时策略或有其它需求，请修改 `main.py` 或联系作者。 