## $hot-news-daily-brief
1. Use a two-stage pipeline: online collector writes `./data/inbox/news_candidates_*.json`, offline Codex task reads local JSON and generates digest.
2. Rank stories with explicit hotness scoring (prominence, engagement, source authority, cross-source pickup, impact).
3. Output bilingual digest with Top 5 first, then `[时政]`, `[金融]`, `[科技-AI]`, `[科技-其他]`.
4. Include `English summary`, `中文总结`, source URL, and absolute published time for every story.
5. Optionally send digest by Gmail API OAuth (preferred) or SMTP fallback.
