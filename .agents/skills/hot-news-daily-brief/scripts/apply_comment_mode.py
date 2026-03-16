#!/usr/bin/env python3
"""
Apply comment output mode for digest markdown.

Modes:
- off: remove each '- 评论:' block before sending.
- on: keep report unchanged.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply comment mode to digest markdown.")
    parser.add_argument("--input", required=True, help="Path to markdown digest file")
    parser.add_argument(
        "--mode",
        choices=["off", "on"],
        default="off",
        help="Comment mode: off removes '- 评论:' blocks, on keeps file unchanged.",
    )
    return parser.parse_args()


def remove_comment_blocks(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    removed = 0
    i = 0

    next_field_pattern = re.compile(
        r"^\s*-\s*(English word count|Source URL|Published time|Why hot|English summary|中文翻译|中文总结)\b",
        flags=re.IGNORECASE,
    )

    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*-\s*评论\s*:", line):
            removed += 1
            i += 1
            while i < len(lines):
                probe = lines[i]
                if next_field_pattern.match(probe) or re.match(r"^###\s+\d+\)", probe) or re.match(
                    r"^##\s+", probe
                ):
                    break
                i += 1
            continue

        out.append(line)
        i += 1

    suffix = "\n" if text.endswith("\n") else ""
    return ("\n".join(out) + suffix), removed


def main() -> int:
    args = parse_args()
    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(f"Digest file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if args.mode == "on":
        print("[OK] Comment mode=on (no changes).")
        return 0

    updated, removed = remove_comment_blocks(text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    print(f"[OK] Comment mode=off applied, removed blocks: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
