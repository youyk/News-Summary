# Hotness Scoring Rubric

Use this rubric to rank candidate stories from the last 24 hours.

## Scoring Dimensions

Score each dimension from 0 to 5, then apply weights.

1. Editorial prominence (weight 0.30)
- 5: Top headline / homepage lead / breaking banner on major outlet.
- 4: Front-page placement or top section lead.
- 3: Not lead, but clearly featured by reputable outlets.
- 2: Niche section only.
- 1: Mentioned but not highlighted.
- 0: No editorial prominence.

2. Engagement velocity (weight 0.25)
- 5: Extremely high activity (comments, reposts, upvotes, shares) in short time.
- 4: Strong and sustained engagement.
- 3: Moderate engagement.
- 2: Low engagement.
- 1: Very low engagement.
- 0: No measurable engagement.

3. Cross-source pickup (weight 0.20)
- 5: Covered quickly by many independent major outlets.
- 4: Covered by several independent outlets.
- 3: Covered by at least two credible outlets.
- 2: Covered by one credible outlet plus weak repeats.
- 1: Single-source only.
- 0: No credible pickup.

4. Source authority (weight 0.15)
- 5: Official source or tier-1 newsroom.
- 4: Reputable mainstream publication.
- 3: Established but secondary publication.
- 2: Community source with partial verification.
- 1: Weak authority.
- 0: Unknown or unreliable source.

5. Public-impact scope (weight 0.10)
- 5: Broad policy, market, infrastructure, or societal impact.
- 4: Major industry or regional impact.
- 3: Sector-level impact.
- 2: Narrow community impact.
- 1: Small audience impact.
- 0: No clear impact.

## Final Score

Use:

`hotness = 0.30*p + 0.25*e + 0.20*c + 0.15*a + 0.10*i`

Where:
- `p`: editorial prominence
- `e`: engagement velocity
- `c`: cross-source pickup
- `a`: source authority
- `i`: public-impact scope

## Threshold Guidance

- `>= 4.0`: Strong Top 5 candidate.
- `3.3 - 3.9`: Include in category section.
- `2.8 - 3.2`: Include only if category lacks better stories.
- `< 2.8`: Usually exclude from final digest.

## Disqualifiers

Exclude items even with high virality when:
- No reliable verification exists.
- Content is clearly promotional/paid without news value.
- Publication time is outside the 24-hour window and not a meaningful update.

## Tie-Break Rules

If scores are close, prioritize in this order:
1. Higher verified real-world impact.
2. More independent source confirmation.
3. More recent update time.

