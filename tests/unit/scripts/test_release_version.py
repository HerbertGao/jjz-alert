"""开发版 PR 的版本决策、changelog，以及 open/publish 脚本的幂等性。"""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"

import sys

sys.path.insert(0, str(SCRIPTS))

from release_version import (  # noqa: E402
    Commit,
    ReleaseError,
    apply_version,
    bump_for,
    bump_version,
    docker_dispatch_needed,
    highest_bump,
    list_semver_tags,
    parse_version,
    plan_repo,
    read_version_text,
    render_changelog_body,
    upsert_changelog,
    write_version_text,
)


def _env(**extra):
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    env.setdefault("GIT_AUTHOR_NAME", "Test")
    env.setdefault("GIT_AUTHOR_EMAIL", "t@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Test")
    env.setdefault("GIT_COMMITTER_EMAIL", "t@example.com")
    env.update(extra)
    return env


def _run(repo, *args, env=None):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=_env(**(env or {})),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {args} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _commit(repo, message, *, author=("Test", "t@example.com"), body=""):
    name, email = author
    env = {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
    _run(repo, "add", "-A", env=env)
    cmd = ["commit", "-m", message]
    if body:
        cmd.extend(["-m", body])
    _run(repo, *cmd, env=env)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "init", "-b", "master")
    _run(path, "config", "user.email", "t@example.com")
    _run(path, "config", "user.name", "Test")
    package = path / "jjz_alert"
    package.mkdir()
    (package / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (path / "CHANGELOG.md").write_text("# Changelog\n\nseed\n", encoding="utf-8")
    _commit(path, "chore: init")
    _run(path, "tag", "v1.2.3")
    return path


def _bare_origin(repo: Path, bare: Path):
    subprocess.run(
        ["git", "init", "--bare", "-b", "master", str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    _run(repo, "remote", "add", "origin", str(bare))
    _run(repo, "push", "origin", "HEAD:master", "v1.2.3")


def _write_fake_gh(bin_dir: Path, log: Path, state: Path):
    bin_dir.mkdir()
    script = bin_dir / "gh"
    script.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path({str(log)!r})
state_path = Path({str(state)!r})
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args, ensure_ascii=False) + "\\n")

def load():
    if state_path.exists() and state_path.read_text(encoding="utf-8").strip():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {{"prs": [], "release": None, "runs": []}}

def save(data):
    state_path.write_text(json.dumps(data), encoding="utf-8")

data = load()
cmd = args[0] if args else ""
if cmd == "pr" and "list" in args:
    print(json.dumps([{{"number": number}} for number in data["prs"]]))
    raise SystemExit(0)
if cmd == "pr" and "create" in args:
    data["prs"].append(len(data["prs"]) + 1)
    save(data)
    print("https://example.test/pull/%s" % data["prs"][-1])
    raise SystemExit(0)
if cmd == "pr" and "edit" in args:
    raise SystemExit(0)
if cmd == "release" and "view" in args:
    if not data.get("release"):
        print("release not found", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({{"isDraft": data["release"]["draft"]}}))
    raise SystemExit(0)
if cmd == "release" and "create" in args:
    if data.get("release"):
        print("release exists", file=sys.stderr)
        raise SystemExit(1)
    data["release"] = {{"draft": False}}
    save(data)
    raise SystemExit(0)
if cmd == "release" and "edit" in args:
    data["release"] = {{"draft": False}}
    save(data)
    raise SystemExit(0)
if cmd == "run" and "list" in args:
    print(json.dumps(data["runs"]))
    raise SystemExit(0)
if cmd == "workflow" and "run" in args:
    workflow = args[args.index("run") + 1]
    ref = args[args.index("--ref") + 1] if "--ref" in args else ""
    if workflow == "docker-image.yml":
        data["runs"].append({{
            "headBranch": ref,
            "headSha": os.environ.get("GITHUB_SHA", ""),
            "conclusion": "success",
            "status": "completed",
            "event": "workflow_dispatch",
            "displayTitle": ref,
        }})
        save(data)
    raise SystemExit(0)
print("unhandled gh", args, file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _gh_log(log: Path):
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _script_env(repo, *, sha, log, state, bin_dir, **extra):
    env = _env(
        RELEASE_ALLOW_LOCAL="1",
        RELEASE_ROOT=str(repo),
        GITHUB_SHA=sha,
        GITHUB_REPOSITORY="HerbertGao/jjz-alert",
        GH_LOG=str(log),
        GH_STATE=str(state),
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    env.update(extra)
    return env


def _run_script(name, env):
    return subprocess.run(
        ["bash", str(SCRIPTS / name)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_bump_table():
    assert bump_version("2.5.0", "patch") == "2.5.1"
    assert bump_version("2.5.0", "minor") == "2.6.0"
    assert bump_version("2.5.0", "major") == "3.0.0"
    assert bump_version("2.9.0", "minor") == "2.10.0"
    assert parse_version("v2.5.0") == (2, 5, 0)
    with pytest.raises(ReleaseError):
        parse_version("01.2.3")
    with pytest.raises(ReleaseError):
        parse_version("1.2")


def test_commit_classification():
    def commit(subject, body="", author="Ada", email="ada@example.com"):
        return Commit("abcdef1234567890", author, email, subject, body)

    assert bump_for(commit("fix: close the gate")) == "patch"
    assert bump_for(commit("feat: add a sensor")) == "minor"
    assert bump_for(commit("perf: speed up redis")) == "patch"
    assert bump_for(commit("refactor: split the client")) == "patch"
    assert bump_for(commit("fix!: drop the field")) == "major"
    assert bump_for(commit("fix: tweak", "BREAKING CHANGE: payload changed")) == "major"
    assert bump_for(commit("docs: rewrite the readme")) is None
    assert bump_for(commit("chore(deps): bump aiohttp")) is None
    assert bump_for(commit("ci: retrigger docker")) is None
    assert bump_for(commit("update something")) is None
    assert bump_for(commit("chore(release): 版本统一到 2.5.1")) is None
    assert (
        bump_for(
            commit(
                "fix: security bump",
                author="dependabot[bot]",
                email="49699333+dependabot[bot]@users.noreply.github.com",
            )
        )
        is None
    )
    assert highest_bump(["patch", None, "minor"]) == "minor"
    assert highest_bump(["minor", "major"]) == "major"
    assert highest_bump([None, None]) is None


def test_changelog_groups_and_upsert_are_stable():
    commits = [
        Commit("a" * 40, "Ada", "a@ex", "feat: add sensor", ""),
        Commit("b" * 40, "Ada", "a@ex", "fix: close gate", ""),
        Commit(
            "c" * 40,
            "dependabot[bot]",
            "dependabot@ex",
            "chore(deps): bump aiohttp",
            "",
        ),
        Commit("d" * 40, "Bot", "b@ex", "chore(release): 版本统一到 1.2.4", ""),
    ]
    body = render_changelog_body(commits)
    assert "### 新功能" in body
    assert "feat: add sensor (aaaaaaa)" in body
    assert "### 修复" in body
    assert "### 其他" in body
    assert "chore(release)" not in body

    section = f"## [1.2.4] - 2026-10-27\n\n{body}"
    once = upsert_changelog("# Changelog\n\nseed\n", "1.2.4", section)
    twice = upsert_changelog(once, "1.2.4", section)
    assert once == twice
    assert once.index("## [1.2.4]") < once.index("seed") or "seed" in once
    assert once.count("## [1.2.4]") == 1


def test_version_edit_keeps_the_rest_of_the_file():
    source = '"""pkg"""\n\n__version__ = "1.2.3"\n\n__all__ = ["__version__"]\n'
    assert read_version_text(source) == "1.2.3"
    updated = write_version_text(source, "1.2.4")
    assert '__version__ = "1.2.4"' in updated
    assert '__all__ = ["__version__"]' in updated
    assert write_version_text(updated, "1.2.4") == updated


def test_semver_tag_sort_is_numeric(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _run(repo, "tag", "v1.9.0")
    _run(repo, "tag", "v1.10.0")
    assert list_semver_tags(repo)[-1][1] == "v1.10.0"


def test_plan_patch_minor_major_and_noise(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "note.txt").write_text("docs\n", encoding="utf-8")
    _commit(repo, "docs: notes")
    assert plan_repo(repo, event="push").action == "skip"

    (repo / "note.txt").write_text("deps\n", encoding="utf-8")
    _commit(
        repo,
        "chore(deps): bump aiohttp from 1 to 2",
        author=(
            "dependabot[bot]",
            "49699333+dependabot[bot]@users.noreply.github.com",
        ),
    )
    assert plan_repo(repo, event="push").action == "skip"

    (repo / "note.txt").write_text("fix\n", encoding="utf-8")
    _commit(
        repo,
        "fix: close the gate",
        body="see chore(release): 版本统一到 9.9.9 in the discussion",
    )
    plan = plan_repo(repo, event="push")
    assert plan.action == "prepare"
    assert plan.version == "1.2.4"
    assert plan.bump == "patch"
    assert plan.tag == "v1.2.4"

    (repo / "note.txt").write_text("feat\n", encoding="utf-8")
    _commit(repo, "feat: add a sensor")
    assert plan_repo(repo, event="push").version == "1.3.0"

    (repo / "note.txt").write_text("break\n", encoding="utf-8")
    _commit(repo, "feat!: remove the legacy payload")
    assert plan_repo(repo, event="push").version == "2.0.0"


def test_plan_publish_recognizes_squash_and_merge(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    init_py = repo / "jjz_alert" / "__init__.py"
    init_py.write_text('__version__ = "1.2.4"\n', encoding="utf-8")
    _commit(repo, "chore(release): 版本统一到 1.2.4 (#41)")
    plan = plan_repo(repo, event="push")
    assert plan.action == "publish"
    assert plan.version == "1.2.4"

    init_py.write_text('__version__ = "1.2.5"\n', encoding="utf-8")
    _commit(
        repo,
        "Merge pull request #42 from HerbertGao/release/version",
        body="chore(release): 版本统一到 1.2.5\n",
    )
    assert plan_repo(repo, event="push").version == "1.2.5"

    init_py.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    _commit(repo, "chore(release): 版本统一到 1.2.4")
    with pytest.raises(ReleaseError, match="__version__"):
        plan_repo(repo, event="push")


def test_explicit_version_and_dispatch_publish(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    with pytest.raises(ReleaseError, match="not newer"):
        plan_repo(
            repo,
            event="workflow_dispatch",
            mode="prepare",
            force_version="1.2.3",
        )
    plan = plan_repo(
        repo,
        event="workflow_dispatch",
        mode="prepare",
        force_version="1.4.0",
    )
    assert plan.action == "prepare"
    assert plan.version == "1.4.0"
    assert plan.bump == "explicit"

    published = plan_repo(repo, event="workflow_dispatch", mode="publish")
    assert published.action == "publish"
    assert published.version == "1.2.3"


def test_apply_is_idempotent(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "note.txt").write_text("fix\n", encoding="utf-8")
    _commit(repo, "fix: close the gate")
    apply_version(repo, "1.2.4", date="2026-10-27")
    version = (repo / "jjz_alert" / "__init__.py").read_text(encoding="utf-8")
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert '__version__ = "1.2.4"' in version
    assert "fix: close the gate" in changelog
    apply_version(repo, "1.2.4", date="2026-10-27")
    assert (repo / "jjz_alert" / "__init__.py").read_text(encoding="utf-8") == version
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == changelog


def test_docker_dispatch_skips_success_and_in_progress_only_for_the_tag():
    sha = "abc123"
    runs = [
        {
            "headBranch": "master",
            "headSha": sha,
            "conclusion": "success",
            "status": "completed",
        },
        {
            "headBranch": "v1.2.4",
            "headSha": "other",
            "conclusion": "success",
            "status": "completed",
        },
    ]
    assert docker_dispatch_needed(runs, tag="v1.2.4", sha=sha) is True
    runs.append(
        {
            "headBranch": "v1.2.4",
            "headSha": sha,
            "conclusion": "",
            "status": "in_progress",
        }
    )
    assert docker_dispatch_needed(runs, tag="v1.2.4", sha=sha) is False


def test_shell_scripts_parse():
    for name in ("open-release-pr.sh", "publish-release.sh", "release.sh"):
        subprocess.run(["bash", "-n", str(SCRIPTS / name)], check=True)


def test_open_release_pr_is_idempotent_and_skips_dependabot(tmp_path):
    noise = _init_repo(tmp_path / "noise")
    bare_noise = tmp_path / "noise.git"
    _bare_origin(noise, bare_noise)
    (noise / "note.txt").write_text("dep\n", encoding="utf-8")
    _commit(
        noise,
        "chore(deps): bump aiohttp from 1 to 2",
        author=(
            "dependabot[bot]",
            "49699333+dependabot[bot]@users.noreply.github.com",
        ),
    )
    _run(noise, "push", "origin", "HEAD:master")
    sha = _run(noise, "rev-parse", "HEAD").strip()
    log = tmp_path / "noise-gh.log"
    state = tmp_path / "noise-gh.json"
    bin_dir = tmp_path / "noise-bin"
    _write_fake_gh(bin_dir, log, state)
    result = _run_script(
        "open-release-pr.sh",
        _script_env(noise, sha=sha, log=log, state=state, bin_dir=bin_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to release" in result.stdout
    heads = subprocess.check_output(
        [
            "git",
            "--git-dir",
            str(bare_noise),
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads",
        ],
        text=True,
    )
    assert "refs/heads/release/version" not in heads
    assert _gh_log(log) == []

    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "origin.git"
    _bare_origin(repo, bare)
    (repo / "note.txt").write_text("fix\n", encoding="utf-8")
    _commit(repo, "fix: close the gate")
    _run(repo, "push", "origin", "HEAD:master")
    sha = _run(repo, "rev-parse", "HEAD").strip()
    log = tmp_path / "gh.log"
    state = tmp_path / "gh.json"
    bin_dir = tmp_path / "bin"
    _write_fake_gh(bin_dir, log, state)
    env = _script_env(repo, sha=sha, log=log, state=state, bin_dir=bin_dir)

    first = _run_script("open-release-pr.sh", env)
    assert first.returncode == 0, first.stdout + first.stderr
    version = subprocess.check_output(
        [
            "git",
            "--git-dir",
            str(bare),
            "show",
            "release/version:jjz_alert/__init__.py",
        ],
        text=True,
    )
    assert '__version__ = "1.2.4"' in version
    subject = subprocess.check_output(
        ["git", "--git-dir", str(bare), "log", "-1", "--format=%s", "release/version"],
        text=True,
    ).strip()
    assert subject == "chore(release): 版本统一到 1.2.4"
    changelog = subprocess.check_output(
        ["git", "--git-dir", str(bare), "show", "release/version:CHANGELOG.md"],
        text=True,
    )
    assert "fix: close the gate" in changelog
    first_cmds = _gh_log(log)
    assert sum(1 for cmd in first_cmds if cmd[:2] == ["pr", "create"]) == 1
    assert sum(1 for cmd in first_cmds if cmd[:2] == ["workflow", "run"]) == 1
    assert "ci.yml" in first_cmds[-1]
    sha_before = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/heads/release/version"],
        text=True,
    ).strip()

    second = _run_script("open-release-pr.sh", env)
    assert second.returncode == 0, second.stdout + second.stderr
    sha_after = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/heads/release/version"],
        text=True,
    ).strip()
    assert sha_before == sha_after
    second_cmds = _gh_log(log)[len(first_cmds) :]
    assert ["pr", "create"] not in [cmd[:2] for cmd in second_cmds]
    assert sum(1 for cmd in second_cmds if cmd[:2] == ["pr", "edit"]) == 1
    assert sum(1 for cmd in second_cmds if cmd[:2] == ["workflow", "run"]) == 0
    tags = subprocess.check_output(["git", "--git-dir", str(bare), "tag"], text=True)
    assert "v1.2.4" not in tags.split()


def test_publish_release_is_idempotent_and_does_not_move_tags(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "origin.git"
    _bare_origin(repo, bare)
    init_py = repo / "jjz_alert" / "__init__.py"
    init_py.write_text('__version__ = "1.2.4"\n', encoding="utf-8")
    (repo / "note.txt").write_text("ship\n", encoding="utf-8")
    _commit(repo, "fix: close the gate")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.2.4] - 2026-10-27\n", encoding="utf-8"
    )
    _commit(repo, "chore(release): 版本统一到 1.2.4")
    _run(repo, "push", "origin", "HEAD:master")
    sha = _run(repo, "rev-parse", "HEAD").strip()
    log = tmp_path / "gh.log"
    state = tmp_path / "gh.json"
    bin_dir = tmp_path / "bin"
    _write_fake_gh(bin_dir, log, state)
    env = _script_env(
        repo,
        sha=sha,
        log=log,
        state=state,
        bin_dir=bin_dir,
        RELEASE_EVENT="push",
    )

    first = _run_script("publish-release.sh", env)
    assert first.returncode == 0, first.stdout + first.stderr
    tag_sha = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/v1.2.4^{}"],
        text=True,
    ).strip()
    assert tag_sha == sha
    assert sum(1 for cmd in _gh_log(log) if cmd[:2] == ["release", "create"]) == 1
    assert any(
        cmd[:2] == ["workflow", "run"] and "docker-image.yml" in cmd
        for cmd in _gh_log(log)
    )
    tag_object = _run(repo, "rev-parse", "refs/tags/v1.2.4").strip()

    second = _run_script("publish-release.sh", env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "already published" in second.stdout
    assert "not dispatching again" in second.stdout
    assert _run(repo, "rev-parse", "refs/tags/v1.2.4").strip() == tag_object
    assert sum(1 for cmd in _gh_log(log) if cmd[:2] == ["release", "create"]) == 1

    moved = _init_repo(tmp_path / "moved")
    moved_bare = tmp_path / "moved.git"
    _bare_origin(moved, moved_bare)
    (moved / "jjz_alert" / "__init__.py").write_text(
        '__version__ = "1.2.4"\n', encoding="utf-8"
    )
    _commit(moved, "chore: bump ahead of the tag")
    _run(moved, "tag", "v1.2.4")
    _run(moved, "push", "origin", "HEAD:master", "v1.2.4")
    old = _run(moved, "rev-parse", "HEAD").strip()
    (moved / "note.txt").write_text("later\n", encoding="utf-8")
    _commit(moved, "chore(release): 版本统一到 1.2.4")
    later = _run(moved, "rev-parse", "HEAD").strip()
    _run(moved, "push", "origin", "HEAD:master")
    log2 = tmp_path / "moved-gh.log"
    state2 = tmp_path / "moved-gh.json"
    bin2 = tmp_path / "moved-bin"
    _write_fake_gh(bin2, log2, state2)
    failed = _run_script(
        "publish-release.sh",
        _script_env(moved, sha=later, log=log2, state=state2, bin_dir=bin2),
    )
    assert failed.returncode != 0
    assert "already points at" in failed.stdout + failed.stderr
    assert (
        subprocess.check_output(
            ["git", "--git-dir", str(moved_bare), "rev-parse", "refs/tags/v1.2.4^{}"],
            text=True,
        ).strip()
        == old
    )
