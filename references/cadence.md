# Cadence — 5-Week Cycle

## Overview

Each contact goes through a repeating 5-week cycle. They stay in this loop indefinitely until they reply or are suppressed. Each week Gabby sends the same email from two addresses — the primary send and a follow-up resend 2 days later.

## Week-by-Week

| Week | Email | Theme | Day 0 | Day 2 |
|------|-------|-------|-------|-------|
| 1 | Email 1 | Intro + Observation | gabby@trafficdriver.ai | auto@paramountals.net |
| 2 | Email 2 | Different Angle | gabby@trafficdriver.ai | auto@paramountals.net |
| 3 | Email 3 | Social Proof | gabby@trafficdriver.ai | auto@paramountals.net |
| 4 | Email 4 | Final Nudge | gabby@trafficdriver.ai | auto@paramountals.net |
| 5 | Cooldown | None | No emails | No resends |
| → | Restart | Email 1 | gabby@trafficdriver.ai | auto@paramountals.net |

Same template, same subject, same Gabby name. Only the sending address changes on the resend.

## Contact State Machine

```
[active, week=1] → Gabby sends email 1 → [active, week=2]
         ↓ (2 days later, if no bounce)
         → Gabby resends email 1 from second address

[active, week=2] → Gabby sends email 2 → [active, week=3]
         ↓ (2 days later, if no bounce)
         → Gabby resends email 2 from second address

...and so on through week 4.

[active, week=5] → cooldown complete → [active, week=1], cycle_count++

[any active week] → reply received → [conversation]
[any active week] → negative reply → [suppressed]
[any active week] → bounce detected → [suppressed]
```

## Key Rules

- **Gabby always sends first** from `gabby@trafficdriver.ai`. The resend only goes to contacts where the primary send didn't bounce.
- **2-day gap minimum.** The resend waits at least 2 days after the primary send (configurable via `--delay-days`).
- **Same email, different address.** The resend uses the identical template, subject options, and signature. Recipient sees the same person.
- **One resend per primary send.** The `followup_sent_at` column prevents duplicate resends.
- **Bounces suppress both.** If the primary email bounces, the contact is suppressed and the resend is skipped.

## Re-entry After Cooldown

When week 5 completes, the contact re-enters week 1 of a fresh cycle. The cycle count increments.
