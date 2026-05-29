# Cadence — 5-Week Cycle

## Overview

Each contact goes through a repeating 5-week cycle. They stay in this loop indefinitely until they reply or are suppressed.

## Week-by-Week

| Week | Email | Theme | Action |
|------|-------|-------|--------|
| 1 | Email 1 | Intro + Observation | Personalized opener referencing their dealership/brand. Value prop tied to their context. Soft CTA. |
| 2 | Email 2 | Different Angle | New observation they may not have considered. Reframes their problem. Different pain point than week 1. |
| 3 | Email 3 | Social Proof | Reference a comparable dealership type/size outcome. Low-pressure "here's what's possible." |
| 4 | Email 4 | Final Nudge | Wrap up, acknowledge no pressure. Fresh piece of value. Door open for future. |
| 5 | Cooldown | None | No email sent. Contact rests. |
| → | Restart | Email 1 | New cycle. `peer_outreach_cycle_count` increments. |

## Contact State Machine

```
[active, week=1] → send email 1 → [active, week=2]
[active, week=2] → send email 2 → [active, week=3]
[active, week=3] → send email 3 → [active, week=4]
[active, week=4] → send email 4 → [active, week=5]
[active, week=5] → cooldown complete → [active, week=1], cycle_count++
                                               ↓
                              [any active week] → reply received → [conversation]
                              [any active week] → negative reply → [suppressed]
```

## Re-entry After Cooldown

When week 5 completes, the contact re-enters week 1 of a fresh cycle. The cycle count increments. The AI research pipeline re-runs to find fresh personalization hooks — no recycled research from previous cycles.

## Cycle Count

Used for reporting only. A contact with `cycle_count >= 6` (roughly 6 months) who has never replied may warrant review.

## Daily Volume

100 sends per day. The daily query picks the 100 contacts whose last send was longest ago among those due. This naturally distributes the load evenly across the week.
