#!/usr/bin/env bash
# Ask GitHub Actions to open the version PR. This does not tag or publish locally.
#
#   scripts/release.sh --dry-run          # print the plan for HEAD
#   scripts/release.sh                    # dispatch prepare (conventional bump)
#   scripts/release.sh 2.5.1              # dispatch prepare with this version
#   scripts/release.sh 2.5.1 --dry-run
#
# Merging the opened PR publishes the GitHub Release and dispatches the
# existing Docker image workflow. See RELEASE.md.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$ROOT"

die() {
  printf 'release: %s\n' "$*" >&2
  exit "${2:-1}"
}

dry=0
ver=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry=1 ;;
    -h | --help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      [[ -z "$ver" ]] || die "unexpected extra argument '$arg'" 2
      ver="${arg#v}"
      ;;
  esac
done

if [[ -n "$ver" && ! "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "invalid version '$ver' (want N.N.N)" 2
fi

PY=${PYTHON:-python3}

if [[ "$dry" == 1 ]]; then
  if [[ -n "$ver" ]]; then
    "$PY" "$SCRIPT_DIR/release_plan.py" plan \
      --event workflow_dispatch --mode prepare --force-version "$ver" --json
  else
    "$PY" "$SCRIPT_DIR/release_plan.py" plan --event push --json
  fi
  exit 0
fi

command -v gh >/dev/null 2>&1 || die "gh not found"
repo_slug="${RELEASE_REPO_SLUG:-HerbertGao/jjz-alert}"
remote_url=$(git remote get-url --push origin 2>/dev/null || git remote get-url origin 2>/dev/null) ||
  die "cannot read origin remote"
case "$remote_url" in
  "https://github.com/$repo_slug" | "https://github.com/$repo_slug.git" | \
    "git@github.com:$repo_slug.git" | "ssh://git@github.com/$repo_slug.git") ;;
  *)
    die "origin remote '$remote_url' does not match '$repo_slug' (set RELEASE_REPO_SLUG to override)"
    ;;
esac

args=(-f mode=prepare)
if [[ -n "$ver" ]]; then
  args+=(-f "version=$ver")
fi
echo "release: dispatching prepare on $repo_slug${ver:+ ($ver)}"
gh workflow run release.yml --repo "$repo_slug" "${args[@]}"
echo "release: workflow dispatched."
echo "  watch: gh run list --repo $repo_slug --workflow=release.yml --limit 3"
echo "  merge the version PR when CI is green; merging publishes the release."
echo "  releases: https://github.com/$repo_slug/releases"
