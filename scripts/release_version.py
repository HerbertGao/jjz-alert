"""jjz-alert 发版决策。

不依赖 npm / changesets。版本基线是最近的 ``vX.Y.Z`` tag，下一版本按
自该 tag 以来的 Conventional Commits 计算：

- ``BREAKING CHANGE`` 或 ``type!`` → major
- ``feat`` → minor
- ``fix`` / ``perf`` / ``refactor`` / ``revert`` → patch
- ``chore`` / ``docs`` / ``style`` / ``test`` / ``ci`` / ``build``、非约定式提交、
  Dependabot 提交 → 不触发发版

``workflow_dispatch`` 可以指定版本，用来发布上述「不自动发版」的改动。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERSION_RELATIVE = Path("jjz_alert") / "__init__.py"
CHANGELOG_RELATIVE = Path("CHANGELOG.md")

_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_VERSION_LINE = re.compile(
    r'^(?P<prefix>__version__\s*=\s*)(?P<quote>["\'])(?P<value>[^"\']+)(?P=quote)',
    re.M,
)
_HEADER = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s+(?P<rest>.+)$"
)
_BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.M)
_RELEASE_LINE = re.compile(
    r"^chore\(release\):\s*版本统一到\s+v?([0-9]+\.[0-9]+\.[0-9]+)\b"
)
_MERGE_RELEASE = re.compile(r"^Merge pull request #\d+ from \S+/release/version\s*$")
_MERGE_BRANCH = re.compile(r"^Merge branch 'release/version'(?: into \S+)?\s*$")

_MINOR = {"feat"}
_PATCH = {"fix", "perf", "refactor", "revert"}
_RANK = {"patch": 1, "minor": 2, "major": 3}

_GROUPS = (
    ("major", "不兼容变更"),
    ("feat", "新功能"),
    ("fix", "修复"),
    ("refactor", "性能与重构"),
    ("other", "其他"),
)

CHANGELOG_HEADER = """# Changelog

版本号来源是 `jjz_alert/__version__`。开发版 PR 在合并前写入对应小节。

`v2.5.0` 及更早的发布没有写入本文件，见
[GitHub Releases](https://github.com/HerbertGao/jjz-alert/releases)。
"""


class ReleaseError(Exception):
    """发版输入不合法，或仓库状态不允许继续。"""


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    email: str
    subject: str
    body: str

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass(frozen=True)
class Plan:
    action: str
    version: str = ""
    tag: str = ""
    bump: str = ""
    previous_tag: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "version": self.version,
            "tag": self.tag,
            "bump": self.bump,
            "previous_tag": self.previous_tag,
            "reason": self.reason,
        }

    def github_output(self) -> str:
        lines = []
        for key, value in self.as_dict().items():
            flat = value.replace("\r", " ").replace("\n", " ").strip()
            lines.append(f"{key}={flat}")
        return "\n".join(lines) + "\n"


def parse_version(value: str) -> tuple[int, int, int]:
    raw = value.strip()
    if raw.startswith("v") or raw.startswith("V"):
        raw = raw[1:]
    match = _SEMVER.fullmatch(raw)
    if not match:
        raise ReleaseError(f"invalid version {value!r} (want N.N.N, no leading v)")
    return tuple(int(part) for part in match.groups())


def format_version(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def normalize_version(value: str) -> str:
    return format_version(parse_version(value))


def bump_version(version: str, level: str) -> str:
    major, minor, patch = parse_version(version)
    if level == "major":
        return format_version((major + 1, 0, 0))
    if level == "minor":
        return format_version((major, minor + 1, 0))
    if level == "patch":
        return format_version((major, minor, patch + 1))
    raise ReleaseError(f"unknown bump level {level!r}")


def highest_bump(levels: list[str | None]) -> str | None:
    best: str | None = None
    for level in levels:
        if level is None:
            continue
        if level not in _RANK:
            raise ReleaseError(f"unknown bump level {level!r}")
        if best is None or _RANK[level] > _RANK[best]:
            best = level
    return best


def release_version_from_line(line: str) -> str | None:
    match = _RELEASE_LINE.match(line.strip())
    if not match:
        return None
    try:
        return normalize_version(match.group(1))
    except ReleaseError:
        return None


def head_release_version(message: str) -> str | None:
    """识别「这一次 push 就是开发版 PR 的合并」。

    只看首行，或 merge commit 正文里的版本行。普通提交正文里引用同一句话
    不会被当成发布。
    """

    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return None
    subject = lines[0]
    from_subject = release_version_from_line(subject)
    if from_subject and subject.startswith("chore(release):"):
        return from_subject
    if _MERGE_RELEASE.match(subject) or _MERGE_BRANCH.match(subject):
        for line in lines[1:]:
            found = release_version_from_line(line)
            if found:
                return found
        return ""
    return None


def is_release_commit(commit: Commit) -> bool:
    return release_version_from_line(commit.subject) is not None


def is_dependabot(commit: Commit) -> bool:
    blob = f"{commit.author} {commit.email}".lower()
    return "dependabot" in blob


def bump_for(commit: Commit) -> str | None:
    if is_dependabot(commit) or is_release_commit(commit):
        return None
    match = _HEADER.match(commit.subject.strip())
    if not match:
        return None
    kind = match.group("type").lower()
    breaking = bool(match.group("bang")) or bool(_BREAKING.search(commit.body))
    if breaking:
        return "major"
    if kind in _MINOR:
        return "minor"
    if kind in _PATCH:
        return "patch"
    return None


def commit_bucket(commit: Commit) -> str:
    if is_release_commit(commit):
        return ""
    match = _HEADER.match(commit.subject.strip())
    kind = match.group("type").lower() if match else ""
    breaking = bool(match and match.group("bang")) or bool(
        _BREAKING.search(commit.body)
    )
    if breaking:
        return "major"
    if kind == "feat":
        return "feat"
    if kind == "fix":
        return "fix"
    if kind in {"perf", "refactor", "revert"}:
        return "refactor"
    return "other"


def render_changelog_body(commits: list[Commit]) -> str:
    buckets: dict[str, list[str]] = {key: [] for key, _title in _GROUPS}
    for commit in commits:
        bucket = commit_bucket(commit)
        if not bucket:
            continue
        buckets[bucket].append(f"- {commit.subject.strip()} ({commit.short})")
    parts: list[str] = []
    for key, title in _GROUPS:
        lines = buckets[key]
        if not lines:
            continue
        parts.append(f"### {title}\n" + "\n".join(lines))
    if not parts:
        return "- 无提交说明\n"
    return "\n\n".join(parts) + "\n"


def render_changelog_section(version: str, date: str, commits: list[Commit]) -> str:
    version = normalize_version(version)
    return f"## [{version}] - {date}\n\n{render_changelog_body(commits)}"


def _assemble_changelog(prefix: str, block: str, suffix: str) -> str:
    parts = [part.strip() for part in (prefix, block, suffix) if part and part.strip()]
    return "\n\n".join(parts) + "\n"


def upsert_changelog(existing: str, version: str, section: str) -> str:
    version = normalize_version(version)
    block = section.strip()
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)",
        re.M | re.S,
    )
    if pattern.search(existing):
        without = pattern.sub("\0", existing, count=1)
        prefix, suffix = without.split("\0", 1)
        return _assemble_changelog(prefix, block, suffix)
    if not existing.strip():
        return _assemble_changelog(CHANGELOG_HEADER, block, "")
    match = re.search(r"^## \[", existing, re.M)
    if match:
        return _assemble_changelog(
            existing[: match.start()], block, existing[match.start() :]
        )
    return _assemble_changelog(existing, block, "")


def read_version_text(text: str) -> str:
    matches = list(_VERSION_LINE.finditer(text))
    if len(matches) != 1:
        raise ReleaseError(
            f"expected exactly one __version__ assignment, found {len(matches)}"
        )
    return normalize_version(matches[0].group("value"))


def write_version_text(text: str, version: str) -> str:
    version = normalize_version(version)
    matches = list(_VERSION_LINE.finditer(text))
    if len(matches) != 1:
        raise ReleaseError(
            f"expected exactly one __version__ assignment, found {len(matches)}"
        )
    match = matches[0]
    start, end = match.span("value")
    return text[:start] + version + text[end:]


def default_image(repository: str | None = None) -> str:
    slug = repository or os.environ.get("GITHUB_REPOSITORY") or "HerbertGao/jjz-alert"
    return f"ghcr.io/{slug.lower()}"


def render_release_notes(
    version: str, commits: list[Commit], image: str | None = None
) -> str:
    version = normalize_version(version)
    image = image or default_image()
    tag = f"v{version}"
    body = render_changelog_body(commits).rstrip()
    return (
        "## Docker 镜像\n\n"
        "支持架构：`linux/amd64`、`linux/arm64`\n\n"
        "```sh\n"
        f"docker pull {image}:{tag}\n"
        f"docker pull {image}:latest\n"
        "```\n\n"
        "## 变更\n\n"
        f"{body}\n\n"
        "---\n"
        "_由 `.github/workflows/release.yml` 发布。"
        "版本源：`jjz_alert/__version__`。_\n"
    )


def render_pr_body(plan: Plan, commits: list[Commit]) -> str:
    version = normalize_version(plan.version)
    bump = plan.bump or "auto"
    previous = plan.previous_tag or "(none)"
    changes = render_changelog_body(commits).rstrip()
    return (
        "开发版 PR（版本 PR）。合并到 `master` 后，Release workflow 会：\n\n"
        f"1. 创建 annotated tag `v{version}`（tag 已存在且指向别的提交则失败，不覆盖）\n"
        "2. 发布**非 draft** GitHub Release（已经发布过则不改 release notes）\n"
        "3. `workflow_dispatch` 现有的 Docker Image Build，在该 tag 上构建并推送\n"
        f"   `ghcr.io/herbertgao/jjz-alert:v{version}` 与 `:latest`\n\n"
        f"本次计划：`{previous}` → `{version}`（{bump}）。{plan.reason}\n\n"
        "## 自上次正式 tag 起的提交\n\n"
        f"{changes}\n\n"
        "不要在这个 PR 里夹带功能改动。版本规则见 `RELEASE.md`。\n"
    )


_ACTIVE_RUN_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}


def _run_blocks_redispatch(run: dict) -> bool:
    conclusion = run.get("conclusion") or ""
    status = run.get("status") or ""
    return conclusion == "success" or status in _ACTIVE_RUN_STATUSES


def docker_dispatch_needed(runs: list[dict], *, tag: str, sha: str) -> bool:
    """tag 上还没有成功或进行中的 Docker Image Build 时才需要再 dispatch。"""

    for run in runs:
        if (run.get("headBranch") or "") != tag:
            continue
        head_sha = run.get("headSha") or ""
        if sha and head_sha and head_sha != sha:
            continue
        if _run_blocks_redispatch(run):
            return False
    return True


def ci_dispatch_needed(runs: list[dict], *, sha: str) -> bool:
    """开发版分支这个 SHA 还没有成功或进行中的 CI 时才需要再 dispatch。"""

    for run in runs:
        if (run.get("headSha") or "") != sha:
            continue
        branch = run.get("headBranch") or ""
        if branch not in {"", "release/version"}:
            continue
        if _run_blocks_redispatch(run):
            return False
    return True


def release_concurrency_scope(
    *,
    event: str,
    message: str = "",
    mode: str = "",
    sha: str,
    ref: str,
) -> str:
    """发布与准备分开排队。

    GitHub 在 ``cancel-in-progress: false`` 时仍只保留同一 group 里最新的
    pending run。发布按提交 SHA 单独成组，后面的 master push 挤不掉它。
    准备共享 ``prepare-<ref>``，只留最新一次。
    """

    text = message or ""
    publish = (event == "workflow_dispatch" and mode == "publish") or (
        event == "push"
        and ("chore(release): 版本统一到" in text or "release/version" in text)
    )
    if publish:
        return f"publish-{sha}"
    return f"prepare-{ref}"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def list_semver_tags(repo: Path) -> list[tuple[tuple[int, int, int], str]]:
    raw = git(repo, "tag", "--list", "v*")
    found: list[tuple[tuple[int, int, int], str]] = []
    for line in raw.splitlines():
        name = line.strip()
        if not name:
            continue
        try:
            parsed = parse_version(name)
        except ReleaseError:
            continue
        found.append((parsed, f"v{format_version(parsed)}"))
    found.sort()
    return found


def tag_before(
    tags: list[tuple[tuple[int, int, int], str]], version: str
) -> str | None:
    target = parse_version(version)
    prior = [name for parsed, name in tags if parsed < target]
    return prior[-1] if prior else None


def tag_named(tags: list[tuple[tuple[int, int, int], str]], version: str) -> str | None:
    target = parse_version(version)
    for parsed, name in tags:
        if parsed == target:
            return name
    return None


def load_commits(repo: Path, tag: str) -> list[Commit]:
    if not tag:
        return []
    raw = git(repo, "log", "--no-merges", "--format=%H", f"{tag}..HEAD")
    commits: list[Commit] = []
    for sha in raw.split():
        show = git(repo, "show", "-s", "--format=%an%n%ae%n%s%n%b", sha)
        parts = show.split("\n", 3)
        while len(parts) < 4:
            parts.append("")
        author, email, subject, body = parts
        commits.append(
            Commit(
                sha=sha,
                author=author,
                email=email,
                subject=subject,
                body=body.rstrip("\n"),
            )
        )
    return commits


def read_version(path: Path) -> str:
    return read_version_text(path.read_text(encoding="utf-8"))


def head_message(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%B")


def head_date(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%cs").strip()


def _plan(
    *,
    action: str,
    version: str = "",
    bump: str = "",
    previous_tag: str = "",
    reason: str = "",
) -> Plan:
    tag = f"v{normalize_version(version)}" if version else ""
    return Plan(
        action=action,
        version=normalize_version(version) if version else "",
        tag=tag,
        bump=bump,
        previous_tag=previous_tag,
        reason=reason,
    )


def plan_repo(
    root: Path,
    *,
    event: str = "push",
    mode: str = "",
    force_version: str = "",
) -> Plan:
    root = Path(root)
    code = read_version(root / VERSION_RELATIVE)
    tags = list_semver_tags(root)
    latest = tags[-1][1] if tags else ""
    latest_version = format_version(tags[-1][0]) if tags else ""
    message = head_message(root)
    event = (event or "push").strip()
    mode = (mode or "").strip()
    if mode not in {"", "prepare", "publish"}:
        raise ReleaseError(f"unknown release mode {mode!r}")
    forced = normalize_version(force_version) if force_version.strip() else ""

    if event == "workflow_dispatch" and mode == "publish":
        version = forced or code
        if version != code:
            raise ReleaseError(
                f"publish version {version} != __version__ {code}; "
                "open a version PR before publishing"
            )
        previous = tag_before(tags, version) or ""
        return _plan(
            action="publish",
            version=version,
            bump="explicit" if forced else "release",
            previous_tag=previous,
            reason="workflow_dispatch publish",
        )

    if event == "push":
        released = head_release_version(message)
        if released is not None:
            version = released or code
            if not version:
                raise ReleaseError("release commit did not include a version")
            if version != code:
                raise ReleaseError(
                    f"release commit says {version} but __version__ is {code}"
                )
            previous = tag_before(tags, version) or ""
            return _plan(
                action="publish",
                version=version,
                bump="release",
                previous_tag=previous,
                reason="merged version PR",
            )

    if forced:
        if latest_version and parse_version(forced) <= parse_version(latest_version):
            raise ReleaseError(f"{forced} is not newer than existing tag {latest}")
        return _plan(
            action="prepare",
            version=forced,
            bump="explicit",
            previous_tag=latest,
            reason=f"workflow_dispatch 指定版本 {forced}",
        )

    if not latest_version:
        raise ReleaseError("no semver tag found; pass an explicit version to release")

    commits = load_commits(root, latest)
    level = highest_bump([bump_for(commit) for commit in commits])
    if level is None:
        return _plan(
            action="skip",
            version=latest_version,
            previous_tag=latest,
            reason=(
                f"自 {latest} 起没有需要发版的提交"
                "（dependabot、chore/docs/style/test/ci/build 与非约定式提交不计）"
            ),
        )

    nxt = bump_version(latest_version, level)
    if parse_version(code) > parse_version(nxt):
        nxt = code
        level = "explicit"
    if tag_named(tags, nxt):
        return _plan(
            action="skip",
            version=nxt,
            bump=level,
            previous_tag=latest,
            reason=f"v{nxt} 已经存在，不重复开开发版 PR",
        )
    releasable = sum(1 for commit in commits if bump_for(commit))
    return _plan(
        action="prepare",
        version=nxt,
        bump=level,
        previous_tag=latest,
        reason=f"{level}：自 {latest} 起 {releasable} 个可发布提交",
    )


def commits_for_version(root: Path, version: str) -> list[Commit]:
    tags = list_semver_tags(root)
    previous = tag_before(tags, version) or ""
    return load_commits(root, previous)


def apply_version(root: Path, version: str, *, date: str | None = None) -> None:
    root = Path(root)
    version = normalize_version(version)
    init_path = root / VERSION_RELATIVE
    init_path.write_text(
        write_version_text(init_path.read_text(encoding="utf-8"), version),
        encoding="utf-8",
    )
    changelog_path = root / CHANGELOG_RELATIVE
    existing = (
        changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
    )
    section = render_changelog_section(
        version, date or head_date(root), commits_for_version(root, version)
    )
    changelog_path.write_text(
        upsert_changelog(existing, version, section), encoding="utf-8"
    )


def load_runs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(data, list):
        raise ReleaseError("docker run list must be a JSON array")
    return data
