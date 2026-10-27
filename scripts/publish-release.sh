#!/usr/bin/env bash
# Annotated tag + non-draft GitHub Release, then dispatch Docker Image Build.
# GITHUB_TOKEN tag pushes do not retrigger on.push workflows, so the image
# build is started with workflow_dispatch on the tag ref (docker-image.yml
# treats refs/tags/* as a release tag, including :latest).
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" && "${RELEASE_ALLOW_LOCAL:-}" != "1" ]]; then
  echo "publish-release.sh runs in GitHub Actions. Recovery: workflow_dispatch mode=publish." >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=${RELEASE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}
cd "$ROOT"

PY=${PYTHON:-python3}
if [[ -n "${GITHUB_SHA:-}" && "$(git rev-parse HEAD)" != "$GITHUB_SHA" ]]; then
  echo "HEAD $(git rev-parse HEAD) is not GITHUB_SHA $GITHUB_SHA" >&2
  exit 1
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
echo "plan action=$action version=$version tag=$tag"
if [[ "$action" != "publish" ]]; then
  echo "refusing to publish (action=$action)" >&2
  exit 1
fi
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "invalid version '$version'" >&2
  exit 1
}
[[ "$tag" == "v$version" ]] || {
  echo "invalid tag '$tag'" >&2
  exit 1
}

git fetch origin --tags --prune
head_sha=$(git rev-parse HEAD)

if git rev-parse -q --verify "refs/tags/${tag}^{}" >/dev/null 2>&1; then
  have=$(git rev-parse "refs/tags/${tag}^{}")
  if [[ "$have" != "$head_sha" ]]; then
    echo "::error::tag $tag already points at $have, not $head_sha"
    exit 1
  fi
  echo "tag $tag already at HEAD"
else
  git -c user.name='github-actions[bot]' \
    -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    -c tag.gpgsign=false \
    tag -a "$tag" -m "$tag" HEAD
  git push origin "refs/tags/${tag}"
  echo "pushed annotated tag $tag"
fi

notes=$(mktemp)
"$PY" "$SCRIPT_DIR/release_plan.py" notes --version "$version" --output "$notes"

if json=$(gh release view "$tag" --json isDraft 2>/dev/null); then
  draft=$(printf '%s' "$json" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["isDraft"])')
  if [[ "$draft" == "True" || "$draft" == "true" ]]; then
    gh release edit "$tag" --draft=false --title "$tag" --notes-file "$notes"
    echo "published existing draft $tag"
  else
    echo "release $tag already published; leaving notes untouched"
  fi
else
  gh release create "$tag" --title "$tag" --notes-file "$notes"
  echo "created release $tag"
fi

runs=$(mktemp)
if gh run list --workflow docker-image.yml --limit 40 \
  --json headBranch,headSha,conclusion,event,status,displayTitle >"$runs"; then
  need=$("$PY" "$SCRIPT_DIR/release_plan.py" docker-needed --tag "$tag" --sha "$head_sha" --runs-file "$runs")
else
  echo "could not list docker runs; dispatching anyway" >&2
  need=yes
fi
need=$(printf '%s' "$need" | tr -d '[:space:]')

if [[ "$need" == "yes" ]]; then
  ok=0
  for delay in 1 2 4 8 16; do
    if gh workflow run docker-image.yml --ref "$tag" -f "version=${tag}"; then
      ok=1
      break
    fi
    echo "workflow_dispatch failed; retrying in ${delay}s" >&2
    sleep "$delay"
  done
  [[ "$ok" == 1 ]]
  echo "dispatched Docker Image Build for $tag"
else
  echo "docker build for $tag already succeeded or is running; not dispatching again"
fi
