# Cadence — 5-Week Cycle (Dual-Sender)

## Overview

Each contact goes through a repeating 5-week cycle. They stay in this loop indefinitely until they reply or are suppressed. Each week has TWO touches: Gabby's primary email + Alex's follow-up 2 days later.

## Week-by-Week

| Week | Gabby Email (Day 0) | Alex Follow-Up (Day 2) |
|------|---------------------|------------------------|
| 1 | Intro + Observation — services list, soft CTA | After-hours leads angle — "who follows up?" |
| 2 | Equity Mining — reframes the problem, different pain | Service lane equity — "sitting on a goldmine" |
| 3 | Spread Thin — BDC support, team backup | Overflow support — "what if your team had backup?" |
| 4 | Testimonial — referral offer, door open | Real numbers — "what 90 days looks like" |
| 5 | Cooldown — no emails | No follow-ups either |

## Contact State Machine

```
[active, week=1] → Gabby sends email 1 → [active, week=2]
         ↓ (2 days later, if no bounce)
         → Alex sends follow-up 1

[active, week=2] → Gabby sends email 2 → [active, week=3]
         ↓ (2 days later, if no bounce)
         → Alex sends follow-up 2

[active, week=3] → Gabby sends email 3 → [active, week=4]
         ↓ (2 days later, if no bounce)
         → Alex sends follow-up 3

[active, week=4] → Gabby sends email 4 → [active, week=5]
         ↓ (2 days later, if no bounce)
         → Alex sends follow-up 4

[active, week=5] → cooldown complete → [active, week=1], cycle_count++
                                               ↓
                              [any active week] → reply received → [conversation]
                              [any active week] → negative reply → [suppressed]
                              [any active week] → bounce detected → [suppressed]
```

## Key Rules

- **Gabby always sends first.** Alex only sends to contacts where Gabby's email was delivered (no bounce detected).
- **2-day gap minimum.** Alex's follow-up waits at least 2 days after Gabby's send (configurable via `--delay-days`).
- **Same week, different content.** Alex's follow-up template matches Gabby's week number but uses completely different copy.
- **One follow-up per Gabby send.** The `followup_sent_at` column prevents duplicate follow-ups for the same weekly send.
- **Bounces suppress both.** If Gabby's email bounces (detected via reply classification), the contact is suppressed and Alex never sends.

## Re-entry After Cooldown

When week 5 completes, the contact re-enters week 1 of a fresh cycle. The cycle count increments. The AI research pipeline re-runs to find fresh personalization hooks — no recycled research from previous cycles.

## Cycle Count

Used for reporting only. A contact with `cycle_count >= 6` (roughly 6 months) who has never replied may warrant review.

## Daily Volume

100 sends per day. The daily query picks the 100 contacts whose last send was longest ago among those due. This naturally distributes the load evenly across the week.
