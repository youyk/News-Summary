## $hot-news-daily-brief
1. Use a two-stage pipeline: online collector writes `./data/inbox/news_candidates_*.json` and date/source archives under `./data/archive/by_date_source/`, offline Codex task reads local JSON and generates digest.
2. Rank stories with explicit hotness scoring (prominence, engagement, source authority, cross-source pickup, impact).
3. Output bilingual digest with Top 5 first, then `当日总体总结（约300字）`, `[时政]`, `[金融]`, `[科技-AI]`, `[科技-其他]`, optional `[X 热点]`, and place `数据源抓取与有效性（过去24小时）` at the end; each section aims for Top3 stories.
4. Build Top 5 from section champions (Top1 of each section) plus one wildcard item.
5. Include `English summary` (at least 200 English words, with concrete quantitative evidence), `中文翻译` (paragraph-by-paragraph literal translation), `English word count`, source URL, and absolute published time for every story. `评论` is optional and currently off by default.
6. Optionally send digest by Gmail API OAuth (preferred) or SMTP fallback.
