# JJZ-Alert · 代理与贡献者约定

进京证智能提醒系统：多通道推送（Apprise 80+）、Redis 缓存、Home Assistant（REST + MQTT Discovery）、REST API；Python + Docker Compose 部署。

本文件是给编码代理和贡献者的唯一全文。`CLAUDE.md` 只指向这里。

## 工作流硬约束

- **每次 `git push` 前必须先执行 `tox -e format`**（等价 `black .`），把格式化结果一并 commit 后再 push。CI / lint 依赖此步骤；遗漏会在 PR 上留下 black diff。这条规则对所有提交类型（`fix` / `feat` / `style` / `docs` / `chore` 等）一视同仁。
- 测试至少跑 `pytest tests/unit/` 全绿才允许 push。覆盖率有变化时建议跑 `tox -e coverage` 复核。

## 配置约定

- `config.yaml` 已 gitignore（文件名匹配任意目录，因此 `openspec/config.yaml` 同样被忽略）。里面有 token 和账户，**不要 commit**。模板只改 `config.yaml.example`。任何新增配置项都要同步更新模板。
- `openspec/config.yaml` 是 openspec-cn 的本地配置，不要尝试 commit。
- 修改配置 schema 时同时更新 `config/validation.py` 与 `config/migration.py`。

## 测试与质量

- 全局测试入口：`python tests/tools/run_tests.py --unit | --performance`，或通过 tox：
  - `tox -e unit -- --fast`（快速单测）
  - `tox -e integration`（集成测试）
  - `tox -e coverage`（覆盖率报告）
  - `tox -e format`（black 格式化，**push 前必跑**）
- 添加新功能必须配套单元测试；触发 service 层逻辑改动时优先在 `tests/unit/service/` 下加 case。
- 测试 fixture 中的 `jjzzlmc` / `blztmc` 等字段统一用半角括号 `()`，因为 API 入边界 `normalize_response_parens` 已把生产数据规范成半角。

## 代码与目录约定

- 主要业务代码在 `jjz_alert/`：`config/` `service/{cache,homeassistant,jjz,notification,traffic}` `base/`。
- CLI 入口：`cli_tools.py`（验证、test-push、ha test/sync/cleanup、status）。
- 自动续办（auto-renew）模块：决策器 `service/jjz/renew_decider.py`，调度 `service/jjz/renew_trigger.py`，工作流 `service/jjz/renew_workflow.py`，状态查询 `service/jjz/jjz_service.py`；spec 在 `openspec/specs/auto-renew/spec.md`。
- 通知发送通过 `service/notification/unified_pusher.py` 统一入口；新增通道走 Apprise URL，不要写死 SDK。
- 涉及行为或契约变化的改动走 openspec：`openspec/changes/<name>/{proposal.md,design.md,specs/**,tasks.md}`。PR 合并后用 `openspec-cn archive` 归档到 `openspec/specs/`。

## 提交、PR 与发版

发版决策在 `scripts/release_version.py`（`bump_for`、`is_dependabot`、`plan_repo`），由 `.github/workflows/release.yml` 在每次 push 到 `master` 时调用。下面的规则按这份代码写，不要另造一套版本号算法。细节和本地命令见 [RELEASE.md](RELEASE.md)。

### 每条提交首行和每个 PR 标题都要是约定式提交

格式（与 `_HEADER` 相同）：

```text
type(可选scope)可选!: 说明
```

对应正则：

```text
^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s+(?P<rest>.+)$
```

- `type` 是一段 ASCII 字母，比较前会转成小写。中文说明放在冒号和空格之后，例如 `feat(api): 增加按令牌绑定车牌的最新进京证查询接口`。
- `scope` 可省略。`!` 若出现，必须紧贴冒号之前（`feat!: ...` 或 `feat(api)!: ...`）。
- 冒号后至少要有一个空格，说明不能为空。`feat(api):增加接口` 匹配失败。
- 没有类型前缀的中文标题匹配失败。Release 把它和 `chore` 一样忽略。

仓库通常用 **squash merge**。落到 `master` 上、被 Release 检查的是 squash 提交的**第一行**。GitHub 默认用 PR 标题做这个第一行，并在末尾加上 ` (#编号)`。`(#编号)` 留在说明里，前缀还在就能识别，例如 `feat(api): 增加按令牌绑定车牌的最新进京证查询接口 (#147)`。

合并前保留这个前缀。把 squash 主题改成没有 `type:` 的中文句子后，自动发版不会发生。

`plan_repo` 用 `git log --no-merges <最近的 vX.Y.Z>..HEAD` 收集提交，因此：

- squash：只看这一条 squash 提交的首行。
- merge commit：合并提交本身被跳过，分支上每条非 merge 提交的首行各自参与计算。
- rebase：每条提交的首行都参与计算。

### 什么会在 push 到 master 后自动打开开发版 PR

基线是最近的 `vX.Y.Z` tag（不是仓库里可能滞后的版本字符串）。自该 tag 以来，`bump_for` 对每条非 merge 提交给出一个级别，`highest_bump` 取最高的：`major` > `minor` > `patch`。

| 提交 | 结果 |
| --- | --- |
| 首行已是约定式，且带 `type!`，或正文有一行以 `BREAKING CHANGE:` / `BREAKING-CHANGE:` 开头 | **major**（`2.6.0` → `3.0.0`）。破坏性优先于类型，所以 `feat!: ...` 是 major |
| `feat` | **minor**（`2.6.0` → `2.7.0`） |
| `fix` / `perf` / `refactor` / `revert` | **patch**（`2.6.0` → `2.6.1`） |
| `chore` / `docs` / `style` / `test` / `ci` / `build` | 不发版 |
| 其他能匹配头格式的类型（如 `feature`、`wip`） | 不发版。会抬版本的类型只有 `feat`、`fix`、`perf`、`refactor`、`revert`，外加上面的破坏性标记 |
| 首行不是约定式 | 不发版 |
| 作者名或邮箱里含 `dependabot`（大小写不敏感） | 不发版，即使首行是 `fix:` |
| 首行是 `chore(release): 版本统一到 X.Y.Z` | 不参与 bump。它是开发版 PR 自己的提交；成为 HEAD 时走发布，见下文 |

正文里的 `BREAKING CHANGE:` 只在首行已经匹配约定式头时生效。纯中文首行加上这份 footer，仍然不发版。

没有可发布提交时，workflow 的 `action=skip`。日志里的原因是：

```text
自 vX.Y.Z 起没有需要发版的提交（dependabot、chore/docs/style/test/ci/build 与非约定式提交不计）
```

有可发布提交时 `action=prepare`：CI 通过后打开或更新**唯一**的开发版 PR，分支 `release/version`，标题 `chore(release): 版本统一到 X.Y.Z`（`X.Y.Z` 无 `v` 前缀）。这个 PR 只改 `jjz_alert/__version__` 和 `CHANGELOG.md`。

若代码里的 `__version__` 已经高于按提交算出的下一版，计划改用代码里的版本（`bump=explicit`）。目标 tag 已存在则 skip，不重复开 PR。

### 2026-11-12 的反例

PR #147 squash 进 `master` 的首行是：

```text
增加按令牌绑定车牌的最新进京证查询接口 (#147)
```

自 tag `v2.6.0` 起没有可发布提交（Dependabot 的 `chore(deps)` 也不计），Release 分类为 `action=skip`。维护者随后对 Release workflow 做 `workflow_dispatch`，`mode=prepare`，并显式填写版本 `2.7.0`，才打开开发版 PR。

同一改动的合法标题：

```text
feat(api): 增加按令牌绑定车牌的最新进京证查询接口
```

squash 之后变成 `feat(api): 增加按令牌绑定车牌的最新进京证查询接口 (#147)`，`bump_for` 给出 minor。

### 标题示例

合法，并且会抬版本：

```text
feat(api): 增加按令牌绑定车牌的最新进京证查询接口
feat(api): 增加按令牌绑定车牌的最新进京证查询接口 (#147)
fix: 修正进京证状态解析
perf(cache): 缩短缓存读取
refactor: 拆分查询客户端
revert: 撤回上一处解析改动
feat!: 更改查询响应字段
fix(api)!: 移除已废弃字段
```

`fix: 调整字段` 的正文里若有单独一行 `BREAKING CHANGE: 响应不再包含旧字段`，结果是 major。

合法，但**不会**自动打开发版 PR：

```text
docs: 将 CLAUDE.md 更新为 AGENTS.md 并明确 PR 与发版约定
chore(deps): bump aiohttp from 3.9.0 to 3.10.0
style: 整理导入
test: 补上查询单测
ci: 收紧标题检查
build: 更新基础镜像
chore(release): 版本统一到 2.7.0
```

非法（squash 后 Release 直接 skip）：

```text
增加按令牌绑定车牌的最新进京证查询接口
增加按令牌绑定车牌的最新进京证查询接口 (#147)
feat(api):增加按令牌绑定车牌的最新进京证查询接口
feature: 增加查询接口
```

最后一行能匹配头格式，但 `feature` 不是 `feat`，所以检查可以通过、发版仍然 skip。需要 minor 时写成 `feat`。

### 合并开发版 PR 才会发布

开发版 PR 的标题保持 `chore(release): 版本统一到 X.Y.Z`。合并进 `master` 后，HEAD 首行（squash 时末尾可以有 ` (#编号)`）被 `head_release_version` 认成发布：创建 annotated tag `vX.Y.Z`（已指向别的提交则失败，不覆盖），发布**非 draft** GitHub Release（已经发布过则不改 release notes），再 `workflow_dispatch` Docker Image Build，推送 `ghcr.io/herbertgao/jjz-alert:vX.Y.Z` 与 `:latest`。

merge commit 也能发布：首行是 `Merge pull request #N from …/release/version` 或 `Merge branch 'release/version'`，并且后面某行仍是 `chore(release): 版本统一到 X.Y.Z`。

`GITHUB_TOKEN` 推上去的 tag 不会再次触发 `on.push`。镜像构建是 workflow 里显式 dispatch 的。

### 需要发版、但提交没有约定式前缀时

不要放宽 `bump_for` 去接受纯中文标题。用手动准备：

1. GitHub → Actions → **Release** → Run workflow。
2. `mode=prepare`（默认）。`version` 可选，填写 `N.N.N`，**不要**加 `v` 前缀。工作流说明如此；脚本若收到单个前导 `v` 会去掉再解析。
3. 填了版本时，计划不再扫描提交，直接准备该版本。它必须**严格高于**最近的 `vX.Y.Z` tag，否则 `plan_repo` 报错。留空则仍按上面的提交规则计算。
4. 合并产生的 `chore(release): 版本统一到 X.Y.Z` PR。合并后打 tag 并发布 GitHub Release。

`mode=publish` 不开 PR。它给当前 `jjz_alert/__version__` 打 tag 并发布，用作开发版 PR 已经合并、但自动发布没跑起来时的补救。若同时填写 `version`，该值必须与 `__version__` 相同，否则报错。版本还没写进 `__version__` 时，用 `prepare` 加显式版本，而不是 `publish`。

本地预览：`scripts/release.sh --dry-run`。指定版本：`scripts/release.sh 2.7.0`。

### CI 会拒绝认不出的 PR 标题

`.github/workflows/ci.yml` 的 `pr-title` 只在 `pull_request` 时运行 `scripts/check_conventional_title.py`。它调用 `is_conventional_subject`，和 `bump_for` 用同一条 `_HEADER`。

- 纯中文标题、冒号后没有空格：失败。
- `docs:` / `chore:` / `style:` / `test:` / `ci:` / `build:` 以及 `chore(release): 版本统一到 X.Y.Z`：通过。它们不自动抬版本，这是发版脚本的行为，检查不去改它。
- Dependabot 的 `chore(deps): …` 标题可以通过。Dependabot 提交不发版，是因为作者名或邮箱含 `dependabot`，不是因为标题检查。

这道检查盖住 GitHub 默认的 squash 主题（等于 PR 标题）。直接 push 到 `master`、或 rebase 后每条提交的首行，仍要自己写成约定式。

## 公开描述脱敏

会公开的 PR 描述、以及会进入 GitHub 的提交正文，只保留协议常量和一般说明。写进去之前去掉：

- 真实群组 ID、个人信息、推送正文
- 生产环境主机名、用户名、部署路径
- 车牌、API token 以及其他密钥

`config.yaml` 和其余已 gitignore 的密钥文件不要 commit。新配置项只进 `config.yaml.example`。

## 部署

镜像由 GitHub Actions 构建 `linux/amd64` 与 `linux/arm64`，发布到 GHCR：

- `ghcr.io/herbertgao/jjz-alert:latest`
- `ghcr.io/herbertgao/jjz-alert:vX.Y.Z`

运行环境使用 Docker Compose。更新已发布镜像：

```bash
docker compose pull && docker compose up -d
```

## 相关文件

- 发版规则的操作说明：[RELEASE.md](RELEASE.md)
- 决策实现：`scripts/release_version.py`、`scripts/release_plan.py`
- 工作流：`.github/workflows/release.yml`
- PR 标题检查：`scripts/check_conventional_title.py`
