#!/usr/bin/env python3
"""
Append weekly cross-window trend interpretation into daily report markdown.

This script is intended to run in Stage C before email rendering/sending.
By default it only runs on Sunday (ISO weekday=7), and inserts section
before "数据源抓取与有效性（过去24小时）" so primary report order stays intact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

HOTNESS_WEIGHTS = {
    "editorial_prominence": 0.30,
    "engagement_velocity": 0.25,
    "cross_source_pickup": 0.20,
    "source_authority": 0.15,
    "public_impact_scope": 0.10,
}

WEEKLY_SECTION_TITLE = "周度趋势分析（跨7/30/90/180/360天）"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append weekly trend interpretation into daily digest markdown."
    )
    parser.add_argument("--report", required=True, help="Daily markdown report file path")
    parser.add_argument(
        "--report-date",
        default="",
        help="Report date YYYY-MM-DD (default: infer from report filename, else today)",
    )
    parser.add_argument(
        "--archive-root",
        default="./data/archive/by_date_source",
        help="Archive root directory",
    )
    parser.add_argument(
        "--analysis-script",
        default="./.agents/skills/hot-news-daily-brief/scripts/analyze_archive.py",
        help="Path to analyze_archive.py",
    )
    parser.add_argument(
        "--analysis-out-dir",
        default="./Report/archive-analysis",
        help="Output directory used by analyze_archive.py",
    )
    parser.add_argument(
        "--windows",
        default="7,30,90,180,360",
        help="Windows passed to analyze_archive.py",
    )
    parser.add_argument(
        "--only-weekday",
        type=int,
        default=7,
        help="Run only when report_date.isoweekday() equals this value (default: 7=Sunday)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run regardless of weekday",
    )
    parser.add_argument(
        "--top-examples",
        type=int,
        default=3,
        help="Representative stories shown per window",
    )
    parser.add_argument(
        "--top-sources",
        type=int,
        default=3,
        help="Top source-trend rows shown per window",
    )
    parser.add_argument(
        "--top-keywords",
        type=int,
        default=6,
        help="Top overall keywords shown per window",
    )
    parser.add_argument(
        "--top-events",
        type=int,
        default=2,
        help="Top repeated events shown per window",
    )
    return parser.parse_args()


def parse_iso_datetime(value: str) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_report_date(report: Path, report_date_raw: str) -> dt.date:
    if report_date_raw:
        return dt.date.fromisoformat(report_date_raw.strip())

    match = re.search(r"(\d{4}-\d{2}-\d{2})", report.name)
    if match:
        return dt.date.fromisoformat(match.group(1))
    return dt.date.today()


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
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            urllib.parse.urlencode(kept),
            "",
        )
    )


def title_fingerprint(title: str) -> str:
    text = title.strip().lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    parts = [piece for piece in text.split() if piece]
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return " ".join(ordered[:10])


def event_key(item: dict[str, Any]) -> str:
    fp = title_fingerprint(str(item.get("title", "")))
    if fp and len(fp.split()) >= 3:
        return f"title:{fp}"
    normalized = normalize_url(str(item.get("url", "")))
    if normalized:
        parsed = urllib.parse.urlsplit(normalized)
        host_path = f"{parsed.netloc}{parsed.path}".lower()
        if host_path:
            return f"url:{host_path}"
    if fp:
        return f"title:{fp}"
    rec_id = str(item.get("id", "")).strip()
    if rec_id:
        return f"id:{rec_id}"
    return ""


def run_archive_analysis(
    python_bin: str,
    analysis_script: Path,
    archive_root: Path,
    analysis_out_dir: Path,
    windows: str,
) -> None:
    cmd = [
        python_bin,
        str(analysis_script),
        "--archive-root",
        str(archive_root),
        "--out-dir",
        str(analysis_out_dir),
        "--windows",
        windows,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr if stderr else stdout
        raise RuntimeError(f"analyze_archive.py failed: {detail}")


def resolve_analysis_json(analysis_out_dir: Path, report_date: dt.date) -> Path:
    expected = analysis_out_dir / f"archive_analysis_{report_date.strftime('%Y%m%d')}.json"
    if expected.exists():
        return expected

    candidates = sorted(
        analysis_out_dir.glob("archive_analysis_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No archive analysis JSON found in {analysis_out_dir}")


def load_archive_records(archive_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not archive_root.exists():
        return records

    for date_dir in sorted(archive_root.iterdir()):
        if not date_dir.is_dir():
            continue
        try:
            dir_date = dt.date.fromisoformat(date_dir.name)
        except ValueError:
            continue

        for source_file in sorted(date_dir.glob("*.json")):
            try:
                payload = json.loads(source_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            source_name = str(payload.get("source", "")).strip() or source_file.stem
            items = payload.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                published = parse_iso_datetime(str(item.get("published_at", "")))
                fetched = parse_iso_datetime(str(item.get("fetched_at", "")))
                record_dt = published or fetched
                record_date = record_dt.date() if record_dt else dir_date

                record = {
                    "title": str(item.get("title", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "source": str(item.get("source", "")).strip() or source_name,
                    "date": record_date,
                    "datetime": record_dt.isoformat() if record_dt else "",
                    "hotness": hotness_score(item),
                    "event_key": event_key(item),
                }
                records.append(record)
    return records


def parse_window_dates(section: dict[str, Any]) -> tuple[dt.date, dt.date]:
    start = dt.date.fromisoformat(str(section["current_start"]))
    end = dt.date.fromisoformat(str(section["current_end"]))
    return start, end


def records_in_window(records: list[dict[str, Any]], start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    return [record for record in records if start <= record["date"] <= end]


def pick_representative_stories(records: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    sorted_rows = sorted(
        records,
        key=lambda r: (float(r.get("hotness", 0.0)), str(r.get("datetime", "")), r.get("title", "")),
        reverse=True,
    )
    for row in sorted_rows:
        key = str(row.get("event_key", "")).strip() or str(row.get("title", "")).strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        picked.append(row)
        if len(picked) >= top_n:
            break
    return picked


def avg_hotness(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    values = [float(r.get("hotness", 0.0)) for r in records]
    return round(sum(values) / len(values), 4)


def delta_label(current: float, previous: float) -> str:
    delta = round(current - previous, 4)
    if abs(delta) < 0.05:
        return "基本持平"
    if delta > 0:
        return f"上升 {delta}"
    return f"下降 {abs(delta)}"


def format_story_bullet(record: dict[str, Any]) -> str:
    title = record.get("title") or "(untitled)"
    source = record.get("source") or "unknown"
    date = record.get("date")
    if isinstance(date, dt.date):
        date_text = date.isoformat()
    else:
        date_text = str(date)
    hotness = record.get("hotness", 0.0)
    url = str(record.get("url", "")).strip()
    if url:
        return f"- [{title}]({url}) | 来源: {source} | 日期: {date_text} | 热度分: {hotness}"
    return f"- {title} | 来源: {source} | 日期: {date_text} | 热度分: {hotness}"


def build_window_section(
    section: dict[str, Any],
    all_records: list[dict[str, Any]],
    top_examples: int,
    top_sources: int,
    top_keywords: int,
    top_events: int,
) -> list[str]:
    lines: list[str] = []
    window_days = int(section.get("window_days", 0))
    current_count = int(section.get("current_record_count", 0))
    previous_count = int(section.get("previous_record_count", 0))

    start, end = parse_window_dates(section)
    previous_start = dt.date.fromisoformat(str(section["previous_start"]))
    previous_end = dt.date.fromisoformat(str(section["previous_end"]))

    current_records = records_in_window(all_records, start, end)
    previous_records = records_in_window(all_records, previous_start, previous_end)
    current_avg = avg_hotness(current_records)
    previous_avg = avg_hotness(previous_records)

    lines.append(f"### {window_days}天窗口")
    lines.append(f"- 时间范围: {start.isoformat()} -> {end.isoformat()}")

    if previous_count <= 0:
        lines.append(
            f"- 趋势解读: 过去{window_days}天共 {current_count} 条候选，前一周期样本不足，"
            "当前窗口形成了第一批可对比热度基线。"
        )
    else:
        delta_count = current_count - previous_count
        delta_pct = round(delta_count * 100.0 / previous_count, 2)
        lines.append(
            f"- 趋势解读: 过去{window_days}天共 {current_count} 条候选，较前一周期"
            f" {previous_count} 条变化 {delta_count:+d} 条（{delta_pct:+.2f}%）；"
            f"平均热度 {delta_label(current_avg, previous_avg)}。"
        )

    source_rows = section.get("source_trends", [])
    if source_rows:
        lines.append("- 来源变化（Top）:")
        for row in source_rows[:top_sources]:
            trend = row.get("trend", "")
            lines.append(
                "  - "
                f"{row.get('source', 'unknown')}: trend={trend}, "
                f"count={row.get('current_count', 0)} (prev={row.get('previous_count', 0)}), "
                f"avg_hotness={row.get('current_avg_hotness', 0.0)}"
            )

    keyword_rows = section.get("keyword_trends", {}).get("overall_top_keywords", [])
    if keyword_rows:
        keyword_bits = []
        for row in keyword_rows[:top_keywords]:
            keyword = row.get("keyword", "")
            score = row.get("score", 0.0)
            delta_score = row.get("delta_score", 0.0)
            keyword_bits.append(f"{keyword}(score={score}, Δ={delta_score})")
        lines.append("- 热词变化: " + "; ".join(keyword_bits))

    events = section.get("repeated_events", [])
    if events:
        lines.append("- 重复事件轨迹:")
        for event in events[:top_events]:
            lines.append(
                "  - "
                f"{event.get('title', '(untitled)')} | occurrences={event.get('occurrences', 0)}, "
                f"sources={event.get('source_count', 0)}, "
                f"first={event.get('first_seen', '')}, last={event.get('last_seen', '')}"
            )

    examples = pick_representative_stories(current_records, top_examples)
    if examples:
        lines.append("- 代表新闻（按热度与去重后排序）:")
        for example in examples:
            lines.append("  " + format_story_bullet(example))

    lines.append("")
    return lines


def build_weekly_section(
    analysis_payload: dict[str, Any],
    all_records: list[dict[str, Any]],
    top_examples: int,
    top_sources: int,
    top_keywords: int,
    top_events: int,
) -> str:
    generated_at = str(analysis_payload.get("generated_at", ""))
    data_start = str(analysis_payload.get("data_start", ""))
    data_end = str(analysis_payload.get("data_end", ""))
    total_records = int(analysis_payload.get("total_records", 0))

    lines: list[str] = []
    lines.append(f"## {WEEKLY_SECTION_TITLE}")
    lines.append("")
    lines.append(f"- 生成时间(UTC): {generated_at}")
    lines.append(f"- 历史覆盖: {data_start} -> {data_end}")
    lines.append(f"- 样本总量: {total_records}")
    lines.append("- 说明: 以下为跨窗口趋势解读，结合具体新闻样本用于判断热度变化是否具备持续性。")
    lines.append("")

    windows = analysis_payload.get("windows", [])
    if not isinstance(windows, list) or not windows:
        lines.append("- 无可用窗口数据。")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    for section in windows:
        if not isinstance(section, dict):
            continue
        lines.extend(
            build_window_section(
                section=section,
                all_records=all_records,
                top_examples=top_examples,
                top_sources=top_sources,
                top_keywords=top_keywords,
                top_events=top_events,
            )
        )

    return "\n".join(lines).rstrip() + "\n"


def remove_existing_weekly_section(text: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(WEEKLY_SECTION_TITLE)}\n.*?(?=^##\s+|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    cleaned = re.sub(pattern, "", text).rstrip()
    return cleaned + "\n"


def upsert_before_source_health(text: str, section_md: str) -> str:
    marker = re.search(r"^##\s+数据源抓取与有效性[^\n]*", text, flags=re.MULTILINE)
    if marker:
        head = text[: marker.start()].rstrip()
        tail = text[marker.start() :].lstrip("\n")
        return f"{head}\n\n{section_md.rstrip()}\n\n{tail.rstrip()}\n"
    return text.rstrip() + "\n\n" + section_md.rstrip() + "\n"


def should_run(report_date: dt.date, only_weekday: int, force: bool) -> bool:
    if force:
        return True
    if only_weekday <= 0:
        return True
    return report_date.isoweekday() == only_weekday


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[ERROR] Report not found: {report_path}", file=sys.stderr)
        return 1

    try:
        report_date = parse_report_date(report_path, args.report_date)
    except ValueError as exc:
        print(f"[ERROR] Invalid report date: {exc}", file=sys.stderr)
        return 1

    if not should_run(report_date, args.only_weekday, args.force):
        print(
            "[INFO] Skip weekly trend section: "
            f"report_date={report_date.isoformat()}, "
            f"isoweekday={report_date.isoweekday()}, target={args.only_weekday}"
        )
        return 0

    archive_root = Path(args.archive_root)
    analysis_out_dir = Path(args.analysis_out_dir)
    analysis_script = Path(args.analysis_script)

    if not analysis_script.exists():
        print(f"[ERROR] analyze script not found: {analysis_script}", file=sys.stderr)
        return 1

    analysis_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        run_archive_analysis(
            python_bin=sys.executable,
            analysis_script=analysis_script,
            archive_root=archive_root,
            analysis_out_dir=analysis_out_dir,
            windows=args.windows,
        )
        analysis_json_path = resolve_analysis_json(analysis_out_dir, report_date)
        payload = json.loads(analysis_json_path.read_text(encoding="utf-8"))
        records = load_archive_records(archive_root)
        weekly_section = build_weekly_section(
            analysis_payload=payload,
            all_records=records,
            top_examples=args.top_examples,
            top_sources=args.top_sources,
            top_keywords=args.top_keywords,
            top_events=args.top_events,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to build weekly trend section: {exc}", file=sys.stderr)
        return 1

    original = report_path.read_text(encoding="utf-8")
    cleaned = remove_existing_weekly_section(original)
    updated = upsert_before_source_health(cleaned, weekly_section)
    report_path.write_text(updated, encoding="utf-8")

    snippet_path = analysis_out_dir / f"weekly_trend_section_{report_date.strftime('%Y%m%d')}.md"
    snippet_path.write_text(weekly_section, encoding="utf-8")

    print(f"[OK] Weekly trend section updated: {report_path}")
    print(f"[OK] Weekly trend snippet: {snippet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
