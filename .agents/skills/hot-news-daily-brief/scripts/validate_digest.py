#!/usr/bin/env python3
"""
Validate markdown digest quality gates before sending email.

Checks:
1) Each story has an English summary with a minimum word count.
2) Daily overall summary exists and is around target Chinese-character length.
3) Source health section exists and contains success/failure subsections.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SECTION_HEADERS = ["[时政]", "[金融]", "[科技-AI]", "[科技-其他]"]
OPTIONAL_SECTION_HEADERS = ["[X 热点]"]
REQUIRED_TOP5_CATEGORY_TAGS = {"时政", "金融", "科技-AI", "科技-其他"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate daily digest markdown quality gates.")
    parser.add_argument("--input", required=True, help="Path to markdown digest file")
    parser.add_argument(
        "--min-english-words",
        type=int,
        default=200,
        help="Minimum English words required for each story summary (default: 200)",
    )
    parser.add_argument(
        "--overall-cn-min",
        type=int,
        default=240,
        help="Minimum Chinese characters for overall summary (default: 240)",
    )
    parser.add_argument(
        "--overall-cn-max",
        type=int,
        default=380,
        help="Maximum Chinese characters for overall summary (default: 380)",
    )
    parser.add_argument(
        "--skip-source-health-check",
        action="store_true",
        help="Skip source health section validation",
    )
    return parser.parse_args()


def read_text(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Digest file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def extract_section(text: str, header_prefix: str) -> str:
    # Match "## <header_prefix...>" until next top-level section.
    pattern = rf"^##\s+{re.escape(header_prefix)}[^\n]*\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def split_story_blocks(section_body: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^###\s+\d+\)\s+(.+)$", section_body, flags=re.MULTILINE))
    blocks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section_body)
        block = section_body[start:end].strip()
        blocks.append((title, block))
    return blocks


def extract_english_summary_block(story_block: str) -> str:
    lines = story_block.splitlines()
    start_idx = -1
    first_line_payload = ""

    for idx, line in enumerate(lines):
        if re.match(r"^\s*-\s*English summary", line, flags=re.IGNORECASE):
            start_idx = idx
            parts = line.split(":", 1)
            if len(parts) == 2:
                first_line_payload = parts[1].strip()
            break

    if start_idx < 0:
        return ""

    collected: list[str] = []
    if first_line_payload:
        collected.append(first_line_payload)

    stop_pattern = re.compile(
        r"^\s*-\s*(中文总结|Source URL|Published time|English word count|Why hot)\b",
        flags=re.IGNORECASE,
    )

    for line in lines[start_idx + 1 :]:
        if stop_pattern.match(line):
            break
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        collected.append(stripped)

    return " ".join(collected).strip()


def count_english_words(text: str) -> int:
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    return len(words)


def count_chinese_chars(text: str) -> int:
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    return len(chars)


def validate_overall_summary(
    full_text: str, min_cn: int, max_cn: int, errors: list[str], info: list[str]
) -> None:
    body = extract_section(full_text, "当日总体总结")
    if not body:
        errors.append("Missing section: ## 当日总体总结（约300字）")
        return
    cn_count = count_chinese_chars(body)
    info.append(f"Overall summary Chinese chars: {cn_count}")
    if cn_count < min_cn or cn_count > max_cn:
        errors.append(
            f"Overall summary Chinese chars out of range: {cn_count} "
            f"(expected {min_cn}-{max_cn})"
        )


def validate_source_health(full_text: str, errors: list[str]) -> None:
    body = extract_section(full_text, "数据源抓取与有效性")
    if not body:
        errors.append("Missing section: ## 数据源抓取与有效性（过去24小时）")
        return

    if "### 成功抓取" not in body:
        errors.append("Source health section missing subsection: ### 成功抓取")
    if "### 抓取失败或不可用" not in body:
        errors.append("Source health section missing subsection: ### 抓取失败或不可用")

    bullet_count = len(re.findall(r"^\s*-\s+.+$", body, flags=re.MULTILINE))
    if bullet_count < 4:
        errors.append("Source health section has too few bullet lines (<4)")


def validate_story_english_words(
    full_text: str, min_words: int, errors: list[str], info: list[str]
) -> None:
    story_count = 0
    checked_count = 0
    sections_to_check = list(SECTION_HEADERS)
    for optional in OPTIONAL_SECTION_HEADERS:
        if extract_section(full_text, optional):
            sections_to_check.append(optional)

    for section in sections_to_check:
        section_body = extract_section(full_text, section)
        if not section_body:
            continue
        if "无可信高热度新闻" in section_body and "###" not in section_body:
            continue

        blocks = split_story_blocks(section_body)
        if 0 < len(blocks) < 3:
            errors.append(f"{section}: requires Top3 stories, but found {len(blocks)}")

        for title, block in blocks:
            story_count += 1
            summary = extract_english_summary_block(block)
            if not summary:
                errors.append(f"[{section}] {title}: missing English summary block")
                continue
            checked_count += 1
            words = count_english_words(summary)
            info.append(f"[{section}] {title}: English words={words}")
            if words < min_words:
                errors.append(
                    f"[{section}] {title}: English summary too short ({words} < {min_words})"
                )

    if story_count == 0:
        errors.append("No story blocks found under category sections.")
    elif checked_count == 0:
        errors.append("No valid English summary blocks found in story sections.")


def validate_top5_structure(full_text: str, errors: list[str], info: list[str]) -> None:
    body = extract_section(full_text, "Top 5 Most Important")
    if not body:
        errors.append("Missing section: ## Top 5 Most Important (Cross-Category)")
        return

    lines = [
        line.strip()
        for line in body.splitlines()
        if re.match(r"^\d+\.\s+\[[^\]]+\]\s+.+", line.strip())
    ]
    if len(lines) != 5:
        errors.append(f"Top 5 section must have exactly 5 ranked lines, found {len(lines)}")
        return

    found_tags: set[str] = set()
    for line in lines:
        match = re.match(r"^\d+\.\s+\[([^\]]+)\]\s+.+", line)
        if match:
            found_tags.add(match.group(1).strip())
    info.append(f"Top5 category tags: {', '.join(sorted(found_tags))}")

    missing = REQUIRED_TOP5_CATEGORY_TAGS - found_tags
    if missing:
        errors.append(
            "Top 5 must include each section champion at least once; missing tags: "
            + ", ".join(sorted(missing))
        )


def main() -> int:
    args = parse_args()

    try:
        text = read_text(args.input)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    info: list[str] = []

    validate_overall_summary(
        full_text=text,
        min_cn=args.overall_cn_min,
        max_cn=args.overall_cn_max,
        errors=errors,
        info=info,
    )
    validate_top5_structure(full_text=text, errors=errors, info=info)
    if not args.skip_source_health_check:
        validate_source_health(full_text=text, errors=errors)
    validate_story_english_words(
        full_text=text,
        min_words=args.min_english_words,
        errors=errors,
        info=info,
    )

    if errors:
        for err in errors:
            print(f"[ERROR] {err}", file=sys.stderr)
        return 1

    print("[OK] Digest validation passed.")
    for line in info:
        print(f"[OK] {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
