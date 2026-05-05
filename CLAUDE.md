# JJZ-Alert · Claude 项目约定

进京证智能提醒系统：多通道推送（Apprise 80+）、Redis 缓存、Home Assistant（REST + MQTT Discovery）、REST API；Python + Docker Compose 部署。

## 工作流硬约束

- **每次 `git push` 前必须先执行 `tox -e format`**（等价 `black .`），把格式化结果一并 commit 后再 push。CI / lint 依赖此步骤；遗漏会导致 PR 上出现 black diff 噪音、review 体验下降，并可能触发额外回合的 codex review。这条规则对所有 commit 类型（fix/feat/style/docs/chore）一视同仁，不可跳过。
- 测试至少跑 `pytest tests/unit/` 全绿才允许 push。覆盖率有变化时建议跑 `tox -e coverage` 复核。

## 配置约定

- `config.yaml` 是用户配置文件，**已 gitignore**（含 token/账户）；模板见 `config.yaml.example`。任何新增配置项都要同步更新模板。
- `openspec/config.yaml` 也在 gitignore 中，是 openspec-cn 的本地配置；不要尝试 commit。
- 修改配置 schema 时同时更新 `config/validation.py` 与 `config/migration.py`。

## 测试与质量

- 全局测试入口：`python tests/tools/run_tests.py --unit | --performance`，或通过 tox：
  - `tox -e unit -- --fast`（快速单测）
  - `tox -e integration`（集成测试）
  - `tox -e coverage`（覆盖率报告）
  - `tox -e format`（black 格式化，**push 前必跑**）
- 添加新功能必须配套单元测试；触发 service 层逻辑改动时优先在 `tests/unit/service/` 下加 case。
- 测试 fixture 中的 `jjzzlmc` / `blztmc` 等字段统一用半角括号 `()`，因为 API 入边界 `normalize_response_parens` 已规范化生产数据为半角形态。

## 代码与目录约定

- 主要业务代码在 `jjz_alert/`：`config/` `service/{cache,homeassistant,jjz,notification,traffic}` `base/`。
- CLI 入口：`cli_tools.py`（验证、test-push、ha test/sync/cleanup、status）。
- 自动续办（auto-renew）模块：决策器 `service/jjz/renew_decider.py`，调度 `service/jjz/renew_trigger.py`，工作流 `service/jjz/renew_workflow.py`，状态查询 `service/jjz/jjz_service.py`；spec 在 `openspec/specs/auto-renew/spec.md`。
- 通知发送通过 `service/notification/unified_pusher.py` 统一入口；新增通道走 Apprise URL，不要写死 SDK。

## 提交与 PR

- Commit message 用约定式（fix / feat / style / docs / chore / refactor / test）。
- PR 描述附 codex review 结论摘要（如经过 codex 审视）。
- 涉及行为/契约变化的改动走 openspec 流程：`openspec/changes/<name>/{proposal.md,design.md,specs/**,tasks.md}`，PR 合并后用 `openspec-cn archive` 归档到 `openspec/specs/`。

## 部署

- 生产部署在 mac-mini，路径 `/Users/herbertgao/Docker/jjz-alert/`；通过 `docker compose pull && docker compose up -d` 更新。
- 镜像由 GHA 多架构构建发布到 `ghcr.io/herbertgao/jjz-alert:latest`。
