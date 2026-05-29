---
name: peer-outreach
description: "Manages the personal peer-to-peer plain-text email outreach system for TrafficDriver.ai. Sends 1:1 conversational emails from gabby@trafficdriver.ai to General Managers at dealerships using a 5-week cadence (4 weekly emails + 1 cooldown). Use when Matt asks to run, build, or modify the peer outreach system, send outreach emails, or handle replies. Covers email generation, SendGrid sending, reply classification, and lead routing to growth@paramountals.com."
---

# Peer-to-Peer Outreach System

Send plain-text, 1:1 conversational emails from Gabby to dealership GMs. 100 emails/day via SendGrid, cycling through the contact database on a 5-week loop.

## Sender Identity

- **Name:** Gabby Pals
- **Email:** gabby@trafficdriver.ai
- **Send service:** SendGrid API (trafficdriver.ai account)
- **Signature:** See `assets/signature.html`

## Quick Reference

| Detail | Value |
|--------|-------|
| Sends per day | 100 |
| Cadence | 4 weeks on, 1 week cooldown |
| Target | GMs only (valid emails, not suppressed) |
| Format | Plain text body + HTML signature |
| Reply routing | Intent → `growth@paramountals.com` lead notification |

## Core Workflow

### 1. Contact Selection

Contacts are stored in the `peer_outreach_contacts` table in the `sales_crm` database.

Run `scripts/seed_contacts.py` to initially populate this table from the main CRM, filtering for GMs with valid emails.

For daily sends, run `scripts/send_outreach_emails.py` which queries contacts due today automatically.

### 2. Email Composition

No per-contact AI research needed. Each week's email is static copy with `{first_name}` as the only merge field. The audience is specific (dealership GMs) so the messaging fits universally. See `references/email-templates.md` for full templates.

Format: Multipart email — plain text body + HTML signature from `assets/signature.html`.

### 3. Sending via SendGrid

Run `python3 scripts/send_outreach_emails.py` to send today's batch.

- `--dry-run` previews without sending
- `--limit N` caps the batch size
- Requires `SENDGRID_API_KEY_TD` environment variable

Sends 100 emails/day through SendGrid API. Throttles with randomized 2-5 minute gaps. Spreads across 4-6 hours.

### 4. 5-Week Cadence

| Week | Action |
|------|--------|
| 1 | Email 1 — Intro + personalized observation |
| 2 | Email 2 — Different angle / new pain point |
| 3 | Email 3 — Social proof / outcome mention |
| 4 | Email 4 — Final nudge / wrap up |
| 5 | Cooldown — no emails |
| → | Restart at Week 1 |

Full cadence details in `references/cadence.md`.

### 5. Reply Handling

Run `python3 scripts/process_replies.py --imap` to poll Gabby's inbox for new replies.

- `--dry-run` previews without sending notifications or auto-replies
- `--webhook-payload '...'` for testing with a JSON payload
- Requires `SENDGRID_API_KEY_TD` and `IMAP_PASS` environment variables

For each reply:
1. Match to original contact via email
2. Classify intent (positive / negative / out-of-office / bounce)
3. If positive → send lead notification to `growth@paramountals.com` with full details + auto-reply from Gabby to continue the conversation
4. If negative → mark suppressed, remove from rotation
5. If OOO → log, retry next cycle

Full reply handling spec in `references/reply-handling.md`.

## Database Fields Required

See `references/database.md` for full schema.
