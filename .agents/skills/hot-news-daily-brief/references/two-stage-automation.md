# Two-Stage Automation (No Internet in Codex Runtime)

Use this design when Codex automation cannot browse the internet.

## Stage A: Online Collection

Run in a network-enabled runtime before digest generation.

Command:

```bash
# Optional: configure source credentials in local env file first
# cp /Users/yongkang/projects/skills/News-Summary/scripts/news_sources.env.example \
#   /Users/yongkang/projects/skills/News-Summary/scripts/news_sources.env
# # Fill REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET when reddit access is blocked.
# # Optional social sources:
# #   - WEIBO_COOKIE / TOUTIAO_COOKIE
# #   - X_HANDLES + X_NITTER_INSTANCES
# #   - X_RSS_URLS / XIAOHONGSHU_RSS_URLS (RSSHub or equivalent bridge)
/bin/zsh /Users/yongkang/projects/skills/News-Summary/scripts/stage_a_collect.sh
```

Expected output:
- `./data/inbox/news_candidates_YYYYMMDDTHHMMSSZ.json`

## Stage B: Offline Digest (Codex Automation)

Run in Codex automation with no internet.
Codex only reads local files and writes report.

Prompt template:

```text
Use [$hot-news-daily-brief](/Users/yongkang/projects/skills/News-Summary/.agents/skills/hot-news-daily-brief/SKILL.md).
Do not browse the internet.
Read the latest ./data/inbox/news_candidates_*.json, keep last-24-hour items, score hotness, deduplicate events, and generate bilingual digest in this order:
Top 5, 当日总体总结（约300字）, 数据源抓取与有效性（过去24小时）, [时政], [金融], [科技-AI], [科技-其他].
Each story must include Why hot, English summary, 中文总结, English word count, Source URL, and absolute published time.
Hard constraints:
1) Each story's English summary must be a single long-form paragraph with at least 200 English words.
2) If any story is under 200 words, expand it before finalizing.
3) Keep 当日总体总结 around 300 Chinese characters.
4) Add a source-health section from latest fetch_report, including successful sources and failed sources.
5) Each category section should output Top3 stories whenever enough reliable candidates exist.
6) Top 5 must use section champions: Top1 from each section + 1 wildcard next-best item.
Write result to ./Report/YYYY-MM-DD.md and include full digest in inbox output.
```

## Stage C: Optional Email Send (Network Required)

Run in a network-enabled runtime after report is generated.

Preferred Gmail API command:

```bash
/bin/cp /Users/yongkang/projects/skills/News-Summary/scripts/gmail.env.example \
  /Users/yongkang/projects/skills/News-Summary/scripts/gmail.env
# Edit gmail.env with real OAuth values and set NEWS_DIGEST_TO.
# Optional:
# export NEWS_DIGEST_MAIL_CONTENT_MODE="multipart"  # plain + HTML (recommended)
# export NEWS_DIGEST_MAIL_CONTENT_MODE="plain"      # plain only
# export NEWS_DIGEST_MAIL_CONTENT_MODE="html-only"  # HTML only
/bin/zsh /Users/yongkang/projects/skills/News-Summary/scripts/stage_c_send_gmail.sh
```

SMTP fallback:

```bash
python3 .agents/skills/hot-news-daily-brief/scripts/send_summary_email.py \
  --to "$NEWS_DIGEST_TO" \
  --subject "Daily Hot News Digest - YYYY-MM-DD" \
  --body-file ./Report/YYYY-MM-DD.md \
  --html-file ./Report/YYYY-MM-DD.html
```

## Scheduling Suggestion

- 06:30 local time: Stage A (online collect)
- 07:00 local time: Stage B (Codex offline summarize)
- 07:05 local time: Stage C (optional email send, online)
