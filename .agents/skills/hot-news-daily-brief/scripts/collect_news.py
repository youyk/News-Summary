#!/usr/bin/env python3
"""
Collect last-24-hour news candidates into a local JSON file.

This script is designed for Stage A of a two-stage pipeline:
- Stage A (online): run this collector with internet access.
- Stage B (offline): Codex automation reads the saved JSON and summarizes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
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


def fetch_json(url: str, timeout: int = 20) -> dict[str, Any]:
    text = fetch_text(url, timeout=timeout)
    return json.loads(text)


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
    if any(keyword in haystack for keyword in AI_KEYWORDS):
        return "科技-AI"
    if any(keyword in haystack for keyword in FINANCE_KEYWORDS):
        return "金融"
    if any(keyword in haystack for keyword in POLITICS_KEYWORDS):
        return "时政"
    return default


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    report: dict[str, Any] = {"source": f"Reddit r/{subreddit}", "url": url}
    try:
        data = fetch_json(url)
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

    children = data.get("data", {}).get("children", [])
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
    return items, report


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

    fetch_reports: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    if not args.skip_network_sources:
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
            )
            items.extend(src_items)
            fetch_reports.append(report)

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
