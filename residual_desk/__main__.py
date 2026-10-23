"""CLI: python -m residual_desk fixtures/calls.jsonl"""

from __future__ import annotations

import sys
from pathlib import Path

from residual_desk.score import format_details, format_table, score_path

_FLAGS = {"--verbose", "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    unknown = [arg for arg in args if arg.startswith("-") and arg not in _FLAGS]
    if unknown:
        print(f"unknown flag: {unknown[0]}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    verbose = "--verbose" in args
    paths = [arg for arg in args if arg not in _FLAGS]
    if len(paths) != 1 or "--help" in args or "-h" in args:
        print(_usage(), file=sys.stderr if len(paths) != 1 else sys.stdout)
        return 2 if len(paths) != 1 else 0
    try:
        report = score_path(Path(paths[0]))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(format_table(report))
    if verbose:
        print()
        print(format_details(report))
    return 0


def _usage() -> str:
    return "usage: python -m residual_desk [--verbose] <calls.jsonl>"


if __name__ == "__main__":
    raise SystemExit(main())
