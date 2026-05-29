# Peer Outreach System

Plain-text, 1:1 conversational email outreach from Gabby Pals to dealership General Managers. 100 emails/day via Gmail SMTP, cycling through contacts on a 5-week cadence (4 weekly emails + 1 cooldown).

## How It Works

1. **Seed contacts** from your CRM into `peer_outreach_contacts`
2. **Send emails** — queries contacts due today, fills templates, sends via Gmail SMTP
3. **Process replies** — polls Gabby's inbox, classifies intent, routes leads

### 5-Week Cadence

| Week | Action |
|------|--------|
| 1 | Email 1 — Intro + service overview |
| 2 | Email 2 — Equity mining angle |
| 3 | Email 3 — BDC support / spread thin |
| 4 | Email 4 — Social proof / final nudge |
| 5 | Cooldown — no emails |
| → | Restart at Week 1 |

### Reply Handling

| Intent | Action |
|--------|--------|
| positive | Lead notification to growth@paramountals.com + auto-reply from Gabby |
| negative | Mark suppressed, remove from rotation |
| ooo | Log, retry next cycle |
| bounce | Mark invalid, suppress |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/seed_contacts.py` | Import GMs from CRM into peer_outreach_contacts |
| `scripts/send_outreach_emails.py` | Send today's batch of outreach emails |
| `scripts/process_replies.py` | Poll inbox for replies, classify, route leads |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials

# Seed contacts from CRM
python3 scripts/seed_contacts.py --dry-run
python3 scripts/seed_contacts.py

# Send outreach (dry run first)
python3 scripts/send_outreach_emails.py --dry-run
python3 scripts/send_outreach_emails.py

# Process replies
python3 scripts/process_replies.py --dry-run
python3 scripts/process_replies.py
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string for peer_outreach_contacts DB |
| `MAIN_CRM_DATABASE_URL` | (Optional) Source CRM database for seeding contacts |
| `SMTP_PASSWORD` | Gmail app password for gabby@trafficdriver.ai |
| `IMAP_PASSWORD` | Gmail app password for gabby@trafficdriver.ai (same as SMTP) |

## Database

PostgreSQL. See `references/database.md` for full schema — tables for contacts, send log, and reply tracking.

## References

- `references/email-templates.md` — Full email copy for all 4 weeks
- `references/cadence.md` — 5-week cycle details and state machine
- `references/reply-handling.md` — Reply classification and lead routing spec
- `references/personalization.md` — AI personalization pipeline (optional enhancement)
- `references/database.md` — SQL schema and status values
- `assets/signature.html` — Gabby's HTML email signature
