#!/usr/bin/env python3
"""
Collect Xiaohongshu post metadata using Playwright with a logged-in browser profile.

This script writes a manual-source JSON file compatible with collect_news.py:
{
  "items": [...]
}

Notes:
- It does not bypass platform controls.
- Use only accounts and URLs you are authorized to access.
- Keep browser profile data local; do not commit it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Xiaohongshu posts via Playwright.")
    parser.add_argument(
        "--urls",
        default="",
        help="Comma-separated share URLs",
    )
    parser.add_argument(
        "--urls-file",
        default="",
        help="Optional text file with one URL per line",
    )
    parser.add_argument(
        "--out-file",
        required=True,
        help="Output JSON file path (manual source format)",
    )
    parser.add_argument(
        "--user-data-dir",
        default="~/.cache/news-summary/xhs-playwright-profile",
        help="Chromium user profile directory for persistent login session",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--channel",
        default="",
        help="Optional browser channel (e.g. chrome, msedge). Overrides bundled chromium.",
    )
    parser.add_argument(
        "--executable-path",
        default="",
        help="Optional browser executable path for Playwright launch",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=20,
        help="Max URLs to process",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout in milliseconds",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=3.0,
        help="Additional wait after page load",
    )
    parser.add_argument(
        "--login-wait-seconds",
        type=int,
        default=0,
        help="Optional login warmup window in seconds (opens xiaohongshu homepage first)",
    )
    parser.add_argument(
        "--now",
        default="",
        help="Optional ISO timestamp override",
    )
    return parser.parse_args()


def utc_now(override: str) -> dt.datetime:
    if override:
        raw = override.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def parse_url_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def read_urls_file(path: str) -> list[str]:
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"URLs file not found: {p}")
    urls: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    return urls


def clean_xhs_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if not parsed.scheme:
        return url.strip()
    # Keep a stable desktop-openable URL; remove one-time share params/tokens.
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    allow_query: list[tuple[str, str]] = []
    for key, value in query_params:
        key_l = key.lower()
        if key_l in {"xsec_token", "xsec_source", "xhsshare", "source"}:
            continue
        allow_query.append((key, value))
    query = urllib.parse.urlencode(allow_query)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def deduplicate_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in urls:
        cleaned = clean_xhs_url(raw)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def first_non_empty(values: list[str]) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return ""


def parse_cn_metric(raw: str) -> float | None:
    if not raw:
        return None
    text = raw.strip().lower().replace(",", "")
    mult = 1.0
    if text.endswith("万"):
        text = text[:-1]
        mult = 10000.0
    elif text.endswith("w"):
        text = text[:-1]
        mult = 10000.0
    try:
        return float(text) * mult
    except ValueError:
        return None


def engagement_level(likes: float | None, comments: float | None, collects: float | None) -> int | None:
    if likes is None and comments is None and collects is None:
        return None
    score = (likes or 0.0) + (comments or 0.0) * 2.0 + (collects or 0.0) * 1.5
    if score >= 100000:
        return 5
    if score >= 30000:
        return 4
    if score >= 8000:
        return 3
    if score >= 2000:
        return 2
    return 1


def infer_category(text: str) -> str:
    hay = text.lower()
    ai_keywords = ["ai", "人工智能", "大模型", "llm", "openai", "机器人", "自动驾驶", "生成式"]
    finance_keywords = ["金融", "股", "a股", "港股", "美股", "利率", "债券", "汇率", "经济", "通胀"]
    politics_keywords = ["时政", "外交", "选举", "战争", "政府", "国会", "议会", "总统", "总理"]
    if any(k in hay for k in ai_keywords):
        return "科技-AI"
    if any(k in hay for k in finance_keywords):
        return "金融"
    if any(k in hay for k in politics_keywords):
        return "时政"
    return "科技-其他"


def main() -> int:
    args = parse_args()
    now = utc_now(args.now)
    channel = args.channel.strip() or "chrome"
    executable_path = args.executable_path.strip()
    urls = parse_url_list(args.urls)
    urls.extend(read_urls_file(args.urls_file))
    urls = deduplicate_urls(urls)[: max(args.max_items, 1)]

    out_path = Path(args.out_file).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not urls:
        payload = {"items": []}
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[WARN] No Xiaohongshu URLs configured. Wrote empty file: {out_path}")
        return 0

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        print("[ERROR] Playwright is not available.")
        print(f"[ERROR] {exc}")
        print("[HINT] Install with: pip3 install playwright (browser channel mode can use local Chrome).")
        return 2

    items: list[dict[str, Any]] = []
    profile_dir = str(Path(args.user_data_dir).expanduser())
    with sync_playwright() as playwright:
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": profile_dir,
            "headless": args.headless,
            "viewport": {"width": 1400, "height": 900},
            "locale": "zh-CN",
        }
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        elif channel:
            launch_kwargs["channel"] = channel

        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = context.new_page()
        page.set_default_timeout(args.timeout_ms)

        if args.login_wait_seconds > 0:
            page.goto("https://www.xiaohongshu.com/", wait_until="domcontentloaded")
            print(
                f"[INFO] Login warmup: please confirm Xiaohongshu login in the opened browser "
                f"within {args.login_wait_seconds} seconds."
            )
            time.sleep(args.login_wait_seconds)

        for idx, url in enumerate(urls, start=1):
            clean_url = clean_xhs_url(url)
            try:
                page.goto(clean_url, wait_until="domcontentloaded")
                if args.wait_seconds > 0:
                    time.sleep(args.wait_seconds)
                data = page.evaluate(
                    """
                    () => {
                      const q = (s) => document.querySelector(s);
                      const meta = (name) => {
                        const p = document.querySelector(`meta[property="${name}"]`);
                        if (p && p.content) return p.content.trim();
                        const n = document.querySelector(`meta[name="${name}"]`);
                        return n && n.content ? n.content.trim() : "";
                      };
                      const title = [
                        meta("og:title"),
                        meta("twitter:title"),
                        q("h1")?.innerText || "",
                        document.title || ""
                      ].find((v) => v && v.trim()) || "";
                      let summary = [
                        meta("og:description"),
                        meta("description"),
                        q("article")?.innerText || "",
                        q("main")?.innerText || ""
                      ].find((v) => v && v.trim()) || "";
                      summary = summary.replace(/\\s+/g, " ").trim();
                      if (summary.length > 240) summary = summary.slice(0, 240);

                      const author = (
                        q('a[href*="/user/profile/"]')?.innerText ||
                        q('[class*="author"]')?.innerText ||
                        ""
                      ).replace(/\\s+/g, " ").trim();

                      const body = (document.body?.innerText || "").replace(/\\s+/g, " ");
                      const first = (arr) => arr.find(Boolean) || "";
                      const pick = (patterns) => {
                        for (const re of patterns) {
                          const m = body.match(re);
                          if (m && m[1]) return m[1];
                        }
                        return "";
                      };
                      const likes = pick([/点赞\\s*([\\d,.]+[万wW]?)/, /赞\\s*([\\d,.]+[万wW]?)/]);
                      const comments = pick([/评论\\s*([\\d,.]+[万wW]?)/]);
                      const collects = pick([/收藏\\s*([\\d,.]+[万wW]?)/]);

                      return {
                        title,
                        summary,
                        author,
                        likes,
                        comments,
                        collects,
                        final_url: window.location.href || ""
                      };
                    }
                    """
                )
            except PlaywrightTimeoutError as exc:
                print(f"[WARN] Timeout on URL: {clean_url} ({exc})")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] Failed URL: {clean_url} ({exc})")
                continue

            title = first_non_empty([str(data.get("title", "")), f"小红书帖子 {idx}"])
            final_url = clean_xhs_url(first_non_empty([str(data.get("final_url", "")), clean_url]))
            author = str(data.get("author", "")).strip()
            summary = str(data.get("summary", "")).strip()
            likes_raw = str(data.get("likes", "")).strip()
            comments_raw = str(data.get("comments", "")).strip()
            collects_raw = str(data.get("collects", "")).strip()

            likes = parse_cn_metric(likes_raw)
            comments = parse_cn_metric(comments_raw)
            collects = parse_cn_metric(collects_raw)
            engage = engagement_level(likes, comments, collects)

            cat_text = f"{title} {summary} {author}"
            category_hint = infer_category(cat_text)
            summary_bits = [summary] if summary else []
            metric_text = " ".join(
                part
                for part in [
                    f"点赞{likes_raw}" if likes_raw else "",
                    f"评论{comments_raw}" if comments_raw else "",
                    f"收藏{collects_raw}" if collects_raw else "",
                ]
                if part
            )
            if metric_text:
                summary_bits.append(metric_text)
            summary_hint = "；".join(summary_bits)[:300]
            editorial_prominence = 5 if idx <= 2 else (4 if idx <= 6 else 3)

            items.append(
                {
                    "title": title,
                    "url": final_url,
                    "source": f"小红书 @{author}" if author else "小红书",
                    "source_group": "social_community",
                    "category_hint": category_hint,
                    "summary_hint": summary_hint,
                    "published_at": now.isoformat(),
                    "hotness_signals": {
                        "editorial_prominence": editorial_prominence,
                        "engagement_velocity": engage,
                        "cross_source_pickup": None,
                        "source_authority": 1 if not author else 2,
                        "public_impact_scope": None,
                    },
                }
            )
            print(f"[OK] Captured: {title[:80]}")

        context.close()

    payload = {"items": items}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Xiaohongshu manual-source JSON written: {out_path}")
    print(f"[OK] Items captured: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
