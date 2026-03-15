#!/usr/bin/env python3
"""
Collect Reddit/X social signals through a logged-in Playwright browser session.

Output is written as manual-source JSON for collect_news.py ingestion:
{
  "items": [...]
}
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect social posts via Playwright.")
    parser.add_argument("--out-file", required=True, help="Output manual JSON path")
    parser.add_argument(
        "--reddit-subreddits",
        default="news,worldnews,technology,artificial",
        help="Comma-separated subreddit list",
    )
    parser.add_argument(
        "--x-handles",
        default="",
        help="Comma-separated X handles (without @)",
    )
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=20,
        help="Max items per subreddit/handle",
    )
    parser.add_argument(
        "--require-reddit-items",
        type=int,
        default=0,
        help="Fail with non-zero exit when total Reddit items are below this number",
    )
    parser.add_argument(
        "--require-x-items",
        type=int,
        default=0,
        help="Fail with non-zero exit when total X items are below this number",
    )
    parser.add_argument(
        "--user-data-dir",
        default="~/.cache/news-summary/social-playwright-profile",
        help="Persistent Chromium profile path for login sessions",
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
        "--login-wait-seconds",
        type=int,
        default=0,
        help="Warmup login window in seconds (opens reddit.com then x.com)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout in ms",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=3.0,
        help="Extra wait after page load",
    )
    parser.add_argument(
        "--human-delay-min-seconds",
        type=float,
        default=1.5,
        help="Minimum random delay before navigations/actions",
    )
    parser.add_argument(
        "--human-delay-max-seconds",
        type=float,
        default=4.0,
        help="Maximum random delay before navigations/actions",
    )
    parser.add_argument(
        "--source-cooldown-seconds",
        type=float,
        default=6.0,
        help="Cooldown between subreddit/handle collections",
    )
    parser.add_argument(
        "--stealth-login",
        action="store_true",
        help="Reduce automation fingerprints for login pages (helps Google SSO flows)",
    )
    parser.add_argument(
        "--now",
        default="",
        help="Optional ISO timestamp override",
    )
    return parser.parse_args()


def parse_csv(raw: str) -> list[str]:
    if not raw:
        return []
    return [x.strip().lstrip("@") for x in raw.split(",") if x.strip()]


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


def keyword_match(haystack: str, keyword: str) -> bool:
    key = keyword.strip().lower()
    if not key:
        return False
    if re.search(r"[a-z0-9]", key):
        pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return key in haystack


AI_KEYWORDS = {
    "ai",
    "artificial intelligence",
    "llm",
    "gpt",
    "openai",
    "anthropic",
    "deepmind",
    "gemini",
    "claude",
    "人工智能",
    "大模型",
    "机器人",
}
FINANCE_KEYWORDS = {
    "stock",
    "stocks",
    "market",
    "markets",
    "fed",
    "interest rate",
    "inflation",
    "bond",
    "oil",
    "earnings",
    "ipo",
    "economy",
    "gdp",
    "股市",
    "美股",
    "港股",
    "a股",
    "汇率",
    "通胀",
    "债券",
}
POLITICS_KEYWORDS = {
    "election",
    "president",
    "prime minister",
    "congress",
    "parliament",
    "war",
    "sanction",
    "government",
    "conflict",
    "ukraine",
    "gaza",
    "iran",
    "russia",
    "taiwan",
    "外交",
    "选举",
    "战争",
    "冲突",
    "政府",
}


def infer_category(text: str, default: str = "科技-其他") -> str:
    haystack = (text or "").lower()
    if any(keyword_match(haystack, k) for k in AI_KEYWORDS):
        return "科技-AI"
    if any(keyword_match(haystack, k) for k in POLITICS_KEYWORDS):
        return "时政"
    if any(keyword_match(haystack, k) for k in FINANCE_KEYWORDS):
        return "金融"
    return default


REDDIT_BLOCK_MARKERS = [
    "you've been blocked by network security",
    "to continue, log in to your reddit account or use your developer token",
]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def bounded_range(min_seconds: float, max_seconds: float) -> tuple[float, float]:
    low = max(0.0, min_seconds)
    high = max(0.0, max_seconds)
    if high < low:
        low, high = high, low
    return low, high


def human_pause(min_seconds: float, max_seconds: float) -> float:
    low, high = bounded_range(min_seconds, max_seconds)
    if high <= 0:
        return 0.0
    duration = low if high == low else random.uniform(low, high)
    time.sleep(duration)
    return duration


def post_load_settle(page: Any, wait_seconds: float, delay_min: float, delay_max: float) -> None:
    if wait_seconds > 0:
        # Base settle time plus jitter lowers obvious automation timing signatures.
        low_jitter = max(0.0, delay_min * 0.25)
        high_jitter = max(low_jitter, delay_max * 0.5)
        time.sleep(wait_seconds + random.uniform(low_jitter, high_jitter))
    try:
        page.mouse.wheel(0, random.randint(320, 980))
        human_pause(0.25, 0.9)
    except Exception:
        pass


def dismiss_x_upgrade_modal(page: Any) -> bool:
    selectors = [
        'div[role="dialog"] button[aria-label="Close"]',
        'div[role="dialog"] [aria-label="Close"]',
        'div[role="dialog"] button[aria-label="关闭"]',
        'div[role="dialog"] [aria-label="关闭"]',
        'div[role="dialog"] button:has-text("Close")',
        'div[role="dialog"] button:has-text("关闭")',
        'div[role="dialog"] button:has-text("Not now")',
        'div[role="dialog"] button:has-text("暂不")',
    ]
    dismissed = False
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 3)
        except Exception:
            continue
        for index in range(count):
            try:
                button = locator.nth(index)
                if not button.is_visible(timeout=700):
                    continue
                button.click(timeout=2000)
                dismissed = True
                time.sleep(0.5)
                break
            except Exception:
                continue
        if dismissed:
            break
    return dismissed


def norm_reddit_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("/"):
        return "https://www.reddit.com" + url
    return url


def norm_x_status_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("/"):
        url = "https://x.com" + url
    parsed = urllib.parse.urlsplit(url.strip())
    path = re.sub(r"/+$", "", parsed.path)
    status_match = re.match(r"^/([A-Za-z0-9_]+)/status/([0-9]+)", path)
    if status_match:
        return f"https://x.com/{status_match.group(1)}/status/{status_match.group(2)}"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_web_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    parsed = urllib.parse.urlsplit(raw)
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query_items if not k.lower().startswith("utm_")]
    new_query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, ""))


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", " ", text, flags=re.I)
    cleaned = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_compact_number(raw: Any) -> int:
    if isinstance(raw, (int, float)):
        return max(0, int(raw))
    text = str(raw or "").strip().lower().replace(",", "")
    if not text:
        return 0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb]|万|亿)?", text, flags=re.I)
    if not match:
        return 0
    value = float(match.group(1))
    unit = (match.group(2) or "").lower()
    factor = 1.0
    if unit == "k":
        factor = 1_000.0
    elif unit == "m":
        factor = 1_000_000.0
    elif unit == "b":
        factor = 1_000_000_000.0
    elif unit == "万":
        factor = 10_000.0
    elif unit == "亿":
        factor = 100_000_000.0
    return max(0, int(value * factor))


def engagement_velocity_from_score(score: float) -> int | None:
    if score <= 0:
        return None
    if score >= 20_000:
        return 5
    if score >= 8_000:
        return 4
    if score >= 2_500:
        return 3
    if score >= 600:
        return 2
    return 1


def compute_x_engagement_score(reply_count: int, repost_count: int, like_count: int, view_count: int) -> float:
    # Weigh repost and view signals higher to prioritize widely diffused posts.
    return (
        float(reply_count) * 1.0
        + float(repost_count) * 2.0
        + float(like_count) * 1.4
        + float(view_count) * 0.02
    )


def should_try_fetch_link(url: str) -> bool:
    normalized = normalize_web_url(url)
    if not normalized:
        return False
    parsed = urllib.parse.urlsplit(normalized)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if scheme not in {"http", "https"}:
        return False
    if not host:
        return False
    blocked_hosts = {
        "x.com",
        "www.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        "pbs.twimg.com",
        "video.twimg.com",
        "pic.x.com",
        "abs.twimg.com",
        "platform.twitter.com",
    }
    if host in blocked_hosts:
        return False
    if host.endswith(".twimg.com"):
        return False
    lower_path = parsed.path.lower()
    blocked_exts = (
        ".js",
        ".css",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".mp4",
        ".m3u8",
        ".woff",
        ".woff2",
    )
    if lower_path.endswith(blocked_exts):
        return False
    return True


def fetch_link_context(url: str, timeout: int = 12, max_bytes: int = 220_000) -> dict[str, str] | None:
    candidate = normalize_web_url(url)
    if not candidate:
        return None
    request = urllib.request.Request(
        candidate,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = normalize_web_url(response.geturl() or candidate)
            content_type = str(response.headers.get("Content-Type", "")).lower()
            body = response.read(max_bytes)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None
    except Exception:
        return None

    result: dict[str, str] = {"url": final_url}
    if "text/html" not in content_type and b"<html" not in body[:2048].lower():
        return result

    text = body.decode("utf-8", errors="replace")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if title_match:
        title = strip_html(title_match.group(1))
        if title:
            result["title"] = title[:220]

    meta_patterns = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    ]
    description = ""
    for pattern in meta_patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            description = strip_html(match.group(1))
            if description:
                break

    if not description:
        for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.I | re.S):
            candidate_paragraph = strip_html(paragraph)
            if len(candidate_paragraph) >= 60:
                description = candidate_paragraph
                break

    if description:
        result["summary"] = description[:360]
    return result


def extract_external_links_from_status_page(
    status_url: str,
    *,
    timeout: int = 10,
    max_bytes: int = 260_000,
    limit: int = 3,
) -> list[str]:
    canonical_status = norm_x_status_url(status_url)
    if not canonical_status:
        return []
    request = urllib.request.Request(
        canonical_status,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    except Exception:
        return []

    text = body.decode("utf-8", errors="replace")
    candidates: list[str] = []
    candidates.extend(re.findall(r"https?://[^\s\"'<>\\]+", text))
    escaped = re.findall(r"https:\\\\/\\\\/[^\s\"'<>\\]+", text)
    candidates.extend(item.replace("\\/", "/") for item in escaped)

    resolved: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_web_url(html.unescape(candidate))
        if not normalized:
            continue
        if normalized == canonical_status:
            continue
        if not should_try_fetch_link(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
        if len(resolved) >= limit:
            break
    return resolved


def collect_reddit_subreddit(
    page: Any,
    subreddit: str,
    now: dt.datetime,
    max_items: int,
    wait_seconds: float,
    delay_min: float,
    delay_max: float,
) -> tuple[list[dict[str, Any]], str]:
    urls = [
        f"https://www.reddit.com/r/{subreddit}/hot/",
        f"https://old.reddit.com/r/{subreddit}/hot/",
    ]
    rows: list[dict[str, Any]] = []
    blocked_detected = False

    for url in urls:
        try:
            human_pause(delay_min, delay_max)
            page.goto(url, wait_until="domcontentloaded")
            post_load_settle(page, wait_seconds, delay_min, delay_max)
            body_text = page.locator("body").inner_text().lower()
            if any(marker in body_text for marker in REDDIT_BLOCK_MARKERS):
                blocked_detected = True
                continue
            rows = page.evaluate(
                """
                () => {
                  const out = [];
                  const push = (title, href, score, comments) => {
                    if (!title || !href) return;
                    out.push({ title: title.trim(), href: href.trim(), score: score || "", comments: comments || "" });
                  };

                  // new reddit style
                  const articleNodes = Array.from(document.querySelectorAll('article'));
                  for (const a of articleNodes) {
                    const titleNode = a.querySelector('h3');
                    const linkNode = a.querySelector('a[href*="/comments/"]');
                    if (!titleNode || !linkNode) continue;
                    const scoreNode = a.querySelector('[id*="vote-arrows"]') || a.querySelector('[aria-label*="upvote"]');
                    const commentNode = Array.from(a.querySelectorAll('a')).find((n) => /comment/i.test(n.textContent || ""));
                    push(
                      titleNode.textContent || "",
                      linkNode.getAttribute('href') || "",
                      scoreNode ? (scoreNode.textContent || "").trim() : "",
                      commentNode ? (commentNode.textContent || "").trim() : ""
                    );
                  }

                  // old reddit style fallback
                  const things = Array.from(document.querySelectorAll('.thing'));
                  for (const t of things) {
                    const titleLink = t.querySelector('a.title');
                    if (!titleLink) continue;
                    const scoreNode = t.querySelector('.score.unvoted');
                    const commentNode = t.querySelector('a.comments');
                    push(
                      titleLink.textContent || "",
                      titleLink.getAttribute('href') || "",
                      scoreNode ? (scoreNode.textContent || "").trim() : "",
                      commentNode ? (commentNode.textContent || "").trim() : ""
                    );
                  }

                  return out;
                }
                """
            )
            if rows:
                break
        except Exception:
            continue

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, row in enumerate(rows, start=1):
        if len(items) >= max_items:
            break
        title = str(row.get("title", "")).strip()
        link = norm_reddit_url(str(row.get("href", "")).strip())
        if not title or not link or link in seen:
            continue
        seen.add(link)
        summary_hint = " ".join(
            [
                str(row.get("score", "")).strip(),
                str(row.get("comments", "")).strip(),
            ]
        ).strip()
        category_hint = infer_category(f"{title} {summary_hint}", default="科技-其他")
        editorial = 5 if rank <= 3 else (4 if rank <= 10 else 3)
        items.append(
            {
                "title": title,
                "url": link,
                "source": f"Reddit (Playwright) r/{subreddit}",
                "source_group": "social_community",
                "category_hint": category_hint,
                "summary_hint": summary_hint,
                "published_at": now.isoformat(),
                "hotness_signals": {
                    "editorial_prominence": editorial,
                    "engagement_velocity": None,
                    "cross_source_pickup": None,
                    "source_authority": 2,
                    "public_impact_scope": None,
                },
            }
        )
    if items:
        return items, "ok"
    if blocked_detected:
        return [], "blocked"
    return [], "empty"


def collect_x_handle(
    page: Any,
    handle: str,
    now: dt.datetime,
    max_items: int,
    wait_seconds: float,
    delay_min: float,
    delay_max: float,
) -> list[dict[str, Any]]:
    clean_handle = handle.lstrip("@").strip().lower()
    if not clean_handle:
        return []
    url = f"https://x.com/{clean_handle}"
    rows: list[dict[str, Any]] = []
    try:
        waits = [wait_seconds]
        if wait_seconds < 8.0:
            waits.append(8.0)
        for current_wait in waits:
            human_pause(delay_min, delay_max)
            page.goto(url, wait_until="domcontentloaded")
            post_load_settle(page, current_wait, delay_min, delay_max)
            if dismiss_x_upgrade_modal(page):
                print(f"[INFO] X @{clean_handle}: dismissed upgrade/subscription modal.")
                human_pause(0.4, 1.1)
            rows = page.evaluate(
                """
                (targetHandle) => {
                  const out = [];
                  const lower = String(targetHandle || "").toLowerCase();
                  const toAbs = (href) => {
                    try {
                      return new URL(href, location.origin).toString();
                    } catch {
                      return String(href || "").trim();
                    }
                  };
                  const canonicalStatus = (href) => {
                    const abs = toAbs(href);
                    const match = abs.match(
                      /https?:\\/\\/(?:www\\.|mobile\\.)?(?:x|twitter)\\.com\\/([A-Za-z0-9_]+)\\/status\\/(\\d+)/i
                    );
                    if (match) {
                      return `https://x.com/${match[1]}/status/${match[2]}`;
                    }
                    const webMatch = abs.match(
                      /https?:\\/\\/(?:www\\.|mobile\\.)?(?:x|twitter)\\.com\\/i\\/web\\/status\\/(\\d+)/i
                    );
                    if (webMatch) {
                      return `https://x.com/i/web/status/${webMatch[1]}`;
                    }
                    return "";
                  };
                  const metricText = (article, testid) => {
                    const node = article.querySelector(`[data-testid="${testid}"]`);
                    return node ? (node.textContent || "").trim() : "";
                  };
                  const articles = Array.from(document.querySelectorAll('article'));
                  for (const article of articles) {
                    const socialContext = (article.querySelector('[data-testid="socialContext"]')?.textContent || "").trim();

                    const statusCandidates = Array.from(article.querySelectorAll('a[href*="/status/"]'))
                      .map((node) => canonicalStatus(node.getAttribute('href') || ""))
                      .filter(Boolean);
                    if (!statusCandidates.length) continue;
                    let href = statusCandidates.find((candidate) => {
                      const owner = candidate.split("/")[3]?.toLowerCase() || "";
                      return owner === lower;
                    }) || statusCandidates[0];
                    if (!href) continue;
                    const owner = href.split("/")[3] || "";
                    const isTargetAuthor = owner.toLowerCase() === lower;

                    const textRoot = article.querySelector('[data-testid="tweetText"]') || article;
                    const textNodes = Array.from(textRoot.querySelectorAll('[lang]'));
                    const text = textNodes.map((n) => n.textContent || "").join(" ").replace(/\\s+/g, " ").trim();
                    if (!text) continue;

                    const outbound = [];
                    const seenLinks = new Set();
                    for (const anchor of Array.from(article.querySelectorAll('a[href]'))) {
                      const raw = anchor.getAttribute('href') || "";
                      const abs = toAbs(raw);
                      if (!abs) continue;
                      if (/\\/status\\//i.test(abs)) continue;
                      if (/\\/analytics/i.test(abs)) continue;
                      if (/\\/hashtag\\//i.test(abs)) continue;
                      if (/^mailto:/i.test(abs)) continue;
                      if (seenLinks.has(abs)) continue;
                      seenLinks.add(abs);
                      outbound.push(abs);
                    }

                    const viewsText =
                      (article.querySelector('a[href*="/analytics"]')?.textContent || "").trim() ||
                      metricText(article, "app-text-transition-container");
                    out.push({
                      href,
                      status_owner: owner,
                      is_target_author: isTargetAuthor,
                      text,
                      social_context: socialContext,
                      reply_text: metricText(article, "reply"),
                      repost_text: metricText(article, "retweet"),
                      like_text: metricText(article, "like"),
                      views_text: viewsText,
                      outbound_links: outbound.slice(0, 4),
                    });
                  }
                  return out;
                }
                """,
                clean_handle,
            )
            if not rows:
                rows = page.evaluate(
                    """
                    () => {
                      const out = [];
                      const toAbs = (href) => {
                        try {
                          return new URL(href, location.origin).toString();
                        } catch {
                          return String(href || "").trim();
                        }
                      };
                      const articles = Array.from(document.querySelectorAll('article'));
                      for (const article of articles) {
                        const statusLink = article.querySelector('a[href*="/status/"]');
                        if (!statusLink) continue;
                        const href = statusLink.getAttribute('href') || "";
                        const textNodes = Array.from(article.querySelectorAll('[lang]'));
                        const text = textNodes.map((n) => n.textContent || "").join(" ").replace(/\\s+/g, " ").trim();
                        if (!text) continue;
                        const outbound = [];
                        const seenLinks = new Set();
                        for (const anchor of Array.from(article.querySelectorAll('a[href]'))) {
                          const raw = anchor.getAttribute('href') || "";
                          const abs = toAbs(raw);
                          if (!abs) continue;
                          if (/\\/status\\//i.test(abs)) continue;
                          if (/\\/analytics/i.test(abs)) continue;
                          if (/\\/hashtag\\//i.test(abs)) continue;
                          if (/^mailto:/i.test(abs)) continue;
                          if (seenLinks.has(abs)) continue;
                          seenLinks.add(abs);
                          outbound.push(abs);
                        }
                        out.push({
                          href,
                          status_owner: "",
                          is_target_author: false,
                          text,
                          social_context: "",
                          reply_text: "",
                          repost_text: "",
                          like_text: "",
                          views_text: "",
                          outbound_links: outbound.slice(0, 4),
                        });
                      }
                      return out;
                    }
                    """
                )
                if rows:
                    print(f"[WARN] X @{clean_handle}: used legacy extractor fallback.")
            if rows:
                break
    except Exception:
        rows = []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    status_link_probe_budget = 10
    ranked_rows: list[dict[str, Any]] = []
    for row in rows:
        reply_count = parse_compact_number(row.get("reply_text"))
        repost_count = parse_compact_number(row.get("repost_text"))
        like_count = parse_compact_number(row.get("like_text"))
        view_count = parse_compact_number(row.get("views_text"))
        score = compute_x_engagement_score(reply_count, repost_count, like_count, view_count)
        if bool(row.get("is_target_author")):
            score += 120.0
        row_copy = dict(row)
        row_copy["reply_count"] = reply_count
        row_copy["repost_count"] = repost_count
        row_copy["like_count"] = like_count
        row_copy["view_count"] = view_count
        row_copy["engagement_score"] = score
        ranked_rows.append(row_copy)

    ranked_rows.sort(
        key=lambda row: (
            float(row.get("engagement_score", 0.0)),
            int(row.get("view_count", 0)),
            int(row.get("like_count", 0)),
        ),
        reverse=True,
    )

    for rank, row in enumerate(ranked_rows, start=1):
        if len(items) >= max_items:
            break
        link = norm_x_status_url(str(row.get("href", "")).strip())
        text = str(row.get("text", "")).strip()
        if not link or not text or link in seen:
            continue
        seen.add(link)

        reply_count = int(row.get("reply_count", 0))
        repost_count = int(row.get("repost_count", 0))
        like_count = int(row.get("like_count", 0))
        view_count = int(row.get("view_count", 0))
        engagement_score = float(row.get("engagement_score", 0.0))
        status_owner = str(row.get("status_owner", "")).strip()
        is_target_author = bool(row.get("is_target_author"))
        social_context = str(row.get("social_context", "")).strip()
        owner_match = re.match(r"^https?://(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/[0-9]+", link, flags=re.I)
        if owner_match:
            if not status_owner:
                status_owner = owner_match.group(1)
            if status_owner.lower() == clean_handle:
                is_target_author = True

        related_source_urls: list[str] = [link]
        linked_contexts: list[dict[str, str]] = []
        outbound_links_raw = row.get("outbound_links") or []
        outbound_links = [normalize_web_url(str(url)) for url in outbound_links_raw]
        outbound_links = [url for url in outbound_links if should_try_fetch_link(url)]
        if not outbound_links and status_link_probe_budget > 0:
            status_link_probe_budget -= 1
            outbound_links = extract_external_links_from_status_page(link, limit=3)
        for outbound_url in outbound_links[:2]:
            ctx = fetch_link_context(outbound_url)
            if not ctx:
                continue
            normalized_ctx_url = normalize_web_url(ctx.get("url", ""))
            if not normalized_ctx_url:
                continue
            ctx["url"] = normalized_ctx_url
            linked_contexts.append(ctx)
            related_source_urls.append(normalized_ctx_url)
            # Keep request pressure low.
            human_pause(max(0.4, delay_min * 0.25), max(0.9, delay_max * 0.35))

        dedup_related = []
        seen_related: set[str] = set()
        for related in related_source_urls:
            if related and related not in seen_related:
                seen_related.add(related)
                dedup_related.append(related)

        summary_hint_parts = [text[:320]]
        if not is_target_author:
            owner_hint = f"Shared/quoted from @{status_owner}." if status_owner else "Shared/quoted post."
            summary_hint_parts.append(owner_hint)
        if social_context:
            summary_hint_parts.append(f"Context: {social_context}")
        if linked_contexts:
            first_ctx = linked_contexts[0]
            title_part = first_ctx.get("title") or first_ctx.get("url", "")
            summary_part = first_ctx.get("summary", "")
            link_context_text = f"Shared link context: {title_part}. {summary_part}".strip()
            summary_hint_parts.append(link_context_text)
        summary_hint = " ".join(part for part in summary_hint_parts if part).strip()[:950]

        title = text[:160]
        category_hint = "X-热点"
        editorial = 5 if rank <= 2 else (4 if rank <= 8 else 3)
        items.append(
            {
                "title": title,
                "url": link,
                "source": f"X (Playwright) @{clean_handle}",
                "source_group": "social_community",
                "category_hint": category_hint,
                "summary_hint": summary_hint,
                "published_at": now.isoformat(),
                "related_source_urls": dedup_related[:4],
                "linked_contexts": linked_contexts[:2],
                "engagement_raw": {
                    "reply_count": reply_count,
                    "repost_count": repost_count,
                    "like_count": like_count,
                    "view_count": view_count,
                    "engagement_score": round(engagement_score, 2),
                    "status_owner": status_owner,
                    "is_target_author": is_target_author,
                },
                "hotness_signals": {
                    "editorial_prominence": editorial,
                    "engagement_velocity": engagement_velocity_from_score(engagement_score),
                    "cross_source_pickup": None,
                    "source_authority": 1,
                    "public_impact_scope": None,
                },
            }
        )
    return items


def main() -> int:
    args = parse_args()
    now = utc_now(args.now)
    subreddits = parse_csv(args.reddit_subreddits)
    x_handles = parse_csv(args.x_handles)
    channel = args.channel.strip() or "chrome"
    executable_path = args.executable_path.strip()
    delay_min, delay_max = bounded_range(
        args.human_delay_min_seconds,
        args.human_delay_max_seconds,
    )
    source_cooldown = max(0.0, args.source_cooldown_seconds)
    out_path = Path(args.out_file).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not subreddits and not x_handles:
        out_path.write_text(json.dumps({"items": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[WARN] No subreddit/handle configured. Wrote empty file: {out_path}")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        print("[ERROR] Playwright is not available.")
        print(f"[ERROR] {exc}")
        print("[HINT] Install with: pip3 install playwright (browser channel mode can use local Chrome).")
        return 2

    items: list[dict[str, Any]] = []
    reddit_total = 0
    x_total = 0
    reddit_statuses: dict[str, str] = {}
    profile = str(Path(args.user_data_dir).expanduser())
    with sync_playwright() as p:
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": profile,
            "headless": args.headless,
            "viewport": {"width": 1400, "height": 920},
            "locale": "en-US",
        }
        if args.stealth_login:
            launch_kwargs["ignore_default_args"] = ["--enable-automation"]
            launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        elif channel:
            launch_kwargs["channel"] = channel

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.new_page()
        page.set_default_timeout(args.timeout_ms)

        if args.login_wait_seconds > 0:
            if subreddits:
                try:
                    human_pause(delay_min, delay_max)
                    page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
                    post_load_settle(page, 1.2, delay_min, delay_max)
                except Exception:
                    pass
            if x_handles:
                try:
                    human_pause(delay_min, delay_max)
                    page.goto("https://x.com/", wait_until="domcontentloaded")
                    post_load_settle(page, 1.2, delay_min, delay_max)
                except Exception:
                    pass
            print(
                f"[INFO] Login warmup: complete required platform login(s) in opened browser within "
                f"{args.login_wait_seconds} seconds."
            )
            time.sleep(args.login_wait_seconds)

        for sub in subreddits:
            rows, status = collect_reddit_subreddit(
                page=page,
                subreddit=sub,
                now=now,
                max_items=args.max_per_source,
                wait_seconds=args.wait_seconds,
                delay_min=delay_min,
                delay_max=delay_max,
            )
            items.extend(rows)
            reddit_total += len(rows)
            reddit_statuses[sub] = status
            if status == "blocked":
                print(
                    f"[WARN] Reddit Playwright r/{sub}: blocked by Reddit network security "
                    "(login or developer token required)"
                )
            print(f"[OK] Reddit Playwright r/{sub}: {len(rows)} items (status={status})")
            if source_cooldown > 0:
                human_pause(source_cooldown, source_cooldown + max(0.8, delay_max))

        for handle in x_handles:
            rows = collect_x_handle(
                page=page,
                handle=handle,
                now=now,
                max_items=args.max_per_source,
                wait_seconds=args.wait_seconds,
                delay_min=delay_min,
                delay_max=delay_max,
            )
            items.extend(rows)
            x_total += len(rows)
            print(f"[OK] X Playwright @{handle}: {len(rows)} items")
            if source_cooldown > 0:
                human_pause(source_cooldown, source_cooldown + max(0.8, delay_max))

        context.close()

    out_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Social Playwright manual JSON written: {out_path}")
    print(f"[OK] Total items captured: {len(items)}")

    exit_code = 0
    if subreddits and args.require_reddit_items > 0 and reddit_total < args.require_reddit_items:
        print(
            f"[ERROR] Reddit Playwright captured too few items: {reddit_total} "
            f"(required >= {args.require_reddit_items})"
        )
        if any(status == "blocked" for status in reddit_statuses.values()):
            print(
                "[HINT] Reddit returned a network-security block page. "
                "Use a logged-in persistent profile or configure REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET "
                "for API collection."
            )
        exit_code = 3
    if x_handles and args.require_x_items > 0 and x_total < args.require_x_items:
        print(
            f"[ERROR] X Playwright captured too few items: {x_total} "
            f"(required >= {args.require_x_items})"
        )
        if exit_code == 0:
            exit_code = 4
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
