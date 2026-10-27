# 发布

发版对齐 [pi-extensions](https://github.com/HerbertGao/pi-extensions/blob/master/.github/workflows/release.yml) 的「push 默认分支 → 版本 PR → 合并后发布」，实现形态来自 [herbertgao-skills](https://github.com/HerbertGao/herbertgao-skills/blob/main/.github/workflows/release.yml)（没有 npm / changesets）。工作流是 [`.github/workflows/release.yml`](.github/workflows/release.yml)。

## 自动路径

1. **推送到 `master`**。自最近的 `vX.Y.Z` tag 起，按下面的规则计算下一版本。没有可发布提交就什么也不做（Dependabot、`chore(deps)` 不会单独开 PR，也不会打空 tag）。
2. 检查（现有 CI）通过后，打开或更新**唯一**的开发版 PR：分支 `release/version`，标题 `chore(release): 版本统一到 X.Y.Z`。这个 PR 只改 `jjz_alert/__version__` 和 `CHANGELOG.md`。重复推送如果树没有变化，不会再推一个新 commit，也不会再开一个 PR。
3. **合并该 PR**（请保留标题；squash 或 merge commit 都可以识别）。workflow 会：
   - 在该提交上创建 annotated tag `vX.Y.Z`（tag 已指向别的提交则失败，不会移动 tag）
   - 发布**非 draft** GitHub Release（已经发布过则不改 notes）
   - `workflow_dispatch` [Docker Image Build](.github/workflows/docker-image.yml)，在这个 tag 上构建并推送 `ghcr.io/herbertgao/jjz-alert:vX.Y.Z` 和 `:latest`

`GITHUB_TOKEN` 推送的 tag **不会**再次触发 `on.push`。所以镜像构建是 workflow 里显式 dispatch 的，不是再推一次 tag。开发版 PR 的 CI 同样由 workflow dispatch `CI Checks`，因为 token 打开的 PR 不会自动跑 pull_request 工作流。

仓库需要允许 GitHub Actions 创建 PR（Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests），并且 `GITHUB_TOKEN` 有 contents / pull-requests 写权限。本 workflow 已在 job 上声明这些权限。

## 版本规则

基线是最近的 `vX.Y.Z`（不是代码里过期的字符串）。自该 tag 以来：

| 提交 | 版本 |
| --- | --- |
| `BREAKING CHANGE` 或 `type!` | major（`2.5.0` → `3.0.0`） |
| `feat` | minor |
| `fix` / `perf` / `refactor` / `revert` | patch |
| `chore` / `docs` / `style` / `test` / `ci` / `build`、非约定式提交 | 不发版 |
| 作者是 Dependabot | 不发版（即使标题像 `fix`） |

多种提交取最高一级。`fix` 再加 `feat` 得到 minor。版本源只有 `jjz_alert/__version__`；REST API 与 Home Assistant 的 `sw_version` 从这里导入。

## 手动

```bash
scripts/release.sh --dry-run          # 只打印计划，不改文件、不打 tag
scripts/release.sh                    # 让 Actions 按上面的规则开/更新开发版 PR
scripts/release.sh 2.6.0              # 指定版本（仍必须高于最近的 tag）
```

Actions 页面也可以对 `Release` workflow 做 `workflow_dispatch`：

- `mode=prepare`：同上。`version` 可空。
- `mode=publish`：不另开 PR，按当前 `__version__` 打 tag 并发布。用于标题被改掉、自动发布没跑起来时的补救。tag 已存在且不是当前提交则失败。

自己推 `v*` tag 时，仍走原来的 Docker workflow：构建多架构镜像；只有在 GitHub Release 还不存在时才创建 Release（避免覆盖自动发布写好的 notes）。
