#!/usr/bin/env python3
"""拒绝 Release 工作流认不出的 PR 标题。

判定与 ``scripts/release_version.py`` 的 ``_HEADER`` / ``bump_for`` 相同：
标题必须是 ``type(可选scope)可选!: 说明``。``docs`` / ``chore`` 等不抬版本的
类型仍然通过。纯中文、冒号后没有空格的标题会失败——squash merge 会把 PR
标题变成 master 上的提交首行，这种首行会被分类为 skip。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_version import is_conventional_subject  # noqa: E402


def title_from(argv: list[str]) -> str:
    if argv:
        return " ".join(argv).strip()
    return os.environ.get("PR_TITLE", "").strip()


def main(argv: list[str] | None = None) -> int:
    title = title_from(list(sys.argv[1:] if argv is None else argv))
    if is_conventional_subject(title):
        print(f"conventional title: {title}")
        return 0
    print(
        "PR 标题不是约定式提交。squash 之后它会成为 master 上的提交首行，"
        "Release 工作流会把它算作 skip，不会自动打开开发版 PR。\n"
        "格式：type(可选scope): 说明\n"
        "例如：feat(api): 增加按令牌绑定车牌的最新进京证查询接口\n"
        "冒号后要有空格。类型是 ASCII 单词，中文说明放在冒号后面。\n"
        "docs / chore / style / test / ci / build 可以通过本检查，但不会自动发版。\n"
        f"实际标题：{title!r}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
