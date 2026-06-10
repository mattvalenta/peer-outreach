# Database Schema — Peer Outreach

Two separate PostgreSQL databases. Contacts live in `clients`, activity tracking lives in `sales_crm`.

---

## clients DB (Contact Source)

### `sales_companies`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| company_name | text | Dealership name |
| city | text | |
| state | text | |
| website | text | |
| industry | text | |

### `sales_contacts`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| company_id | uuid | FK → sales_companies |
| first_name | text | |
| last_name | text | |
| title | text | Job title (e.g. "General Manager") |
| email_1 | text | Primary email |
| contact_phone_1 | text | Primary phone |
| title_category | varchar(50) | Pre-categorized (General Manager, Sales Manager, etc.) |

---

## sales_crm DB (Activity Tracking)

### `peer_outreach_contacts`

Local copy of contacts being actively targeted. Seeded from clients DB.

```sql
CREATE TABLE peer_outreach_contacts (
    id SERIAL PRIMARY KEY,
    source_contact_id VARCHAR(36),       -- original sales_contacts.id
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    email VARCHAR(255) NOT NULL,
    role VARCHAR(255),
    dealership_name VARCHAR(255),
    dealership_city VARCHAR(255),
    dealership_state VARCHAR(255),
    phone VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    outreach_week INTEGER DEFAULT 1,
    cycle_count INTEGER DEFAULT 0,
    last_sent_at TIMESTAMP,
    followup_sent_at TIMESTAMP,        -- last follow-up email sent at (auto@paramountals.net)
    last_reply_at TIMESTAMP,
    reply_intent VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_contact_id, email)
);
```

### `peer_outreach_log`

Every email sent. Includes body text for reply context matching.

```sql
CREATE TABLE peer_outreach_log (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES peer_outreach_contacts(id),
    email_sent_to VARCHAR(255),
    week INTEGER NOT NULL,
    subject VARCHAR(500),
    sendgrid_message_id VARCHAR(255),
    body_text TEXT,
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMP DEFAULT NOW()
);
```

### `peer_outreach_replies`

Every reply received, with classification and action taken.

```sql
CREATE TABLE peer_outreach_replies (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES peer_outreach_contacts(id),
    from_email VARCHAR(255),
    subject VARCHAR(500),
    body_text TEXT,
    intent VARCHAR(20),
    lead_notification_sent BOOLEAN DEFAULT FALSE,
    auto_reply_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Daily Send Query

```sql
SELECT id, first_name, last_name, email, role, dealership_name,
       outreach_week, cycle_count, last_sent_at
FROM peer_outreach_contacts
WHERE status = 'active'
  AND outreach_week IN (1, 2, 3, 4)
  AND (
    last_sent_at IS NULL
    OR last_sent_at < NOW() - INTERVAL '7 days'
  )
ORDER BY last_sent_at ASC NULLS FIRST
LIMIT 100;
```

## Follow-Up Send Query (auto@paramountals.net)

Contacts that received Gabby's email 2+ days ago, haven't bounced, and haven't
received a follow-up for that specific Gabby send yet.

```sql
SELECT
    poc.id, poc.first_name, poc.last_name, poc.email,
    poc.followup_sent_at,
    pol.week AS gabby_week,
    pol.created_at AS gabby_sent_at
FROM peer_outreach_contacts poc
INNER JOIN (
    SELECT contact_id, week, created_at,
           ROW_NUMBER() OVER (PARTITION BY contact_id ORDER BY created_at DESC) AS rn
    FROM peer_outreach_log
) pol ON pol.contact_id = poc.id AND pol.rn = 1
WHERE poc.status = 'active'
  AND poc.reply_intent IS NULL
  AND pol.created_at <= NOW() - INTERVAL '2 days'
  AND (
    poc.followup_sent_at IS NULL
    OR poc.followup_sent_at < pol.created_at
  )
ORDER BY pol.created_at ASC
LIMIT 100;
```

## Senders

| Sender | Email | Purpose | SMTP |
|--------|-------|---------|------|
| Gabby Pals | gabby@trafficdriver.ai | Primary weekly emails (weeks 1-4) | Gmail SMTP |
| Alex Martin | auto@paramountals.net | Follow-up emails (2 days after Gabby) | Gmail SMTP |

Both log to `peer_outreach_log`. Follow-ups are prefixed with `[Follow-up]` in the subject column.

## Seed Query (from clients DB)

```sql
SELECT c.id::text, c.first_name, c.last_name,
       COALESCE(NULLIF(c.email_1, ''), NULLIF(c.email_2, ''), NULLIF(c.personal_email, '')) AS email,
       c.title, co.company_name, co.city, co.state, c.contact_phone_1
FROM sales_contacts c
JOIN sales_companies co ON c.company_id = co.id
WHERE c.title_category IN ('General Manager', 'Owner')
  AND (NULLIF(c.email_1, '') IS NOT NULL
    OR NULLIF(c.email_2, '') IS NOT NULL
    OR NULLIF(c.personal_email, '') IS NOT NULL);
```

## Status Values

| Field | Values | Description |
|-------|--------|-------------|
| `status` | `active` | In rotation, receiving emails |
| | `conversation` | Reply received, in human conversation |
| | `suppressed` | Unsubscribed, bounced, or not interested |
| | `cooldown` | In week 5 cooldown |
| `outreach_week` | `1-4` | Active sending weeks |
| | `5` | Cooldown week |
| `reply_intent` | `positive` | Interested — lead created |
| | `negative` | Not interested — suppress |
| | `ooo` | Out of office — retry |
| | `bounce` | Invalid — suppress |
| | `unclear` | Ambiguous — treated as positive |
