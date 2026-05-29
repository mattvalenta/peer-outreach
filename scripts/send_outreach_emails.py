"""
Peer Outreach — Email Sending Engine (Gmail SMTP)

Queries contacts due for outreach, fills the appropriate week's template,
sends via Gmail SMTP, logs everything.

Usage:
  python3 send_outreach_emails.py --dry-run     # Preview without sending
  python3 send_outreach_emails.py               # Send for real
  python3 send_outreach_emails.py --limit 10    # Send only 10
"""

import os
import sys
import time
import random
import argparse
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────
DB_URL = os.environ.get("DATABASE_URL", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = "gabby@trafficdriver.ai"
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", os.environ.get("IMAP_PASSWORD", ""))

FROM_EMAIL = "gabby@trafficdriver.ai"
FROM_NAME = "Gabby Pals"

DAILY_LIMIT = 100
MIN_DELAY_SEC = 120  # 2 min
MAX_DELAY_SEC = 300  # 5 min

# ── Signature ───────────────────────────────────────────
SIGNATURE_HTML = """<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
  <strong style="color: #1a1a1a;">Gabby Pals</strong><br>
  <span style="color: #666666;">Solutions Consultant</span><br><br>
  <a href="https://paramountals.com/" style="color: #2b6cb0; text-decoration: underline;">Paramount Lead Solutions</a><br>
  <a href="https://trafficdriver.ai/" style="color: #2b6cb0; text-decoration: underline;">TrafficDriver.ai</a><br><br>
  <a href="tel:8006435084" style="color: #2b6cb0; text-decoration: none;">800-643-5084</a>
</div>"""

SIGNATURE_PLAIN = """Gabby Pals
Solutions Consultant
Paramount Lead Solutions — https://paramountals.com/
TrafficDriver.ai — https://trafficdriver.ai/
800-643-5084"""

# ── Email Templates ─────────────────────────────────────

EMAIL_TEMPLATES = {
    1: {
        "subjects": [
            "different kind of dealership support",
            "real people, real phones, real results",
            "not software — actual humans doing the work"
        ],
        "body": """Hi {first_name},

I know your inbox is full of software demos and marketing pitches. We're not one of those.

We're a team of real sales people who pick up the phones, convert your leads, follow up with customers, and take the calls your staff doesn't have time for. If AI makes sense for your budget we layer that in too. But either way, the work gets done.

Here's what we handle:

• Sales BDC — humans on your inbound leads (phone, text, email). We follow every lead for 90 days, cradle to grave.
• Service BDC — people taking your service calls, upselling appointments, running outbound retention campaigns
• Equity Mining — a team calling your previous customers and showing them why now's the time to buy
• AI Virtual Receptionist — AI answering inbound sales and service calls around the clock
• AI Internet Lead Follow-Up — AI on internet lead outreach and follow-up (text, email, phone)

Everything's a la carte. You pick what you need. Everyone works out of our Chicagoland office — not remote, not overseas.

Worth a conversation?"""
    },
    2: {
        "subjects": [
            "quick follow up",
            "following up"
        ],
        "body": """Hi {first_name},

Following up on my email from last week. 90% of dealerships have at least one gap in their lead process. Most fill those gaps with us instead of expanding their internal teams.

Here's one we see a lot: a dealer paying $4,000+ a month for equity mining software, but nobody's actually calling the customers. They cancel the software, use that budget for real people doing real equity mining work, and the ROI flips fast.

If any of this sounds familiar, let me know."""
    },
    3: {
        "subjects": [
            "spread thin?",
            "quick thought"
        ],
        "body": """Hi {first_name},

Some of the dealerships we work with aren't missing a piece of the puzzle. They're just spread thin. Their team handles everything, but everything's a little backed up.

That's where our BDC support packages come in. We work behind your existing team, helping convert older internet leads, running service-to-sales equity mining, and taking the overflow calls your people can't get to. Nothing replaces your crew. We just take the weight off so they can breathe.

If that sounds like your store, happy to talk through it."""
    },
    4: {
        "subjects": [
            "last one from me",
            "dealers crushing it"
        ],
        "body": """Hi {first_name},

I'll keep this short since I've sent a few now. Just wanted to share that we've got dealers running with us who are now #1 in their region. Multiple stores. Not because they bought more software — because they finally had actual people working their leads.

Happy to connect you with a couple of them if you want to hear it from someone who's been in your shoes. If not, no worries at all."""
    }
}


def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def get_contacts(limit=DAILY_LIMIT):
    """Get contacts due for outreach today, ordered by longest-waiting first.
    Includes dedup: skips contacts sent to in the last 5 minutes (SMTP sent but DB crashed)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, first_name, last_name, email, role, dealership_name,
               dealership_brand, dealership_city, dealership_state,
               outreach_week, cycle_count, last_sent_at
        FROM peer_outreach_contacts
        WHERE status = 'active'
          AND outreach_week IN (1, 2, 3, 4)
          AND (
            last_sent_at IS NULL
            OR last_sent_at < NOW() - INTERVAL '7 days'
          )
          AND id NOT IN (
            SELECT contact_id FROM peer_outreach_log
            WHERE created_at > NOW() - INTERVAL '10 minutes'
          )
        ORDER BY last_sent_at ASC NULLS FIRST
        LIMIT %s
    """, (limit,))
    contacts = cur.fetchall()
    cur.close()
    conn.close()
    return contacts


def compose_email(contact):
    """Fill template for the contact's current week. Returns (subject, plain_body, html_body)."""
    week = contact["outreach_week"]
    template = EMAIL_TEMPLATES[week]

    subject = random.choice(template["subjects"])
    body = template["body"].format(first_name=contact["first_name"] or "there")

    full_plain = body + "\n\n" + SIGNATURE_PLAIN
    full_html = "<pre style='white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#333;margin:0;'>" + body + "</pre><br>" + SIGNATURE_HTML

    return subject, full_plain, full_html


def send_email(contact, dry_run=False):
    """Send one email via Gmail SMTP. Returns (msg_id, subject) or (None, subject)."""
    subject, plain_body, html_body = compose_email(contact)
    to_email = contact["email"]

    if dry_run:
        print(f"  [DRY RUN] To: {to_email} | Subject: {subject}")
        return f"dry-run-{contact['id']}-{int(time.time())}", subject

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Message-ID"] = f"peer-outreach-{contact['id']}-{int(time.time())}@trafficdriver.ai"

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return msg["Message-ID"], subject
    except Exception as e:
        print(f"  SMTP error for {to_email}: {e}")
        return None, subject


def update_contact(conn, contact, msg_id, subject, plain_body):
    """Mark contact as sent and advance week."""
    new_week = contact["outreach_week"] + 1
    new_cycle = contact["cycle_count"]
    if new_week > 5:
        new_week = 1
        new_cycle += 1

    cur = conn.cursor()
    cur.execute("""
        UPDATE peer_outreach_contacts
        SET outreach_week = %s,
            cycle_count = %s,
            last_sent_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """, (new_week, new_cycle, contact["id"]))

    # Log the send (including body for future reply context)
    cur.execute("""
        INSERT INTO peer_outreach_log (contact_id, email_sent_to, week, subject, sendgrid_message_id, body_text, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'sent')
    """, (contact["id"], contact["email"], contact["outreach_week"],
          subject, msg_id, plain_body))

    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Send peer outreach emails via Gmail SMTP")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--limit", type=int, default=DAILY_LIMIT, help="Max emails to send")
    args = parser.parse_args()

    contacts = get_contacts(args.limit)
    print(f"Contacts due: {len(contacts)}")

    if not contacts:
        print("No contacts due today.")
        return

    sent = 0
    conn = get_db()

    for i, contact in enumerate(contacts):
        first = contact["first_name"] or contact["email"]
        week = contact["outreach_week"]
        print(f"\nSending week {week} email to {first} ({contact['email']})")

        msg_id, subject = send_email(contact, dry_run=args.dry_run)
        if msg_id:
            _, plain_body, _ = compose_email(contact)
            update_contact(conn, contact, msg_id, subject, plain_body)
            conn.commit()
            sent += 1
            print(f"  ✓ Sent: \"{subject}\" | ID: {msg_id}")
        else:
            print(f"  ✗ Failed to send")

        # Random delay between sends (skip on last one)
        remaining = len(contacts) - i - 1
        if remaining > 0:
            delay = random.randint(MIN_DELAY_SEC, MAX_DELAY_SEC)
            if args.dry_run:
                delay = 1
            print(f"  Waiting {delay}s...")
            time.sleep(delay)

    conn.close()
    print(f"\nDone. {sent}/{len(contacts)} emails sent.")


if __name__ == "__main__":
    main()
