---
name: peer-outreach
description: "Manages the peer-to-peer plain-text email outreach system for TrafficDriver.ai. Dual-sender: Gabby sends weekly emails from gabby@trafficdriver.ai, then resends the same emails 2 days later from auto@paramountals.net to contacts that didn't bounce. Same sender name, same templates, different address to protect deliverability. 5-week cadence (4 weekly + 1 cooldown). Use when Matt asks to run, build, or modify the peer outreach system, send outreach emails, or handle replies."
---

# Peer-to-Peer Outreach System

Dual-address plain-text email outreach to dealership GMs. Gabby sends weekly emails from her primary address, then resends the same email from a second address 2 days later to contacts that didn't bounce. The primary address cleans the list; the second address hits the clean contacts.

## Hosting & Source of Truth

- **GitHub:** https://github.com/mattvalenta/peer-outreach
- **Hosting:** GCP (managed by dev manager)
- **Source of truth:** GitHub repo — clone/pull to operate, don't edit local copies

## Senders

| Address | Sender Name | Role | SMTP |
|---------|-------------|------|------|
| gabby@trafficdriver.ai | Gabby Pals | Primary send (week 0) | Gmail SMTP |
| auto@paramountals.net | Gabby Pals | Follow-up resend (week +2 days) | Gmail SMTP |

Both emails show **Gabby Pals** as the sender. Same signature, same templates. The recipient sees the same person — only the email address changes.

## Quick Reference

| Detail | Value |
|--------|-------|
| Gabby primary sends/day | 100 |
| Follow-up resends/day | 100 (contacts that received Gabby's email 2+ days ago, no bounce) |
| Cadence | 4 weeks on, 1 week cooldown |
| Follow-up delay | 2 days after primary send (configurable via `--delay-days`) |
| Target | GMs only (valid emails, not suppressed) |
| Format | Plain text body + HTML signature |
| Reply routing | Intent → `growth@paramountals.com` lead notification |

## Daily Workflow

### Step 1: Gabby sends primary emails
```bash
python3 scripts/send_outreach_emails.py            # Send for real
python3 scripts/send_outreach_emails.py --dry-run   # Preview
python3 scripts/send_outreach_emails.py --limit 10  # Cap at 10
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `SMTP_PASSWORD`

### Step 2: Gabby resends from second address (run daily, 2+ days after Step 1)
```bash
python3 scripts/send_followup_emails.py              # Send for real
python3 scripts/send_followup_emails.py --dry-run    # Preview
python3 scripts/send_followup_emails.py --delay-days 3  # Wait 3 days instead of 2
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `FOLLOWUP_SMTP_PASSWORD`

### Step 3: Process replies (replies come to gabby@trafficdriver.ai inbox)
```bash
python3 scripts/process_replies.py              # Process unread replies
python3 scripts/process_replies.py --dry-run    # Preview only
python3 scripts/process_replies.py --mark-read  # Mark as read after processing
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `SMTP_PASSWORD`, `IMAP_PASSWORD`

## 5-Week Cadence

| Week | Primary Send (Day 0) | Follow-Up Resend (Day 2) |
|------|---------------------|--------------------------|
| 1 | Intro + services list | Same email, different address |
| 2 | Equity mining angle | Same email, different address |
| 3 | Spread thin / BDC support | Same email, different address |
| 4 | Testimonial / referral | Same email, different address |
| 5 | Cooldown — no emails | No resends either |

Full templates: `references/email-templates.md`
Full cadence: `references/cadence.md`

## How Follow-Up Resends Work

1. Gabby sends weekly email from `gabby@trafficdriver.ai` → `last_sent_at` updated
2. Script queries contacts where Gabby sent 2+ days ago, no bounce, no resend yet
3. Same email (same template, same subject, same signature) sent from `auto@paramountals.net`
4. `followup_sent_at` updated on contact, logged to `peer_outreach_log`
5. If Gabby's email bounced (detected via reply classification), contact is suppressed → resend skipped

## Database Migration

When deploying for the first time with follow-up support:
```bash
python3 scripts/add_followup_column.py              # Apply migration
python3 scripts/add_followup_column.py --dry-run    # Preview only
```
Adds `followup_sent_at TIMESTAMP` column + index to `peer_outreach_contacts`.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SALES_CRM_DB_URL` | PostgreSQL connection for `sales_crm` |
| `CLIENTS_DB_URL` | PostgreSQL connection for `clients` |
| `DATABASE_URL` | Fallback if `SALES_CRM_DB_URL` not set |
| `SMTP_PASSWORD` | Gmail app password for `gabby@trafficdriver.ai` |
| `IMAP_PASSWORD` | Gmail app password for `gabby@trafficdriver.ai` |
| `FOLLOWUP_SMTP_PASSWORD` | Gmail app password for `auto@paramountals.net` |

## Setup (on a fresh checkout)

```bash
git clone https://github.com/mattvalenta/peer-outreach.git
cd peer-outreach
pip install -r requirements.txt
cp .env.example .env
# Edit .env with database URLs and Gmail credentials
# Run migration: python3 scripts/add_followup_column.py
```

See `references/database.md` for full schema.
