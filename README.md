# Peer Outreach System

Plain-text, 1:1 conversational email outreach from Gabby Pals to dealership General Managers. 100 emails/day via Gmail SMTP, cycling through contacts on a 5-week cadence (4 weekly emails + 1 cooldown).

## How It Works

1. **Seed contacts** from the clients DB (`sales_contacts` + `sales_companies`) into `peer_outreach_contacts` in sales_crm DB
2. **Send emails** — queries contacts due today, fills templates, sends via Gmail SMTP
3. **Process replies** — polls Gabby's inbox, classifies intent, routes leads

### 5-Week Cadence

| Week | Subject | Action |
|------|---------|--------|
| 1 | real people, real phones, real results | Intro + service overview |
| 2 | quick follow up | Equity mining angle |
| 3 | spread thin? | BDC support / spread thin |
| 4 | last one from me | Social proof / final nudge |
| 5 | — | Cooldown — no emails |
| → | — | Restart at Week 1 |

### Reply Handling

| Intent | Action |
|--------|--------|
| positive | Lead notification to growth@paramountals.com + auto-reply from Gabby |
| negative | Mark suppressed, remove from rotation |
| ooo | Log, retry next cycle |
| bounce | Mark invalid, suppress |

## Database Architecture

Two separate PostgreSQL databases:

| Database | Purpose | Key Tables |
|----------|---------|------------|
| **clients** | Source of contacts (scraped dealership data) | `sales_companies`, `sales_contacts` |
| **sales_crm** | Peer outreach activity tracking | `peer_outreach_contacts`, `peer_outreach_log`, `peer_outreach_replies` |

## Scripts

| Script | Reads From | Writes To |
|--------|-----------|-----------|
| `scripts/seed_contacts.py` | clients DB | sales_crm DB |
| `scripts/send_outreach_emails.py` | sales_crm DB | sales_crm DB |
| `scripts/process_replies.py` | sales_crm DB | sales_crm DB |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database URLs and Gmail credentials

# Seed contacts from clients DB
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
| `SALES_CRM_DB_URL` | PostgreSQL connection for sales_crm (activity tracking) |
| `CLIENTS_DB_URL` | PostgreSQL connection for clients (contact source) |
| `DATABASE_URL` | Fallback if SALES_CRM_DB_URL not set |
| `SMTP_PASSWORD` | Gmail app password for gabby@trafficdriver.ai |
| `IMAP_PASSWORD` | Gmail app password for gabby@trafficdriver.ai (same as SMTP) |

## References

- `references/email-templates.md` — Full email copy for all 4 weeks
- `references/cadence.md` — 5-week cycle details and state machine
- `references/reply-handling.md` — Reply classification and lead routing spec
- `references/personalization.md` — AI personalization pipeline (optional enhancement)
- `references/database.md` — SQL schema and status values
- `assets/signature.html` — Gabby's HTML email signature
