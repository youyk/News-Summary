## $hot-news-daily-brief
1. Use a two-stage pipeline: online collector writes `./data/inbox/news_candidates_*.json`, offline Codex task reads local JSON and generates digest.
2. Rank stories with explicit hotness scoring (prominence, engagement, source authority, cross-source pickup, impact).
3. Output bilingual digest with Top 5 first, then `当日总体总结（约300字）`, `数据源抓取与有效性（过去24小时）`, `[时政]`, `[金融]`, `[科技-AI]`, `[科技-其他]`; each section aims for Top3 stories.
4. Build Top 5 from section champions (Top1 of each section) plus one wildcard item.
5. Include `English summary` (single paragraph, at least 200 English words), `中文总结`, `English word count`, source URL, and absolute published time for every story.
6. Optionally send digest by Gmail API OAuth (preferred) or SMTP fallback.
