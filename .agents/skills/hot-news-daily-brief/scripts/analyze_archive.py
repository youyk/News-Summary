#!/usr/bin/env python3
"""
Analyze date/source archive files for multi-window trends.

Outputs:
- JSON analytics payload (machine-readable)
- Markdown report (human-readable)

Default windows: 7,30,90,180,360 days.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_WINDOWS = [7, 30, 90, 180, 360]
HOTNESS_WEIGHTS = {
    "editorial_prominence": 0.30,
    "engagement_velocity": 0.25,
    "cross_source_pickup": 0.20,
    "source_authority": 0.15,
    "public_impact_scope": 0.10,
}

EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "over",
    "under",
    "after",
    "before",
    "about",
    "what",
    "when",
    "where",
    "which",
    "while",
    "will",
    "would",
    "could",
    "should",
    "have",
    "has",
    "had",
    "are",
    "was",
    "were",
    "been",
    "being",
    "its",
    "their",
    "your",
    "our",
    "his",
    "her",
    "they",
    "them",
    "you",
    "not",
    "now",
    "new",
    "says",
    "say",
    "said",
    "amid",
    "latest",
    "video",
    "live",
    "news",
    "update",
    "updates",
    "comment",
    "comments",
    "shared",
    "quoted",
    "http",
    "https",
    "www",
    "com",
    "amp",
    "rt",
    "via",
}

ZH_STOPWORDS = {
    "今天",
    "昨日",
    "表示",
    "回应",
    "发布",
    "视频",
    "最新",
    "消息",
    "报道",
    "我们",
    "他们",
    "你们",
    "这个",
    "那个",
    "以及",
    "进行",
    "相关",
    "事件",
    "平台",
    "官方",
    "网友",
    "新闻",
    "热搜",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze archive trends across time windows.")
    parser.add_argument(
        "--archive-root",
        default="./data/archive/by_date_source",
        help="Archive root directory produced by collect_news.py",
    )
    parser.add_argument(
        "--windows",
        default="7,30,90,180,360",
        help="Comma-separated window days",
    )
    parser.add_argument(
        "--out-dir",
        default="./Report/archive-analysis",
        help="Output directory for analysis files",
    )
    parser.add_argument(
        "--top-keywords",
        type=int,
        default=10,
        help="Top keywords per source/window",
    )
    parser.add_argument(
        "--top-sources",
        type=int,
        default=12,
        help="Top sources per window",
    )
    parser.add_argument(
        "--top-events",
        type=int,
        default=15,
        help="Top repeated event trajectories per window",
    )
    return parser.parse_args()


def parse_windows(raw: str) -> list[int]:
    values: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            day = int(piece)
        except ValueError:
            continue
        if day > 0:
            values.append(day)
    if not values:
        return list(DEFAULT_WINDOWS)
    return sorted(dict.fromkeys(values))


def parse_dt(value: str) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0
    return 0.0


def hotness_score(item: dict[str, Any]) -> float:
    signals = item.get("hotness_signals")
    if not isinstance(signals, dict):
        return 0.0
    score = 0.0
    for key, weight in HOTNESS_WEIGHTS.items():
        score += to_float(signals.get(key)) * weight
    return round(score, 4)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    kept = [(k, v) for (k, v) in query if not k.lower().startswith("utm_")]
    path = parsed.path.rstrip("/")
    normalized = urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(kept), "")
    )
    return normalized


def tokenize_keywords(text: str) -> set[str]:
    lowered = text.lower()
    tokens: set[str] = set()

    for tok in re.findall(r"[a-z][a-z0-9+\-]{2,}", lowered):
        if tok in EN_STOPWORDS:
            continue
        if tok.isdigit():
            continue
        tokens.add(tok)

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if 2 <= len(chunk) <= 6:
            if chunk not in ZH_STOPWORDS:
                tokens.add(chunk)
            continue
        if len(chunk) > 6:
            # Sliding short n-grams for long no-space Chinese phrases.
            for n in (2, 3, 4):
                max_start = min(len(chunk) - n + 1, 24)
                for idx in range(max_start):
                    gram = chunk[idx : idx + n]
                    if gram in ZH_STOPWORDS:
                        continue
                    tokens.add(gram)

    return tokens


def title_fingerprint(title: str) -> str:
    text = title.strip().lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    parts = [p for p in text.split() if p and p not in EN_STOPWORDS]
    if not parts:
        return ""
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return " ".join(ordered[:12])


def event_key(item: dict[str, Any]) -> str:
    fp = title_fingerprint(str(item.get("title", "")))
    if fp and len(fp.split()) >= 3:
        return f"title:{fp}"
    normalized = normalize_url(str(item.get("url", "")))
    if normalized:
        parsed = urllib.parse.urlsplit(normalized)
        host_path = f"{parsed.netloc}{parsed.path}"
        if host_path:
            return f"url:{host_path.lower()}"
    if fp:
        return f"title:{fp}"
    return f"id:{item.get('id', '')}"


def day_list(start: dt.date, end: dt.date) -> list[str]:
    days: list[str] = []
    cur = start
    while cur <= end:
        days.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return days


def load_records(archive_root: Path) -> tuple[list[dict[str, Any]], list[dt.date]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    dates: set[dt.date] = set()

    if not archive_root.exists():
        return records, []

    for date_dir in sorted(archive_root.iterdir()):
        if not date_dir.is_dir():
            continue
        try:
            dir_date = dt.date.fromisoformat(date_dir.name)
        except ValueError:
            continue
        dates.add(dir_date)

        for json_file in sorted(date_dir.glob("*.json")):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            source = str(payload.get("source", "")).strip() or json_file.stem
            source_slug = str(payload.get("source_slug", "")).strip() or json_file.stem
            items = payload.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                rec_id = str(item.get("id", "")).strip()
                if not rec_id:
                    rec_id = f"{source_slug}:{hash((item.get('title',''), item.get('url','')))}"
                uniq = f"{date_dir.name}:{source_slug}:{rec_id}"
                if uniq in seen:
                    continue
                seen.add(uniq)

                published = parse_dt(str(item.get("published_at", "")))
                fetched = parse_dt(str(item.get("fetched_at", "")))
                record_dt = published or fetched
                record_date = (record_dt.date() if record_dt else dir_date)
                dates.add(record_date)

                title = str(item.get("title", "")).strip()
                summary = str(item.get("summary_hint", "")).strip()
                category = str(item.get("category_hint", "")).strip()
                url = str(item.get("url", "")).strip()
                hotness = hotness_score(item)
                keyword_tokens = tokenize_keywords(f"{title} {summary}")

                records.append(
                    {
                        "id": rec_id,
                        "source": source,
                        "source_slug": source_slug,
                        "date": record_date,
                        "datetime": record_dt.isoformat() if record_dt else "",
                        "title": title,
                        "summary_hint": summary,
                        "url": url,
                        "category_hint": category,
                        "hotness": hotness,
                        "keywords": keyword_tokens,
                        "event_key": event_key(item),
                    }
                )

    return records, sorted(dates)


def stats_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0, "avg_hotness": 0.0, "max_hotness": 0.0}
    hotness_values = [float(r["hotness"]) for r in records]
    return {
        "count": len(records),
        "avg_hotness": round(sum(hotness_values) / len(hotness_values), 4),
        "max_hotness": round(max(hotness_values), 4),
    }


def source_trends(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    top_sources: int,
) -> list[dict[str, Any]]:
    curr_by_src: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prev_by_src: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in current:
        curr_by_src[r["source"]].append(r)
    for r in previous:
        prev_by_src[r["source"]].append(r)

    all_sources = set(curr_by_src.keys()) | set(prev_by_src.keys())
    rows: list[dict[str, Any]] = []
    for src in all_sources:
        c_stats = stats_for_records(curr_by_src.get(src, []))
        p_stats = stats_for_records(prev_by_src.get(src, []))
        delta_hot = round(c_stats["avg_hotness"] - p_stats["avg_hotness"], 4)
        c_count = c_stats["count"]
        p_count = p_stats["count"]
        if p_count > 0:
            delta_count_pct = round((c_count - p_count) * 100.0 / p_count, 2)
        elif c_count > 0:
            delta_count_pct = 100.0
        else:
            delta_count_pct = 0.0

        if p_count == 0 and c_count > 0:
            trend = "new"
        elif delta_hot >= 0.2 or delta_count_pct >= 30:
            trend = "up"
        elif delta_hot <= -0.2 or delta_count_pct <= -30:
            trend = "down"
        else:
            trend = "flat"

        rows.append(
            {
                "source": src,
                "current_count": c_count,
                "current_avg_hotness": c_stats["avg_hotness"],
                "previous_count": p_count,
                "previous_avg_hotness": p_stats["avg_hotness"],
                "delta_avg_hotness": delta_hot,
                "delta_count_pct": delta_count_pct,
                "trend": trend,
            }
        )

    rows.sort(
        key=lambda x: (
            x["current_count"],
            x["current_avg_hotness"],
            x["delta_avg_hotness"],
        ),
        reverse=True,
    )
    return rows[:top_sources]


def keyword_trends(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    top_keywords: int,
    top_sources: int,
) -> dict[str, Any]:
    curr_by_src: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prev_by_src: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in current:
        curr_by_src[r["source"]].append(r)
    for r in previous:
        prev_by_src[r["source"]].append(r)

    sources = sorted(curr_by_src.keys(), key=lambda s: len(curr_by_src[s]), reverse=True)[:top_sources]
    source_keywords: dict[str, list[dict[str, Any]]] = {}

    overall_curr = Counter()
    overall_prev = Counter()

    for src in sources:
        curr_score = Counter()
        prev_score = Counter()
        curr_count = Counter()
        prev_count = Counter()

        for r in curr_by_src[src]:
            weight = float(r["hotness"]) + 1.0
            for kw in r["keywords"]:
                curr_score[kw] += weight
                curr_count[kw] += 1
                overall_curr[kw] += weight
        for r in prev_by_src.get(src, []):
            weight = float(r["hotness"]) + 1.0
            for kw in r["keywords"]:
                prev_score[kw] += weight
                prev_count[kw] += 1
                overall_prev[kw] += weight

        rows: list[dict[str, Any]] = []
        for kw, score in curr_score.items():
            delta = score - prev_score.get(kw, 0.0)
            rows.append(
                {
                    "keyword": kw,
                    "score": round(score, 3),
                    "count": int(curr_count[kw]),
                    "delta_score": round(delta, 3),
                    "prev_score": round(prev_score.get(kw, 0.0), 3),
                    "prev_count": int(prev_count.get(kw, 0)),
                }
            )
        rows.sort(key=lambda x: (x["score"], x["delta_score"], x["count"]), reverse=True)
        source_keywords[src] = rows[:top_keywords]

    overall_rows: list[dict[str, Any]] = []
    for kw, score in overall_curr.items():
        delta = score - overall_prev.get(kw, 0.0)
        overall_rows.append(
            {
                "keyword": kw,
                "score": round(score, 3),
                "delta_score": round(delta, 3),
            }
        )
    overall_rows.sort(key=lambda x: (x["score"], x["delta_score"]), reverse=True)

    return {
        "by_source": source_keywords,
        "overall_top_keywords": overall_rows[:top_keywords],
    }


def repeated_event_trajectories(
    current: list[dict[str, Any]],
    top_events: int,
) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in current:
        key = r.get("event_key", "")
        if key:
            by_key[key].append(r)

    rows: list[dict[str, Any]] = []
    for key, cluster in by_key.items():
        if len(cluster) < 2:
            continue
        date_set = {r["date"] for r in cluster}
        source_set = {r["source"] for r in cluster}
        if len(date_set) < 2 and len(source_set) < 2:
            continue

        title_counter = Counter(r["title"] for r in cluster if r["title"])
        representative = title_counter.most_common(1)[0][0] if title_counter else key

        url_counter = Counter(r["url"] for r in cluster if r["url"])
        urls = [u for (u, _) in url_counter.most_common(3)]

        daily_counter = Counter(r["date"].isoformat() for r in cluster)
        daily_series = [{"date": d, "count": c} for d, c in sorted(daily_counter.items())]

        hotness_values = [float(r["hotness"]) for r in cluster]
        rows.append(
            {
                "event_key": key,
                "title": representative,
                "occurrences": len(cluster),
                "source_count": len(source_set),
                "sources": sorted(source_set),
                "first_seen": min(date_set).isoformat(),
                "last_seen": max(date_set).isoformat(),
                "avg_hotness": round(sum(hotness_values) / len(hotness_values), 4),
                "max_hotness": round(max(hotness_values), 4),
                "daily_series": daily_series,
                "urls": urls,
            }
        )

    rows.sort(
        key=lambda x: (x["occurrences"], x["source_count"], x["avg_hotness"]),
        reverse=True,
    )
    return rows[:top_events]


def render_markdown(
    *,
    generated_at: str,
    archive_root: str,
    data_start: str,
    data_end: str,
    total_records: int,
    windows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# Archive Trend Analysis")
    lines.append("")
    lines.append(f"- Generated at: {generated_at}")
    lines.append(f"- Archive root: `{archive_root}`")
    lines.append(f"- Data coverage: {data_start} -> {data_end}")
    lines.append(f"- Total records: {total_records}")
    lines.append("")

    for section in windows:
        wd = section["window_days"]
        lines.append(f"## Window {wd}d")
        lines.append("")
        lines.append(
            f"- Current: {section['current_start']} -> {section['current_end']} "
            f"(records={section['current_record_count']})"
        )
        lines.append(
            f"- Previous: {section['previous_start']} -> {section['previous_end']} "
            f"(records={section['previous_record_count']})"
        )
        lines.append("")

        lines.append("### Source Heat Trends")
        if section["source_trends"]:
            for row in section["source_trends"]:
                lines.append(
                    "- "
                    f"{row['source']}: trend={row['trend']}, "
                    f"current_count={row['current_count']}, "
                    f"current_avg_hotness={row['current_avg_hotness']}, "
                    f"delta_avg_hotness={row['delta_avg_hotness']}, "
                    f"delta_count_pct={row['delta_count_pct']}%"
                )
        else:
            lines.append("- No data")
        lines.append("")

        lines.append("### Source Top Keywords")
        by_source = section["keyword_trends"]["by_source"]
        if by_source:
            for source, kws in by_source.items():
                lines.append(f"- {source}")
                if not kws:
                    lines.append("  - No keywords")
                    continue
                for kw in kws:
                    lines.append(
                        f"  - {kw['keyword']} "
                        f"(score={kw['score']}, count={kw['count']}, delta={kw['delta_score']})"
                    )
        else:
            lines.append("- No data")
        lines.append("")

        lines.append("### Repeated Event Trajectories")
        events = section["repeated_events"]
        if events:
            for idx, evt in enumerate(events, start=1):
                lines.append(
                    f"{idx}. {evt['title']} "
                    f"(occurrences={evt['occurrences']}, sources={evt['source_count']}, "
                    f"first={evt['first_seen']}, last={evt['last_seen']})"
                )
                lines.append(
                    "   - trajectory: "
                    + " -> ".join(f"{x['date']}:{x['count']}" for x in evt["daily_series"])
                )
                if evt["urls"]:
                    lines.append("   - urls: " + " | ".join(evt["urls"]))
        else:
            lines.append("- No repeated events detected")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    windows = parse_windows(args.windows)
    archive_root = Path(args.archive_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records, dates = load_records(archive_root)
    generated_at = dt.datetime.now(dt.timezone.utc)

    if not records or not dates:
        payload = {
            "schema_version": "1.0",
            "generated_at": generated_at.isoformat(),
            "archive_root": str(archive_root),
            "error": "No archive records found",
            "windows": windows,
        }
        json_path = out_dir / "archive_analysis_empty.json"
        md_path = out_dir / "archive_analysis_empty.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(
            "# Archive Trend Analysis\n\nNo archive records found.\n",
            encoding="utf-8",
        )
        print(f"[WARN] No archive records found under: {archive_root}")
        print(f"[OK] Wrote JSON: {json_path}")
        print(f"[OK] Wrote Markdown: {md_path}")
        return 0

    latest_date = max(dates)
    earliest_date = min(dates)

    sections: list[dict[str, Any]] = []
    for wd in windows:
        current_start = latest_date - dt.timedelta(days=wd - 1)
        current_end = latest_date
        previous_end = current_start - dt.timedelta(days=1)
        previous_start = previous_end - dt.timedelta(days=wd - 1)

        current_days = set(day_list(current_start, current_end))
        previous_days = set(day_list(previous_start, previous_end))

        current_records = [r for r in records if r["date"].isoformat() in current_days]
        previous_records = [r for r in records if r["date"].isoformat() in previous_days]

        src_trend_rows = source_trends(
            current=current_records,
            previous=previous_records,
            top_sources=args.top_sources,
        )
        kw_trend = keyword_trends(
            current=current_records,
            previous=previous_records,
            top_keywords=args.top_keywords,
            top_sources=args.top_sources,
        )
        repeated = repeated_event_trajectories(
            current=current_records,
            top_events=args.top_events,
        )

        sections.append(
            {
                "window_days": wd,
                "current_start": current_start.isoformat(),
                "current_end": current_end.isoformat(),
                "previous_start": previous_start.isoformat(),
                "previous_end": previous_end.isoformat(),
                "current_record_count": len(current_records),
                "previous_record_count": len(previous_records),
                "source_trends": src_trend_rows,
                "keyword_trends": kw_trend,
                "repeated_events": repeated,
            }
        )

    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "archive_root": str(archive_root),
        "data_start": earliest_date.isoformat(),
        "data_end": latest_date.isoformat(),
        "total_records": len(records),
        "windows": sections,
    }

    stamp = latest_date.strftime("%Y%m%d")
    json_path = out_dir / f"archive_analysis_{stamp}.json"
    md_path = out_dir / f"archive_analysis_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_text = render_markdown(
        generated_at=payload["generated_at"],
        archive_root=payload["archive_root"],
        data_start=payload["data_start"],
        data_end=payload["data_end"],
        total_records=payload["total_records"],
        windows=payload["windows"],
    )
    md_path.write_text(md_text, encoding="utf-8")

    print(f"[OK] Wrote JSON: {json_path}")
    print(f"[OK] Wrote Markdown: {md_path}")
    for section in sections:
        print(
            f"[OK] Window {section['window_days']}d: "
            f"records={section['current_record_count']}, "
            f"sources={len(section['source_trends'])}, "
            f"repeated_events={len(section['repeated_events'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
