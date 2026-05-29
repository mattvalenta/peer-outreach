# Reply Handling

## Reply Detection

SendGrid Inbound Parse webhook catches replies to gabby@trafficdriver.ai. The webhook delivers parsed email data as JSON to a configured endpoint.

Alternatively: periodic IMAP polling of gabby@trafficdriver.ai inbox.

## Reply Processing Flow

### 1. Match to Contact

Use `In-Reply-To` / `References` headers to match the reply to the original outbound email. Look up `peer_outreach_log` by `sendgrid_message_id` or subject threading. Identify the source contact in `prospect_dealership_contacts`.

### 2. Classify Intent

| Intent | Indicators | Action |
|--------|------------|--------|
| **positive** | "interested", "tell me more", "let's talk", "call me", meeting request, questions about the product, curiosity | Trigger lead notification + generate auto-reply |
| **negative** | "not interested", "stop", "unsubscribe", "remove", "don't contact", "no thanks" | Mark suppressed, no further emails |
| **ooo** | "out of office", "vacation", "leave", "away until", auto-reply pattern | Skip this cycle, resume next cycle |
| **bounce** | Hard bounce, mailbox full, address doesn't exist | Mark email invalid, suppress |
| **unclear** | Ambiguous reply, short answer, not clearly positive or negative | Default to positive (escalate for human review via lead notification) |

Use AI/LLM for classification. Feed the reply body + subject. Prompt: "Classify this reply as positive, negative, ooo, or bounce."

### 3. Positive Intent → Lead Notification

Send an email to `growth@paramountals.com` via SendGrid:

**Subject:** `[Peer Outreach] Lead: {first_name} {last_name} — {dealership}`

**Body template (HTML, internal use):**
```
Lead from peer outreach — {first_name} {last_name} replied with positive intent.

---
Contact Details:
Name: {first_name} {last_name}
Role: {role}
Dealership: {dealership}
Brand: {brand}
Email: {email}
Phone: {phone}
Location: {city}, {state}
---

Email Chain:
{full_email_chain}

---
Status: Awaiting follow-up
```

### 4. Positive Intent → Auto-Reply

Generate a conversational reply from Gabby acknowledging their interest and keeping the conversation going. Send via SendGrid.

Tone: Warm, human, excited to help. Suggests a next step (quick call, share more details, answer their specific question).

Example:
```
Subject: Re: {original_subject}

Hi {first_name},

{acknowledges_their_specific_interest_or_question}

{suggests_next_step_naturally}

Looking forward to it.

Gabby
```

### 5. Update Database

After processing:
- `peer_outreach_status` → `'conversation'` (positive) or `'suppressed'` (negative)
- `peer_outreach_reply_intent` → classification
- `peer_outreach_last_reply_at` → now
- Log full reply in `peer_outreach_replies` table

## Ongoing Conversation Threads

If a contact is in `conversation` status, they do NOT receive further automated outreach emails. All follow-up is manual from Gabby's inbox until the conversation is resolved.
