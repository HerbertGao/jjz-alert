#!/usr/bin/env bash
# Open or update the single version PR ("开发版 PR") on branch release/version.
# Push to master runs this after checks. Re-runs with the same tree do not
# push another commit or open a second PR.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" && "${RELEASE_ALLOW_LOCAL:-}" != "1" ]]; then
  echo "open-release-pr.sh runs in GitHub Actions. Locally: scripts/release.sh --dry-run" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=${RELEASE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}
cd "$ROOT"

PY=${PYTHON:-python3}
base=${RELEASE_BASE_SHA:-${GITHUB_SHA:-}}
if [[ -z "$base" ]]; then
  echo "GITHUB_SHA (or RELEASE_BASE_SHA) is required" >&2
  exit 1
fi

git fetch origin --tags --prune
if git ls-remote --exit-code --heads origin release/version >/dev/null 2>&1; then
  git fetch origin '+refs/heads/release/version:refs/remotes/origin/release/version'
fi

if [[ "$(git rev-parse HEAD)" != "$base" ]]; then
  git checkout --detach "$base"
fi

plan_file=$(mktemp)
"$PY" "$SCRIPT_DIR/release_plan.py" plan \
  --event "${RELEASE_EVENT:-push}" \
  --mode "${RELEASE_MODE:-}" \
  --force-version "${RELEASE_FORCE_VERSION:-}" \
  --github-output >"$plan_file"

field() {
  awk -v key="$1" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' \
    "$plan_file"
}

action=$(field action)
version=$(field version)
tag=$(field tag)
bump=$(field bump)
previous_tag=$(field previous_tag)
reason=$(field reason)
echo "plan action=$action version=$version tag=$tag"
echo "plan reason=$reason"

if [[ "$action" == "skip" ]]; then
  echo "nothing to release"
  exit 0
fi
if [[ "$action" != "prepare" ]]; then
  echo "refusing to open a version PR (action=$action)" >&2
  exit 1
fi
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "invalid planned version '$version'" >&2
  exit 1
}
[[ "$tag" == "v$version" ]] || {
  echo "invalid planned tag '$tag'" >&2
  exit 1
}

git checkout -B release/version "$base"
"$PY" "$SCRIPT_DIR/release_plan.py" apply --version "$version"
git add -- jjz_alert/__init__.py CHANGELOG.md

if git diff --cached --quiet; then
  echo "version files already match $version; not opening an empty PR"
  git reset --hard HEAD
  exit 0
fi

new_tree=$(git write-tree)
pushed=0
commit_release() {
  git -c user.name='github-actions[bot]' \
    -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    -c commit.gpgsign=false \
    commit -m "chore(release): 版本统一到 ${version}"
}

if git rev-parse --verify --quiet refs/remotes/origin/release/version >/dev/null; then
  remote_tree=$(git rev-parse 'refs/remotes/origin/release/version^{tree}')
  if [[ "$new_tree" == "$remote_tree" ]]; then
    echo "release branch already has this tree"
    git reset --hard HEAD
  else
    commit_release
    expected=$(git rev-parse refs/remotes/origin/release/version)
    git push --force-with-lease="refs/heads/release/version:${expected}" \
      origin "HEAD:refs/heads/release/version"
    pushed=1
  fi
else
  commit_release
  git push origin "HEAD:refs/heads/release/version"
  pushed=1
fi

body=$(mktemp)
"$PY" "$SCRIPT_DIR/release_plan.py" pr-body \
  --version "$version" \
  --bump "$bump" \
  --previous-tag "$previous_tag" \
  --reason "$reason" \
  --output "$body"
title="chore(release): 版本统一到 ${version}"

repo_args=()
if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
  repo_args=(--repo "$GITHUB_REPOSITORY")
fi

existing=$(
  gh pr list "${repo_args[@]}" \
    --head release/version --base master --state open --json number \
    | "$PY" -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["number"] if rows else "")'
)
created=0
if [[ -n "$existing" ]]; then
  gh pr edit "$existing" "${repo_args[@]}" --title "$title" --body-file "$body"
  echo "updated PR #$existing"
else
  gh pr create "${repo_args[@]}" \
    --base master --head release/version --title "$title" --body-file "$body"
  created=1
  echo "opened version PR"
fi

if [[ "$pushed" == 1 || "$created" == 1 ]]; then
  # GITHUB_TOKEN pushes do not trigger pull_request/push workflows.
  gh workflow run ci.yml --ref release/version
  echo "dispatched CI Checks on release/version"
fi
