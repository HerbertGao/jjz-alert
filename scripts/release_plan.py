#!/usr/bin/env python3
"""发版计划 / 写版本号 / 生成说明。供 workflow 与 scripts/release.sh 调用。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from release_version import (
    Plan,
    ReleaseError,
    apply_version,
    commits_for_version,
    default_image,
    docker_dispatch_needed,
    load_runs,
    plan_repo,
    render_pr_body,
    render_release_notes,
)


def _root(value: str) -> Path:
    return Path(value).resolve()


def _print_plan(args: argparse.Namespace) -> int:
    plan = plan_repo(
        _root(args.root),
        event=args.event,
        mode=args.mode,
        force_version=args.force_version,
    )
    if args.github_output and args.json:
        print("::error::pass only one of --github-output and --json", file=sys.stderr)
        return 2
    if args.github_output:
        sys.stdout.write(plan.github_output())
        summary = os_summary()
        if summary is not None:
            text = (
                f"### Release plan\n\n"
                f"- action: `{plan.action}`\n"
                f"- version: `{plan.version or '-'}`\n"
                f"- {plan.reason}\n"
            )
            with summary.open("a", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    json.dump(plan.as_dict(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def os_summary() -> Path | None:
    raw = os.environ.get("GITHUB_STEP_SUMMARY")
    return Path(raw) if raw else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="print the release decision")
    plan.add_argument("--event", default="push")
    plan.add_argument("--mode", default="")
    plan.add_argument("--force-version", default="")
    plan.add_argument("--github-output", action="store_true")
    plan.add_argument(
        "--json",
        action="store_true",
        help="print JSON (this is the default unless --github-output)",
    )

    apply = sub.add_parser("apply", help="write __version__ and CHANGELOG.md")
    apply.add_argument("--version", required=True)

    notes = sub.add_parser("notes", help="write GitHub Release notes")
    notes.add_argument("--version", required=True)
    notes.add_argument("--output", required=True)

    body = sub.add_parser("pr-body", help="write the version PR body")
    body.add_argument("--version", required=True)
    body.add_argument("--bump", default="")
    body.add_argument("--previous-tag", default="")
    body.add_argument("--reason", default="")
    body.add_argument("--output", required=True)

    docker = sub.add_parser(
        "docker-needed", help="print yes/no for dispatching the image workflow"
    )
    docker.add_argument("--tag", required=True)
    docker.add_argument("--sha", required=True)
    docker.add_argument("--runs-file", required=True)

    args = parser.parse_args(argv)
    root = _root(args.root)
    try:
        if args.cmd == "plan":
            return _print_plan(args)
        if args.cmd == "apply":
            apply_version(root, args.version)
            return 0
        if args.cmd == "notes":
            commits = commits_for_version(root, args.version)
            text = render_release_notes(args.version, commits, default_image())
            Path(args.output).write_text(text, encoding="utf-8")
            return 0
        if args.cmd == "pr-body":
            plan = Plan(
                action="prepare",
                version=args.version,
                tag=f"v{args.version.lstrip('vV')}",
                bump=args.bump,
                previous_tag=args.previous_tag,
                reason=args.reason,
            )
            text = render_pr_body(plan, commits_for_version(root, args.version))
            Path(args.output).write_text(text, encoding="utf-8")
            return 0
        if args.cmd == "docker-needed":
            needed = docker_dispatch_needed(
                load_runs(Path(args.runs_file)), tag=args.tag, sha=args.sha
            )
            sys.stdout.write("yes\n" if needed else "no\n")
            return 0
    except ReleaseError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    sys.exit(main())
