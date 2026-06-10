"""
Peer Outreach — Follow-Up Email Sender (auto@paramountals.net)

Sends follow-up emails from a secondary sender to contacts that received
Gabby's email without bouncing. Complements Gabby's weekly emails with
different content from a different sender on a different domain.

Flow:
  1. Gabby sends weekly email (send_outreach_emails.py)
  2. 2 days later, this script sends a follow-up to non-bounced contacts
  3. Both use the same cadence (week 1-4), but different templates

Usage:
  python3 send_followup_emails.py --dry-run     # Preview without sending
  python3 send_followup_emails.py               # Send for real
  python3 send_followup_emails.py --limit 10    # Send only 10
  python3 send_followup_emails.py --delay-days 3  # Wait 3 days instead of 2
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

# ── Config ──────────────────────────────────────────────
DB_URL = os.environ.get("SALES_CRM_DB_URL", os.environ.get("DATABASE_URL", ""))

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = os.environ.get("FOLLOWUP_SMTP_EMAIL", "auto@paramountals.net")
SMTP_PASSWORD = os.environ.get("FOLLOWUP_SMTP_PASSWORD", "")

FROM_EMAIL = SMTP_EMAIL
FROM_NAME = "Alex Martin"

DAILY_LIMIT = 100
DEFAULT_DELAY_DAYS = 2
MIN_DELAY_SEC = 120  # 2 min
MAX_DELAY_SEC = 300  # 5 min

# ── Signature ───────────────────────────────────────────
SIGNATURE_HTML = """<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
  <strong style="color: #1a1a1a;">Alex Martin</strong><br>
  <span style="color: #666666;">Solutions Consultant</span><br><br>
  <a href="https://paramountals.com/" style="color: #2b6cb0; text-decoration: underline;">Paramount Lead Solutions</a><br><br>
  <a href="tel:8006435084" style="color: #2b6cb0; text-decoration: none;">800-643-5084</a>
</div>"""

SIGNATURE_PLAIN = """Alex Martin
Solutions Consultant
Paramount Lead Solutions — https://paramountals.com/
800-643-5084"""

# ── Follow-Up Templates (mapped to Gabby's send week) ──

FOLLOWUP_TEMPLATES = {
    1: {
        "subjects": [
            "quick question about your leads",
            "your internet leads — who's following up?"
        ],
        "body": """Hi {first_name},

Quick question — when an internet lead comes in after hours, who's following up? Most dealers tell us it sits until morning. By then the customer's already talking to someone else.

We have a team that picks up those leads around the clock. Real people, not a bot. They respond within minutes, not hours.

Worth a 5 minute call?"""
    },
    2: {
        "subjects": [
            "sitting on a goldmine",
            "your past customers are buying — just not from you"
        ],
        "body": """Hi {first_name},

Your service lane sees customers every day who are in equity positions. They're driving cars worth more than they owe. Most dealers know this but don't have the people to call them.

We do. Our team runs equity mining campaigns to your service customers and sold leads. We make the calls, set the appointments, and your sales team closes.

Want to see what that looks like?"""
    },
    3: {
        "subjects": [
            "what if your team had backup?",
            "your BDC doesn't have to do everything"
        ],
        "body": """Hi {first_name},

A lot of BDC teams we talk to are running lean. They're handling inbound, outbound, service, and internet leads — all at once. Something always falls through the cracks.

We plug in behind your existing team and catch what they can't. No replacing anyone. Just extra hands on the keyboard and phones so nothing gets missed.

If that sounds familiar, let's chat."""
    },
    4: {
        "subjects": [
            "what 90 days looks like",
            "dealers we work with — real numbers"
        ],
        "body": """Hi {first_name},

One of our dealers went from 30% lead follow-up to 95% in their first month. Not because they hired more people — because they added our team behind the scenes.

Same store, same leads, same budget. Just more hands doing the work.

If you want to see the before and after, happy to walk you through it."""
    }
}


def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def get_contacts(delay_days=DEFAULT_DELAY_DAYS, limit=DAILY_LIMIT):
    """
    Get contacts due for a follow-up email.

    Criteria:
    - Gabby sent them an email (exists in peer_outreach_log)
    - It's been >= delay_days since Gabby's send
    - No follow-up has been sent for that specific Gabby send yet
      (followup_sent_at IS NULL or followup_sent_at < Gabby's last send)
    - Contact is still active (not suppressed, not in conversation)
    - Not suppressed due to bounce
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            poc.id,
            poc.first_name,
            poc.last_name,
            poc.email,
            poc.role,
            poc.dealership_name,
            poc.dealership_brand,
            poc.dealership_city,
            poc.dealership_state,
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
          AND pol.created_at <= NOW() - INTERVAL '%s days'
          AND (
            poc.followup_sent_at IS NULL
            OR poc.followup_sent_at < pol.created_at
          )
        ORDER BY pol.created_at ASC
        LIMIT %s
    """, (delay_days, limit))

    contacts = cur.fetchall()
    cur.close()
    conn.close()
    return contacts


def compose_email(contact):
    """Fill the follow-up template matching Gabby's send week."""
    gabby_week = contact["gabby_week"]
    template = FOLLOWUP_TEMPLATES.get(gabby_week)
    if not template:
        print(f"  WARNING: No follow-up template for week {gabby_week}")
        return None, None, None

    subject = random.choice(template["subjects"])
    body = template["body"].format(first_name=contact["first_name"] or "there")

    full_plain = body + "\n\n" + SIGNATURE_PLAIN
    full_html = (
        "<pre style='white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;"
        "font-size:14px;color:#333;margin:0;'>" + body + "</pre><br>" + SIGNATURE_HTML
    )

    return subject, full_plain, full_html


def send_email(contact, dry_run=False):
    """Send one follow-up email via SMTP. Returns (msg_id, subject) or (None, subject)."""
    subject, plain_body, html_body = compose_email(contact)
    if subject is None:
        return None, "skipped"

    to_email = contact["email"]

    if dry_run:
        print(f"  [DRY RUN] To: {to_email} | Subject: {subject}")
        return f"dry-run-followup-{contact['id']}-{int(time.time())}", subject

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Message-ID"] = f"peer-followup-{contact['id']}-{int(time.time())}@paramountals.net"

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return msg["Message-ID"], subject
    except smtplib.SMTPRecipientsRefused as e:
        # Hard bounce — contact is invalid
        print(f"  BOUNCE (invalid address) for {to_email}: {e}")
        return None, subject
    except Exception as e:
        print(f"  SMTP error for {to_email}: {e}")
        return None, subject


def update_contact(conn, contact, msg_id, subject, plain_body, gabby_week):
    """Log the follow-up send and update followup_sent_at."""
    cur = conn.cursor()

    # Update followup_sent_at on the contact
    cur.execute("""
        UPDATE peer_outreach_contacts
        SET followup_sent_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """, (contact["id"],))

    # Log in peer_outreach_log with week matching Gabby's send
    # (so we have a record of what was sent and when)
    cur.execute("""
        INSERT INTO peer_outreach_log
            (contact_id, email_sent_to, week, subject, sendgrid_message_id, body_text, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'sent')
    """, (contact["id"], contact["email"], gabby_week,
          f"[Follow-up] {subject}", msg_id, plain_body))

    cur.close()


def mark_bounced(conn, contact):
    """Suppress a contact that hard-bounced on the follow-up send."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE peer_outreach_contacts
        SET status = 'suppressed',
            reply_intent = 'bounce',
            updated_at = NOW()
        WHERE id = %s
    """, (contact["id"],))
    cur.close()


def main():
    parser = argparse.ArgumentParser(
        description="Send follow-up emails via auto@paramountals.net"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--limit", type=int, default=DAILY_LIMIT, help="Max emails to send")
    parser.add_argument(
        "--delay-days", type=int, default=DEFAULT_DELAY_DAYS,
        help=f"Days to wait after Gabby's send (default: {DEFAULT_DELAY_DAYS})"
    )
    args = parser.parse_args()

    if not DB_URL:
        print("ERROR: Set SALES_CRM_DB_URL or DATABASE_URL environment variable.")
        sys.exit(1)

    if not SMTP_PASSWORD and not args.dry_run:
        print("ERROR: Set FOLLOWUP_SMTP_PASSWORD environment variable.")
        sys.exit(1)

    contacts = get_contacts(delay_days=args.delay_days, limit=args.limit)
    print(f"Contacts due for follow-up: {len(contacts)}")

    if not contacts:
        print("No contacts due for follow-up today.")
        return

    sent = 0
    bounced = 0
    conn = get_db()

    for i, contact in enumerate(contacts):
        first = contact["first_name"] or contact["email"]
        gabby_week = contact["gabby_week"]
        gabby_sent = contact["gabby_sent_at"].strftime("%Y-%m-%d") if contact["gabby_sent_at"] else "?"
        print(f"\n[{i+1}/{len(contacts)}] Follow-up for week {gabby_week} (Gabby sent {gabby_sent})")
        print(f"  To: {first} ({contact['email']})")

        msg_id, subject = send_email(contact, dry_run=args.dry_run)
        if msg_id:
            _, plain_body, _ = compose_email(contact)
            update_contact(conn, contact, msg_id, subject, plain_body, gabby_week)
            conn.commit()
            sent += 1
            print(f"  ✓ Sent: \"{subject}\" | ID: {msg_id}")
        elif subject != "skipped":
            # Check if it was a bounce (SMTPRecipientsRefused)
            print(f"  ✗ Failed — checking if bounce...")
            # We can't easily distinguish bounce vs temp failure here
            # The bounce is already printed in send_email
            conn.commit()

        # Random delay between sends
        remaining = len(contacts) - i - 1
        if remaining > 0:
            delay = random.randint(MIN_DELAY_SEC, MAX_DELAY_SEC)
            if args.dry_run:
                delay = 1
            print(f"  Waiting {delay}s...")
            time.sleep(delay)

    conn.close()
    print(f"\nDone. {sent}/{len(contacts)} follow-ups sent. {bounced} bounced.")


if __name__ == "__main__":
    main()
