#!/usr/bin/env python3
"""
Render markdown digest into a styled HTML document for email.

This script uses a minimal markdown renderer to avoid third-party dependencies.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


CSS = """
body {
  margin: 0;
  padding: 0;
  background: #f4f6f8;
  color: #1a1a1a;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
}
.wrap {
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 16px 36px;
}
.card {
  background: #ffffff;
  border: 1px solid #e6e9ee;
  border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 4px 16px rgba(0,0,0,.04);
}
h1 { font-size: 28px; margin: 0 0 14px; color: #111827; }
h2 { font-size: 22px; margin: 26px 0 10px; color: #111827; border-bottom: 1px solid #eceff3; padding-bottom: 6px; }
h3 { font-size: 18px; margin: 18px 0 8px; color: #1f2937; }
p { margin: 10px 0; line-height: 1.75; font-size: 15px; }
ul, ol { margin: 8px 0 12px 22px; line-height: 1.7; }
li { margin: 4px 0; }
code {
  background: #f2f4f7;
  border: 1px solid #e7ebf0;
  border-radius: 5px;
  padding: 1px 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 90%;
}
a { color: #0f62fe; text-decoration: none; }
a:hover { text-decoration: underline; }
pre {
  background: #111827;
  color: #f8fafc;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  line-height: 1.5;
}
blockquote {
  margin: 12px 0;
  border-left: 4px solid #dbe2ea;
  padding: 4px 12px;
  color: #4b5563;
  background: #f9fbfd;
}
.footer {
  margin-top: 16px;
  color: #6b7280;
  font-size: 12px;
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render markdown digest to HTML.")
    parser.add_argument("--input", required=True, help="Input markdown file path")
    parser.add_argument("--output", required=True, help="Output HTML file path")
    parser.add_argument(
        "--title",
        default="Daily Hot News Digest",
        help="HTML <title> value",
    )
    return parser.parse_args()


def inline_format(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(md_text: str) -> str:
    lines = md_text.splitlines()
    parts: list[str] = []
    in_ul = False
    in_ol = False
    in_pre = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            if in_pre:
                parts.append("</pre>")
                in_pre = False
            else:
                parts.append("<pre>")
                in_pre = True
            continue

        if in_pre:
            parts.append(html.escape(line))
            continue

        if not stripped:
            close_lists()
            continue

        if stripped.startswith("### "):
            close_lists()
            parts.append(f"<h3>{inline_format(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            close_lists()
            parts.append(f"<h2>{inline_format(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            close_lists()
            parts.append(f"<h1>{inline_format(stripped[2:])}</h1>")
            continue

        if stripped.startswith("> "):
            close_lists()
            parts.append(f"<blockquote>{inline_format(stripped[2:])}</blockquote>")
            continue

        ul_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul_match:
            if in_ol:
                parts.append("</ol>")
                in_ol = False
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{inline_format(ul_match.group(1))}</li>")
            continue

        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if not in_ol:
                parts.append("<ol>")
                in_ol = True
            parts.append(f"<li>{inline_format(ol_match.group(1))}</li>")
            continue

        close_lists()
        parts.append(f"<p>{inline_format(stripped)}</p>")

    close_lists()
    if in_pre:
        parts.append("</pre>")

    return "\n".join(parts)


def build_document(title: str, body_html: str) -> str:
    title_escaped = html.escape(title)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{title_escaped}</title>\n"
        f"  <style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class=\"wrap\">\n"
        "    <div class=\"card\">\n"
        f"{body_html}\n"
        "      <div class=\"footer\">Generated by Hot News Daily Brief pipeline.</div>\n"
        "    </div>\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def main() -> int:
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        raise FileNotFoundError(f"Input markdown not found: {in_path}")

    md_text = in_path.read_text(encoding="utf-8")
    body = markdown_to_html(md_text)
    doc = build_document(args.title, body)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"[OK] HTML written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
