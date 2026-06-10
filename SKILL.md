---
name: peer-outreach
description: "Manages the peer-to-peer plain-text email outreach system for TrafficDriver.ai. Dual-sender: Gabby (gabby@trafficdriver.ai) sends weekly emails, then Alex (auto@paramountals.net) sends follow-ups 2 days later to non-bounced contacts. 5-week cadence (4 weekly + 1 cooldown). Use when Matt asks to run, build, or modify the peer outreach system, send outreach emails, or handle replies. Covers email generation, Gmail SMTP sending, reply classification, and lead routing to growth@paramountals.com."
---

# Peer-to-Peer Outreach System

Dual-sender plain-text email outreach to dealership GMs. Gabby sends the primary weekly emails; Alex sends follow-ups 2 days later to contacts that didn't bounce.

## Hosting & Source of Truth

- **GitHub:** https://github.com/mattvalenta/peer-outreach
- **Hosting:** GCP (managed by dev manager)
- **Source of truth:** GitHub repo — clone/pull to operate, don't edit local copies

## Senders

| Sender | Email | Role | SMTP |
|--------|-------|------|------|
| **Gabby Pals** | gabby@trafficdriver.ai | Primary weekly emails (weeks 1-4) | Gmail SMTP (port 465, SSL) |
| **Alex Martin** | auto@paramountals.net | Follow-up emails (2 days after Gabby) | Gmail SMTP (port 465, SSL) |

- Gabby's domain: `trafficdriver.ai`
- Alex's domain: `paramountals.net` (separate domain = separate reputation)
- Both log to `peer_outreach_log`. Follow-ups prefixed with `[Follow-up]` in subject column.
- **Signature:** Gabby uses `assets/signature.html`, Alex uses `assets/followup-signature.html`

## Quick Reference

| Detail | Value |
|--------|-------|
| Gabby sends/day | 100 |
| Follow-ups/day | 100 (contacts that received Gabby's email 2+ days ago, no bounce) |
| Cadence | 4 weeks on, 1 week cooldown |
| Follow-up delay | 2 days after Gabby's send (configurable via `--delay-days`) |
| Target | GMs only (valid emails, not suppressed) |
| Format | Plain text body + HTML signature |
| Reply routing | Intent → `growth@paramountals.com` lead notification |

## Daily Workflow

### Step 1: Gabby sends weekly emails
```bash
python3 scripts/send_outreach_emails.py            # Send for real
python3 scripts/send_outreach_emails.py --dry-run   # Preview
python3 scripts/send_outreach_emails.py --limit 10  # Cap at 10
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `SMTP_PASSWORD` (gabby's app password)

### Step 2: Alex sends follow-ups (run daily, after Gabby's sends have aged 2+ days)
```bash
python3 scripts/send_followup_emails.py              # Send for real
python3 scripts/send_followup_emails.py --dry-run    # Preview
python3 scripts/send_followup_emails.py --delay-days 3  # Wait 3 days instead of 2
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `FOLLOWUP_SMTP_PASSWORD` (auto@paramountals.net app password)

### Step 3: Process replies (from both senders — replies come to Gabby's inbox)
```bash
python3 scripts/process_replies.py              # Process unread replies
python3 scripts/process_replies.py --dry-run    # Preview only
python3 scripts/process_replies.py --mark-read  # Mark as read after processing
```
Requires: `SALES_CRM_DB_URL` (or `DATABASE_URL`), `SMTP_PASSWORD`, `IMAP_PASSWORD`

## 5-Week Cadence

| Week | Gabby Email | Alex Follow-Up |
|------|-------------|----------------|
| 1 | Intro + services list | "Quick question about your leads" (after-hours angle) |
| 2 | Equity mining angle | "Sitting on a goldmine" (service lane equity) |
| 3 | Spread thin / BDC support | "What if your team had backup?" (overflow support) |
| 4 | Testimonial / referral | "What 90 days looks like" (real numbers) |
| 5 | Cooldown — no emails | No follow-ups either |

Full cadence: `references/cadence.md`
Gabby templates: `references/email-templates.md`
Alex follow-up templates: `references/followup-templates.md`

## How Follow-Ups Work

1. Gabby sends weekly email → `last_sent_at` updated, `outreach_week` advances
2. Script queries contacts where Gabby sent 2+ days ago, no bounce, no follow-up yet
3. Alex sends a **different** email (different content, different sender, different domain)
4. `followup_sent_at` updated on contact, logged to `peer_outreach_log`
5. If Gabby's email bounced (detected via reply classification), contact is suppressed → Alex skips them

## Database Migration

When deploying for the first time with follow-up support:
```bash
python3 scripts/add_followup_column.py              # Apply migration
python3 scripts/add_followup_column.py --dry-run    # Preview only
```
Adds `followup_sent_at TIMESTAMP` column + index to `peer_outreach_contacts`.

## Environment Variables (set in GCP deployment)

| Variable | Description |
|----------|-------------|
| `SALES_CRM_DB_URL` | PostgreSQL connection for `sales_crm` |
| `CLIENTS_DB_URL` | PostgreSQL connection for `clients` |
| `DATABASE_URL` | Fallback if `SALES_CRM_DB_URL` not set |
| `SMTP_PASSWORD` | Gmail app password for `gabby@trafficdriver.ai` |
| `IMAP_PASSWORD` | Gmail app password for `gabby@trafficdriver.ai` (same as SMTP) |
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

## Database Fields Required

See `references/database.md` for full schema (`peer_outreach_*` tables in `sales_crm`).
