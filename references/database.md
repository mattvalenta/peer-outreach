# Database Schema — Peer Outreach

## New Fields on `prospect_dealership_contacts`

```sql
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_status VARCHAR(20) DEFAULT 'active';
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_week INTEGER DEFAULT 1;
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_last_sent TIMESTAMP;
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_cycle_count INTEGER DEFAULT 0;
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_reply_intent VARCHAR(20);
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_last_reply_at TIMESTAMP;
ALTER TABLE prospect_dealership_contacts ADD COLUMN peer_outreach_template_variant INTEGER;
```

## New Table: `peer_outreach_log`

```sql
CREATE TABLE peer_outreach_log (
  id SERIAL PRIMARY KEY,
  contact_id INTEGER REFERENCES prospect_dealership_contacts(id),
  email_sent_to VARCHAR(255),
  week INTEGER NOT NULL,
  template_variant INTEGER,
  sendgrid_message_id VARCHAR(255),
  status VARCHAR(20) DEFAULT 'sent',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_peer_outreach_log_contact ON peer_outreach_log(contact_id);
CREATE INDEX idx_peer_outreach_log_created ON peer_outreach_log(created_at);
```

## New Table: `peer_outreach_replies`

```sql
CREATE TABLE peer_outreach_replies (
  id SERIAL PRIMARY KEY,
  contact_id INTEGER REFERENCES prospect_dealership_contacts(id),
  from_email VARCHAR(255),
  subject VARCHAR(500),
  body_text TEXT,
  body_html TEXT,
  intent VARCHAR(20),
  action_taken VARCHAR(50),
  lead_notification_sent BOOLEAN DEFAULT FALSE,
  auto_reply_sent BOOLEAN DEFAULT FALSE,
  raw_payload JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
```

## Daily Send Query

```sql
SELECT c.*, d.name AS dealership_name
FROM prospect_dealership_contacts c
JOIN prospect_dealerships d ON c.prospect_dealership_id = d.id
LEFT JOIN email_validations ev ON ev.email = c.email
WHERE c.peer_outreach_status = 'active'
  AND c.peer_outreach_week IN (1, 2, 3, 4)
  AND (
    c.peer_outreach_last_sent IS NULL
    OR c.peer_outreach_last_sent < NOW() - INTERVAL '7 days'
  )
  AND c.email IS NOT NULL
  AND c.email != ''
  AND c.role ILIKE '%general manager%'
  AND (ev.is_valid IS NULL OR ev.is_valid = TRUE)
  AND (ev.is_unsubscribed IS NULL OR ev.is_unsubscribed = FALSE)
  AND c.is_unsubscribed IS NOT TRUE
ORDER BY c.peer_outreach_last_sent ASC NULLS FIRST
LIMIT 100;
```

## Status Values Reference

| Field | Values | Description |
|-------|--------|-------------|
| `peer_outreach_status` | `active` | In rotation, receiving emails |
| | `conversation` | Reply received, in human conversation |
| | `suppressed` | Unsubscribed, bounced, or not interested |
| | `cooldown` | In week 5 cooldown |
| `peer_outreach_week` | `1-4` | Active sending weeks |
| | `5` | Cooldown week |
| `peer_outreach_reply_intent` | `pending` | Not yet classified |
| | `positive` | Interested — lead created |
| | `negative` | Not interested — suppress |
| | `ooo` | Out of office — retry |
| | `bounce` | Invalid — suppress |
