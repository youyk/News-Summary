#!/usr/bin/env python3
"""
Collect last-24-hour news candidates into a local JSON file.

This script is designed for Stage A of a two-stage pipeline:
- Stage A (online): run this collector with internet access.
- Stage B (offline): Codex automation reads the saved JSON and summarizes.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


RSS_FEEDS = [
    {
        "source": "BBC World",
        "group": "mainstream_news",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "base_category": "时政",
        "priority": 5,
    },
    {
        "source": "BBC Business",
        "group": "finance",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "base_category": "金融",
        "priority": 5,
    },
    {
        "source": "BBC Technology",
        "group": "technology",
        "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "base_category": "科技-其他",
        "priority": 4,
    },
    {
        "source": "CNBC Top News",
        "group": "finance",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "base_category": "金融",
        "priority": 4,
    },
    {
        "source": "TechCrunch",
        "group": "technology",
        "url": "https://techcrunch.com/feed/",
        "base_category": "科技-其他",
        "priority": 4,
    },
    {
        "source": "The Verge",
        "group": "technology",
        "url": "https://www.theverge.com/rss/index.xml",
        "base_category": "科技-其他",
        "priority": 4,
    },
    {
        "source": "NPR News",
        "group": "mainstream_news",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "base_category": "时政",
        "priority": 3,
    },
    {
        "source": "CNN World",
        "group": "mainstream_news",
        "url": "http://rss.cnn.com/rss/edition_world.rss",
        "base_category": "时政",
        "priority": 4,
    },
    {
        "source": "CNN Business",
        "group": "finance",
        "url": "http://rss.cnn.com/rss/money_latest.rss",
        "base_category": "金融",
        "priority": 4,
    },
    {
        "source": "CBS Top Stories",
        "group": "mainstream_news",
        "url": "https://www.cbsnews.com/latest/rss/main",
        "base_category": "时政",
        "priority": 4,
    },
    {
        "source": "CBS World",
        "group": "mainstream_news",
        "url": "https://www.cbsnews.com/latest/rss/world",
        "base_category": "时政",
        "priority": 4,
    },
    {
        "source": "CBS MoneyWatch",
        "group": "finance",
        "url": "https://www.cbsnews.com/latest/rss/moneywatch",
        "base_category": "金融",
        "priority": 4,
    },
    {
        "source": "WSJ World",
        "group": "mainstream_news",
        "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "base_category": "时政",
        "priority": 4,
    },
    {
        "source": "WSJ Markets",
        "group": "finance",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "base_category": "金融",
        "priority": 4,
    },
]


REDDIT_SOURCES = [
    ("news", "social_community"),
    ("worldnews", "social_community"),
    ("technology", "social_community"),
    ("artificial", "social_community"),
]


USER_AGENT = "NewsSummaryCollector/1.0 (+https://localhost)"

AI_KEYWORDS = {
    "ai",
    "artificial intelligence",
    "llm",
    "gpt",
    "gemini",
    "claude",
    "openai",
    "anthropic",
    "deepmind",
    "model",
    "人工智能",
    "大模型",
    "生成式ai",
    "算力",
    "ai芯片",
    "机器人",
    "自动驾驶",
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
    "bank",
    "economy",
    "gdp",
    "recession",
    "dollar",
    "股市",
    "a股",
    "港股",
    "美股",
    "汇率",
    "人民币",
    "美元",
    "央行",
    "通胀",
    "债券",
    "原油",
    "金价",
    "经济",
    "财政",
    "就业",
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
    "diplomat",
    "conflict",
    "ukraine",
    "gaza",
    "iran",
    "russia",
    "china",
    "taiwan",
    "政府",
    "外交",
    "总统",
    "总理",
    "选举",
    "战争",
    "制裁",
    "冲突",
    "国务院",
    "国会",
    "议会",
    "联合国",
    "国防",
    "两会",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect news candidates into JSON.")
    parser.add_argument(
        "--out-dir",
        default="./data/inbox",
        help="Output directory for JSON candidate files",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Lookback window in hours",
    )
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=30,
        help="Max items to keep per RSS source",
    )
    parser.add_argument(
        "--reddit-limit",
        type=int,
        default=25,
        help="Max posts per subreddit",
    )
    parser.add_argument(
        "--reddit-client-id",
        default="",
        help="Optional Reddit API client_id (or set REDDIT_CLIENT_ID)",
    )
    parser.add_argument(
        "--reddit-client-secret",
        default="",
        help="Optional Reddit API client_secret (or set REDDIT_CLIENT_SECRET)",
    )
    parser.add_argument(
        "--disable-reddit-rss-fallback",
        action="store_true",
        help="Disable Reddit RSS fallback when JSON API access is blocked",
    )
    parser.add_argument(
        "--disable-weibo-hotsearch",
        action="store_true",
        help="Disable Weibo hot-search collector",
    )
    parser.add_argument(
        "--weibo-limit",
        type=int,
        default=30,
        help="Max topics to keep from Weibo hot search",
    )
    parser.add_argument(
        "--weibo-cookie",
        default="",
        help="Optional Weibo cookie (or set WEIBO_COOKIE)",
    )
    parser.add_argument(
        "--disable-toutiao-hotboard",
        action="store_true",
        help="Disable Toutiao hot-board collector",
    )
    parser.add_argument(
        "--toutiao-limit",
        type=int,
        default=30,
        help="Max topics to keep from Toutiao hot board",
    )
    parser.add_argument(
        "--toutiao-cookie",
        default="",
        help="Optional Toutiao cookie (or set TOUTIAO_COOKIE)",
    )
    parser.add_argument(
        "--x-handles",
        default="",
        help="Optional comma-separated X handles for Nitter RSS collector",
    )
    parser.add_argument(
        "--x-limit",
        type=int,
        default=20,
        help="Max posts to keep per X handle",
    )
    parser.add_argument(
        "--x-nitter-instances",
        default="",
        help="Optional comma-separated Nitter instances (or set X_NITTER_INSTANCES)",
    )
    parser.add_argument(
        "--x-rss-urls",
        default="",
        help="Optional comma-separated X RSS URLs (or set X_RSS_URLS)",
    )
    parser.add_argument(
        "--xiaohongshu-rss-urls",
        default="",
        help="Optional comma-separated Xiaohongshu RSS URLs (or set XIAOHONGSHU_RSS_URLS)",
    )
    parser.add_argument(
        "--manual-glob",
        default="",
        help="Optional glob for manual JSON source files (for X/Xiaohongshu/custom)",
    )
    parser.add_argument(
        "--skip-network-sources",
        action="store_true",
        help="Skip RSS/Reddit HTTP fetch and only use manual files",
    )
    parser.add_argument(
        "--now",
        default="",
        help="Optional ISO timestamp override in UTC (for deterministic tests)",
    )
    return parser.parse_args()


def parse_csv_values(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def engagement_bucket(
    value: float | None,
    *,
    p5: float,
    p4: float,
    p3: float,
    p2: float,
) -> int | None:
    if value is None:
        return None
    if value >= p5:
        return 5
    if value >= p4:
        return 4
    if value >= p3:
        return 3
    if value >= p2:
        return 2
    return 1


def make_hotness(
    editorial_prominence: int | None,
    *,
    engagement_velocity: int | None = None,
    source_authority: int | None = None,
) -> dict[str, Any]:
    return {
        "editorial_prominence": editorial_prominence,
        "engagement_velocity": engagement_velocity,
        "cross_source_pickup": None,
        "source_authority": source_authority,
        "public_impact_scope": None,
    }


def infer_rss_source_name(url: str, prefix: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc or "unknown-host"
    path = parsed.path.strip("/").replace("/", " ")
    suffix = f" {path}" if path else ""
    return f"{prefix} RSS ({host}{suffix})"


def env_truthy(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def utc_now(override: str) -> dt.datetime:
    if override:
        ts = override.strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_text_with_headers(
    url: str,
    headers: dict[str, str],
    timeout: int = 20,
    method: str = "GET",
    data: bytes | None = None,
) -> str:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    req_headers.update(headers)
    request = urllib.request.Request(
        url,
        headers=req_headers,
        method=method,
        data=data,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_json(url: str, timeout: int = 20) -> dict[str, Any]:
    text = fetch_text(url, timeout=timeout)
    return json.loads(text)


def fetch_reddit_access_token(client_id: str, client_secret: str) -> str:
    encoded = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    basic = f"{client_id}:{client_secret}".encode("utf-8")
    auth = base64.b64encode(basic).decode("ascii")
    response = fetch_text_with_headers(
        url="https://www.reddit.com/api/v1/access_token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
        data=encoded,
    )
    payload = json.loads(response)
    token = str(payload.get("access_token", "")).strip()
    if not token:
        raise ValueError(f"Reddit OAuth token response missing access_token: {payload}")
    return token


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_dt(value: str) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def first_text(parent: ET.Element, tag_suffixes: list[str]) -> str:
    for elem in parent.iter():
        local = elem.tag.split("}")[-1].lower()
        if local in tag_suffixes:
            text = elem.text or ""
            if text.strip():
                return text.strip()
    return ""


def category_from_text(text: str, default: str) -> str:
    haystack = (text or "").lower()
    if any(keyword_match(haystack, keyword) for keyword in AI_KEYWORDS):
        return "科技-AI"
    if any(keyword_match(haystack, keyword) for keyword in POLITICS_KEYWORDS):
        return "时政"
    if any(keyword_match(haystack, keyword) for keyword in FINANCE_KEYWORDS):
        return "金融"
    return default


def keyword_match(haystack: str, keyword: str) -> bool:
    key = (keyword or "").strip().lower()
    if not key:
        return False
    # For CJK keywords use plain containment; for Latin tokens require word boundaries.
    if re.search(r"[a-z0-9]", key):
        pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return key in haystack


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query_params if not k.lower().startswith("utm_")]
    new_query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


def stable_id(source: str, url: str, title: str) -> str:
    material = f"{source}|{normalize_url(url)}|{title.strip().lower()}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def parse_feed_entries(feed_xml: str) -> list[dict[str, str]]:
    root = ET.fromstring(feed_xml)
    entries: list[dict[str, str]] = []
    root_tag = root.tag.split("}")[-1].lower()

    if root_tag == "rss":
        for item in root.findall(".//item"):
            entries.append(
                {
                    "title": first_text(item, ["title"]),
                    "url": first_text(item, ["link"]),
                    "summary": first_text(item, ["description", "summary"]),
                    "published_at_raw": first_text(
                        item, ["pubdate", "published", "updated", "date"]
                    ),
                }
            )
        return entries

    if root_tag == "feed":
        for entry in root.findall(".//{*}entry"):
            link = ""
            for link_node in entry.findall(".//{*}link"):
                rel = (link_node.attrib.get("rel") or "alternate").lower()
                href = link_node.attrib.get("href", "").strip()
                if href and rel == "alternate":
                    link = href
                    break
                if href and not link:
                    link = href
            entries.append(
                {
                    "title": first_text(entry, ["title"]),
                    "url": link,
                    "summary": first_text(entry, ["summary", "content"]),
                    "published_at_raw": first_text(
                        entry, ["published", "updated", "date"]
                    ),
                }
            )
        return entries

    raise ValueError(f"Unsupported feed format: root tag={root.tag}")


def collect_rss_source(
    source_cfg: dict[str, Any],
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: dict[str, Any] = {
        "source": source_cfg["source"],
        "url": source_cfg["url"],
    }
    try:
        feed_text = fetch_text(source_cfg["url"])
        entries = parse_feed_entries(feed_text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
        report["fetched"] = 0
        return [], report
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"unexpected: {exc}"
        report["fetched"] = 0
        return [], report

    items: list[dict[str, Any]] = []
    for rank, entry in enumerate(entries[:limit], start=1):
        title = (entry.get("title") or "").strip()
        url = normalize_url((entry.get("url") or "").strip())
        if not title or not url:
            continue
        published = parse_dt(entry.get("published_at_raw", ""))
        if published and (published < window_start or published > now):
            continue
        snippet = strip_html(entry.get("summary", ""))
        combined = f"{title} {snippet}"
        category = category_from_text(combined, source_cfg["base_category"])
        prominence = max(1, source_cfg["priority"] - ((rank - 1) // 8))
        item = {
            "id": stable_id(source_cfg["source"], url, title),
            "title": title,
            "url": url,
            "source": source_cfg["source"],
            "source_group": source_cfg["group"],
            "category_hint": category,
            "summary_hint": snippet,
            "published_at": published.isoformat() if published else "",
            "fetched_at": now.isoformat(),
            "hotness_signals": {
                "editorial_prominence": prominence,
                "engagement_velocity": None,
                "cross_source_pickup": None,
                "source_authority": source_cfg["priority"],
                "public_impact_scope": None,
            },
        }
        items.append(item)

    report["status"] = "ok"
    report["fetched"] = len(items)
    return items, report


def collect_reddit(
    subreddit: str,
    group: str,
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
    oauth_token: str = "",
    allow_rss_fallback: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_name = f"Reddit r/{subreddit}"
    url_public = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    url_oauth = f"https://oauth.reddit.com/r/{subreddit}/hot?limit={limit}"
    url_rss = f"https://old.reddit.com/r/{subreddit}/hot/.rss?limit={limit}"
    report: dict[str, Any] = {
        "source": source_name,
        "url": url_oauth if oauth_token else url_public,
    }
    attempts: list[str] = []

    children: list[dict[str, Any]] = []
    mode = ""

    if oauth_token:
        try:
            text = fetch_text_with_headers(
                url_oauth,
                headers={"Authorization": f"Bearer {oauth_token}"},
            )
            data = json.loads(text)
            children = list(data.get("data", {}).get("children", []))
            mode = "oauth_json"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            attempts.append(f"oauth_json failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"oauth_json failed: unexpected {exc}")

    if not children:
        try:
            data = fetch_json(url_public)
            children = list(data.get("data", {}).get("children", []))
            mode = "public_json"
            report["url"] = url_public
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            attempts.append(f"public_json failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"public_json failed: unexpected {exc}")

    if not children and allow_rss_fallback:
        try:
            feed_text = fetch_text(url_rss)
            entries = parse_feed_entries(feed_text)
            items: list[dict[str, Any]] = []
            for rank, entry in enumerate(entries[:limit], start=1):
                title = (entry.get("title") or "").strip()
                post_url = normalize_url((entry.get("url") or "").strip())
                if not title or not post_url:
                    continue
                published = parse_dt(entry.get("published_at_raw", ""))
                if published and (published < window_start or published > now):
                    continue
                snippet = strip_html(entry.get("summary", ""))[:300]
                combined = f"{title} {snippet}"
                category = category_from_text(combined, "科技-其他")
                prominence = 5 if rank <= 3 else (4 if rank <= 10 else 3)
                item = {
                    "id": stable_id(source_name, post_url, title),
                    "title": title,
                    "url": post_url,
                    "source": source_name,
                    "source_group": group,
                    "category_hint": category,
                    "summary_hint": snippet,
                    "published_at": published.isoformat() if published else "",
                    "fetched_at": now.isoformat(),
                    "hotness_signals": {
                        "editorial_prominence": prominence,
                        "engagement_velocity": None,
                        "cross_source_pickup": None,
                        "source_authority": 2,
                        "public_impact_scope": None,
                    },
                    "engagement_raw": {},
                }
                items.append(item)
            report["status"] = "ok"
            report["fetched"] = len(items)
            report["mode"] = "rss_fallback"
            report["url"] = url_rss
            if attempts:
                report["attempts"] = attempts
            return items, report
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            attempts.append(f"rss_fallback failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"rss_fallback failed: unexpected {exc}")

    if not children:
        report["status"] = "error"
        report["error"] = " | ".join(attempts) if attempts else "unknown error"
        report["fetched"] = 0
        if attempts:
            report["attempts"] = attempts
        return [], report

    items: list[dict[str, Any]] = []
    for rank, child in enumerate(children, start=1):
        payload = child.get("data", {})
        title = (payload.get("title") or "").strip()
        post_url = payload.get("url_overridden_by_dest") or payload.get("url") or ""
        post_url = normalize_url(str(post_url).strip())
        if not title or not post_url:
            continue

        created_utc = payload.get("created_utc")
        published = None
        if isinstance(created_utc, (int, float)):
            published = dt.datetime.fromtimestamp(created_utc, tz=dt.timezone.utc)
        if published and (published < window_start or published > now):
            continue

        snippet = strip_html(payload.get("selftext", ""))[:300]
        score = payload.get("score")
        comments = payload.get("num_comments")
        engagement_level = None
        if isinstance(score, (int, float)) and isinstance(comments, (int, float)):
            raw = float(score) + float(comments) * 2.0
            if raw >= 5000:
                engagement_level = 5
            elif raw >= 2000:
                engagement_level = 4
            elif raw >= 800:
                engagement_level = 3
            elif raw >= 300:
                engagement_level = 2
            else:
                engagement_level = 1

        combined = f"{title} {snippet}"
        category = category_from_text(combined, "科技-其他")
        prominence = 5 if rank <= 3 else (4 if rank <= 10 else 3)
        item = {
            "id": stable_id(f"Reddit r/{subreddit}", post_url, title),
            "title": title,
            "url": post_url,
            "source": f"Reddit r/{subreddit}",
            "source_group": group,
            "category_hint": category,
            "summary_hint": snippet,
            "published_at": published.isoformat() if published else "",
            "fetched_at": now.isoformat(),
            "hotness_signals": {
                "editorial_prominence": prominence,
                "engagement_velocity": engagement_level,
                "cross_source_pickup": None,
                "source_authority": 2,
                "public_impact_scope": None,
            },
            "engagement_raw": {
                "score": score,
                "comments": comments,
            },
        }
        items.append(item)

    report["status"] = "ok"
    report["fetched"] = len(items)
    report["mode"] = mode or "public_json"
    if attempts:
        report["attempts"] = attempts
    return items, report


def collect_social_rss_urls(
    urls: list[str],
    *,
    source_prefix: str,
    source_group: str,
    base_category: str,
    source_priority: int,
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not urls:
        return [], []
    items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for url in urls:
        cfg = {
            "source": infer_rss_source_name(url, source_prefix),
            "group": source_group,
            "url": url,
            "base_category": base_category,
            "priority": source_priority,
        }
        src_items, report = collect_rss_source(
            source_cfg=cfg,
            now=now,
            window_start=window_start,
            limit=limit,
        )
        items.extend(src_items)
        reports.append(report)
    return items, reports


def collect_weibo_hotsearch(
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
    cookie: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = "https://weibo.com/ajax/side/hotSearch"
    source_name = "Weibo Hot Search"
    report: dict[str, Any] = {"source": source_name, "url": url}

    headers = {
        "Referer": "https://weibo.com/",
        "Accept": "application/json, text/plain, */*",
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        text = fetch_text_with_headers(url, headers=headers)
        payload = json.loads(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
        report["fetched"] = 0
        return [], report
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"unexpected: {exc}"
        report["fetched"] = 0
        return [], report

    topics: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("realtime"), list):
            topics = [topic for topic in data["realtime"] if isinstance(topic, dict)]
        elif isinstance(payload.get("realtime"), list):
            topics = [topic for topic in payload["realtime"] if isinstance(topic, dict)]

    if not topics:
        report["status"] = "error"
        report["error"] = "unexpected response format: missing realtime topics"
        report["fetched"] = 0
        return [], report

    items: list[dict[str, Any]] = []
    for rank, topic in enumerate(topics[:limit], start=1):
        title = (
            str(topic.get("word", "")).strip()
            or str(topic.get("note", "")).strip()
            or str(topic.get("title", "")).strip()
        )
        if not title:
            continue

        topic_url = str(topic.get("topic_url", "")).strip()
        if topic_url.startswith("//"):
            topic_url = f"https:{topic_url}"
        if not topic_url:
            query = urllib.parse.quote_plus(title)
            topic_url = f"https://s.weibo.com/weibo?q={query}"
        topic_url = normalize_url(topic_url)

        hot_value = (
            parse_float(topic.get("raw_hot"))
            or parse_float(topic.get("num"))
            or parse_float(topic.get("hot"))
        )
        hot_level = engagement_bucket(
            hot_value,
            p5=2_000_000,
            p4=800_000,
            p3=200_000,
            p2=50_000,
        )
        label_name = str(topic.get("label_name", "")).strip()
        flag_desc = str(topic.get("flag_desc", "")).strip()
        summary_hint = " ".join(part for part in [label_name, flag_desc] if part).strip()

        # Topic boards are near-real-time. Keep only window-consistent timestamps.
        published = now
        if published < window_start or published > now:
            continue

        combined = f"{title} {summary_hint}".strip()
        category = category_from_text(combined, "科技-其他")
        prominence = 5 if rank <= 3 else (4 if rank <= 10 else 3)

        items.append(
            {
                "id": stable_id(source_name, topic_url, title),
                "title": title,
                "url": topic_url,
                "source": source_name,
                "source_group": "social_community",
                "category_hint": category,
                "summary_hint": summary_hint,
                "published_at": published.isoformat(),
                "fetched_at": now.isoformat(),
                "hotness_signals": make_hotness(
                    prominence,
                    engagement_velocity=hot_level,
                    source_authority=2,
                ),
                "engagement_raw": {
                    "raw_hot": topic.get("raw_hot"),
                    "num": topic.get("num"),
                },
            }
        )

    report["status"] = "ok"
    report["fetched"] = len(items)
    return items, report


def collect_toutiao_hotboard(
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
    cookie: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
    source_name = "Toutiao Hot Board"
    report: dict[str, Any] = {"source": source_name, "url": url}
    headers = {
        "Referer": "https://www.toutiao.com/hot-event/hot-board/",
        "Accept": "application/json, text/plain, */*",
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        text = fetch_text_with_headers(url, headers=headers)
        payload = json.loads(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
        report["fetched"] = 0
        return [], report
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"unexpected: {exc}"
        report["fetched"] = 0
        return [], report

    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = [item for item in payload["data"] if isinstance(item, dict)]

    if not rows:
        report["status"] = "error"
        report["error"] = "unexpected response format: missing data list"
        report["fetched"] = 0
        return [], report

    items: list[dict[str, Any]] = []
    for rank, row in enumerate(rows[:limit], start=1):
        title = str(row.get("Title") or row.get("title") or "").strip()
        if not title:
            continue

        topic_url = str(row.get("Url") or row.get("url") or "").strip()
        if topic_url.startswith("/"):
            topic_url = f"https://www.toutiao.com{topic_url}"
        if not topic_url:
            query = urllib.parse.quote_plus(title)
            topic_url = f"https://so.toutiao.com/search?keyword={query}"
        topic_url = normalize_url(topic_url)

        hot_value = (
            parse_float(row.get("HotValue"))
            or parse_float(row.get("hot_value"))
            or parse_float(row.get("hotValue"))
        )
        hot_level = engagement_bucket(
            hot_value,
            p5=2_000_000,
            p4=800_000,
            p3=250_000,
            p2=80_000,
        )
        label = str(row.get("Label") or row.get("label") or "").strip()
        summary_hint = label

        published = now
        if published < window_start or published > now:
            continue

        combined = f"{title} {summary_hint}".strip()
        category = category_from_text(combined, "科技-其他")
        prominence = 5 if rank <= 3 else (4 if rank <= 10 else 3)

        items.append(
            {
                "id": stable_id(source_name, topic_url, title),
                "title": title,
                "url": topic_url,
                "source": source_name,
                "source_group": "social_community",
                "category_hint": category,
                "summary_hint": summary_hint,
                "published_at": published.isoformat(),
                "fetched_at": now.isoformat(),
                "hotness_signals": make_hotness(
                    prominence,
                    engagement_velocity=hot_level,
                    source_authority=2,
                ),
                "engagement_raw": {
                    "hot_value": row.get("HotValue") or row.get("hot_value") or row.get("hotValue"),
                },
            }
        )

    report["status"] = "ok"
    report["fetched"] = len(items)
    return items, report


def collect_x_nitter_handles(
    handles: list[str],
    instances: list[str],
    now: dt.datetime,
    window_start: dt.datetime,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not handles:
        return [], []

    if not instances:
        instances = [
            "https://nitter.net",
            "https://nitter.poast.org",
            "https://nitter.privacydev.net",
        ]

    all_items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []

    for handle in handles:
        clean_handle = handle.lstrip("@")
        source_name = f"X @{clean_handle}"
        attempts: list[str] = []
        handle_items: list[dict[str, Any]] = []
        selected_url = ""

        for instance in instances:
            base = instance.rstrip("/")
            feed_url = f"{base}/{clean_handle}/rss"
            selected_url = feed_url
            try:
                feed_text = fetch_text(feed_url)
                entries = parse_feed_entries(feed_text)
                for rank, entry in enumerate(entries[:limit], start=1):
                    title = (entry.get("title") or "").strip()
                    post_url = normalize_url((entry.get("url") or "").strip())
                    if not title or not post_url:
                        continue
                    published = parse_dt(entry.get("published_at_raw", ""))
                    if published and (published < window_start or published > now):
                        continue
                    snippet = strip_html(entry.get("summary", ""))[:300]
                    category = category_from_text(f"{title} {snippet}", "科技-其他")
                    prominence = 5 if rank <= 3 else (4 if rank <= 10 else 3)
                    handle_items.append(
                        {
                            "id": stable_id(source_name, post_url, title),
                            "title": title,
                            "url": post_url,
                            "source": source_name,
                            "source_group": "social_community",
                            "category_hint": category,
                            "summary_hint": snippet,
                            "published_at": published.isoformat() if published else "",
                            "fetched_at": now.isoformat(),
                            "hotness_signals": make_hotness(
                                prominence,
                                source_authority=1,
                            ),
                        }
                    )
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
                attempts.append(f"{feed_url} failed: {exc}")
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"{feed_url} failed: unexpected {exc}")

        report: dict[str, Any] = {"source": source_name, "url": selected_url}
        if handle_items:
            report["status"] = "ok"
            report["fetched"] = len(handle_items)
            report["mode"] = "nitter_rss"
            if attempts:
                report["attempts"] = attempts
            all_items.extend(handle_items)
        else:
            report["status"] = "error"
            report["fetched"] = 0
            report["error"] = " | ".join(attempts) if attempts else "no accessible nitter instance"
            if attempts:
                report["attempts"] = attempts
        reports.append(report)

    return all_items, reports


def collect_manual_files(
    manual_glob: str,
    now: dt.datetime,
    window_start: dt.datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not manual_glob:
        return [], []
    root_glob = Path(manual_glob)
    paths = sorted(root_glob.parent.glob(root_glob.name))
    items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for path in paths:
        report: dict[str, Any] = {"source": f"manual:{path.name}", "url": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows: list[dict[str, Any]]
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                rows = payload["items"]
            elif isinstance(payload, list):
                rows = payload
            else:
                raise ValueError("Manual JSON must be a list or {'items': [...]}")
            added = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title", "")).strip()
                url = normalize_url(str(row.get("url", "")).strip())
                source = str(row.get("source", "Manual Source")).strip() or "Manual Source"
                if not title or not url:
                    continue
                published = parse_dt(str(row.get("published_at", "")).strip())
                if published and (published < window_start or published > now):
                    continue
                summary_hint = strip_html(str(row.get("summary_hint", "")).strip())
                category = str(row.get("category_hint", "")).strip()
                if category not in {"时政", "金融", "科技-AI", "科技-其他"}:
                    category = category_from_text(f"{title} {summary_hint}", "科技-其他")
                item = {
                    "id": stable_id(source, url, title),
                    "title": title,
                    "url": url,
                    "source": source,
                    "source_group": str(row.get("source_group", "custom")).strip() or "custom",
                    "category_hint": category,
                    "summary_hint": summary_hint,
                    "published_at": published.isoformat() if published else "",
                    "fetched_at": now.isoformat(),
                    "hotness_signals": row.get(
                        "hotness_signals",
                        {
                            "editorial_prominence": None,
                            "engagement_velocity": None,
                            "cross_source_pickup": None,
                            "source_authority": None,
                            "public_impact_scope": None,
                        },
                    ),
                }
                items.append(item)
                added += 1
            report["status"] = "ok"
            report["fetched"] = added
        except Exception as exc:  # noqa: BLE001
            report["status"] = "error"
            report["error"] = str(exc)
            report["fetched"] = 0
        reports.append(report)
    return items, reports


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        url_key = normalize_url(item.get("url", ""))
        title_key = re.sub(r"\s+", " ", item.get("title", "").strip().lower())
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)
    return result


def main() -> int:
    args = parse_args()
    now = utc_now(args.now)
    window_start = now - dt.timedelta(hours=args.window_hours)
    reddit_client_id = args.reddit_client_id.strip() or os.getenv("REDDIT_CLIENT_ID", "").strip()
    reddit_client_secret = args.reddit_client_secret.strip() or os.getenv(
        "REDDIT_CLIENT_SECRET", ""
    ).strip()
    weibo_cookie = args.weibo_cookie.strip() or os.getenv("WEIBO_COOKIE", "").strip()
    toutiao_cookie = args.toutiao_cookie.strip() or os.getenv("TOUTIAO_COOKIE", "").strip()
    x_handles = parse_csv_values(args.x_handles or os.getenv("X_HANDLES", ""))
    x_instances = parse_csv_values(args.x_nitter_instances or os.getenv("X_NITTER_INSTANCES", ""))
    x_rss_urls = parse_csv_values(args.x_rss_urls or os.getenv("X_RSS_URLS", ""))
    xiaohongshu_rss_urls = parse_csv_values(
        args.xiaohongshu_rss_urls or os.getenv("XIAOHONGSHU_RSS_URLS", "")
    )
    disable_weibo_hotsearch = args.disable_weibo_hotsearch or env_truthy("DISABLE_WEIBO_HOTSEARCH")
    disable_toutiao_hotboard = args.disable_toutiao_hotboard or env_truthy(
        "DISABLE_TOUTIAO_HOTBOARD"
    )

    fetch_reports: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    reddit_oauth_token = ""

    if not args.skip_network_sources:
        if reddit_client_id and reddit_client_secret:
            try:
                reddit_oauth_token = fetch_reddit_access_token(
                    client_id=reddit_client_id,
                    client_secret=reddit_client_secret,
                )
            except Exception as exc:  # noqa: BLE001
                fetch_reports.append(
                    {
                        "source": "Reddit OAuth bootstrap",
                        "url": "https://www.reddit.com/api/v1/access_token",
                        "status": "error",
                        "error": str(exc),
                        "fetched": 0,
                    }
                )

        for source_cfg in RSS_FEEDS:
            src_items, report = collect_rss_source(
                source_cfg=source_cfg,
                now=now,
                window_start=window_start,
                limit=args.limit_per_source,
            )
            items.extend(src_items)
            fetch_reports.append(report)

        for subreddit, group in REDDIT_SOURCES:
            src_items, report = collect_reddit(
                subreddit=subreddit,
                group=group,
                now=now,
                window_start=window_start,
                limit=args.reddit_limit,
                oauth_token=reddit_oauth_token,
                allow_rss_fallback=not args.disable_reddit_rss_fallback,
            )
            items.extend(src_items)
            fetch_reports.append(report)

        if not disable_weibo_hotsearch:
            src_items, report = collect_weibo_hotsearch(
                now=now,
                window_start=window_start,
                limit=args.weibo_limit,
                cookie=weibo_cookie,
            )
            items.extend(src_items)
            fetch_reports.append(report)

        if not disable_toutiao_hotboard:
            src_items, report = collect_toutiao_hotboard(
                now=now,
                window_start=window_start,
                limit=args.toutiao_limit,
                cookie=toutiao_cookie,
            )
            items.extend(src_items)
            fetch_reports.append(report)

        x_items, x_reports = collect_x_nitter_handles(
            handles=x_handles,
            instances=x_instances,
            now=now,
            window_start=window_start,
            limit=args.x_limit,
        )
        items.extend(x_items)
        fetch_reports.extend(x_reports)

        x_feed_items, x_feed_reports = collect_social_rss_urls(
            urls=x_rss_urls,
            source_prefix="X",
            source_group="social_community",
            base_category="科技-其他",
            source_priority=2,
            now=now,
            window_start=window_start,
            limit=args.x_limit,
        )
        items.extend(x_feed_items)
        fetch_reports.extend(x_feed_reports)

        xhs_items, xhs_reports = collect_social_rss_urls(
            urls=xiaohongshu_rss_urls,
            source_prefix="Xiaohongshu",
            source_group="social_community",
            base_category="科技-其他",
            source_priority=2,
            now=now,
            window_start=window_start,
            limit=args.limit_per_source,
        )
        items.extend(xhs_items)
        fetch_reports.extend(xhs_reports)

    manual_items, manual_reports = collect_manual_files(
        manual_glob=args.manual_glob,
        now=now,
        window_start=window_start,
    )
    items.extend(manual_items)
    fetch_reports.extend(manual_reports)

    deduped = deduplicate(items)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"news_candidates_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path = out_dir / filename

    ok_sources = sum(1 for item in fetch_reports if item.get("status") == "ok")
    failed_sources = sum(1 for item in fetch_reports if item.get("status") != "ok")

    payload = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "window_hours": args.window_hours,
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "stats": {
            "total_before_dedup": len(items),
            "total_after_dedup": len(deduped),
            "sources_ok": ok_sources,
            "sources_failed": failed_sources,
        },
        "fetch_report": fetch_reports,
        "items": deduped,
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[OK] Wrote candidate file: {out_path}")
    print(
        f"[OK] Items: {len(deduped)} (before dedup: {len(items)}), "
        f"sources ok={ok_sources}, failed={failed_sources}"
    )
    if failed_sources:
        print("[WARN] Some sources failed. Check fetch_report in output JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
