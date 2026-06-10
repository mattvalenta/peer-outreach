"""
Peer Outreach — Follow-Up Email Sender (auto@paramountals.net)

Resends the SAME weekly email from a second address to contacts that didn't
bounce from Gabby's primary send. Same sender name (Gabby Pals), same
templates, different email address. Gabby's address cleans the list; this
address hits the clean contacts.

Flow:
  1. Gabby sends weekly email from gabby@trafficdriver.ai (send_outreach_emails.py)
  2. 2 days later, this script resends the same week's email from auto@paramountals.net
  3. Only sends to contacts where Gabby's email didn't bounce

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
FROM_NAME = "Gabby Pals"

DAILY_LIMIT = 100
DEFAULT_DELAY_DAYS = 2
MIN_DELAY_SEC = 120  # 2 min
MAX_DELAY_SEC = 300  # 5 min

# ── Signature (same as Gabby's primary send) ────────────
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

# ── Email Templates (same as send_outreach_emails.py) ───

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


def get_contacts(delay_days=DEFAULT_DELAY_DAYS, limit=DAILY_LIMIT):
    """
    Get contacts due for a follow-up resend.

    Criteria:
    - Gabby sent them an email (exists in peer_outreach_log)
    - It's been >= delay_days since Gabby's send
    - No follow-up has been sent for that specific Gabby send yet
      (followup_sent_at IS NULL or followup_sent_at < Gabby's last send)
    - Contact is still active (not suppressed, not in conversation)
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
    """Fill the same template matching Gabby's send week."""
    gabby_week = contact["gabby_week"]
    template = EMAIL_TEMPLATES.get(gabby_week)
    if not template:
        print(f"  WARNING: No template for week {gabby_week}")
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
        print(f"  BOUNCE (invalid address) for {to_email}: {e}")
        return None, subject
    except Exception as e:
        print(f"  SMTP error for {to_email}: {e}")
        return None, subject


def update_contact(conn, contact, msg_id, subject, plain_body, gabby_week):
    """Log the follow-up send and update followup_sent_at."""
    cur = conn.cursor()

    cur.execute("""
        UPDATE peer_outreach_contacts
        SET followup_sent_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """, (contact["id"],))

    cur.execute("""
        INSERT INTO peer_outreach_log
            (contact_id, email_sent_to, week, subject, sendgrid_message_id, body_text, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'sent')
    """, (contact["id"], contact["email"], gabby_week,
          subject, msg_id, plain_body))

    cur.close()


def main():
    parser = argparse.ArgumentParser(
        description="Resend weekly emails from auto@paramountals.net to non-bounced contacts"
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
    print(f"Contacts due for follow-up resend: {len(contacts)}")

    if not contacts:
        print("No contacts due for follow-up today.")
        return

    sent = 0
    conn = get_db()

    for i, contact in enumerate(contacts):
        first = contact["first_name"] or contact["email"]
        gabby_week = contact["gabby_week"]
        gabby_sent = contact["gabby_sent_at"].strftime("%Y-%m-%d") if contact["gabby_sent_at"] else "?"
        print(f"\n[{i+1}/{len(contacts)}] Week {gabby_week} resend (original sent {gabby_sent})")
        print(f"  To: {first} ({contact['email']})")

        msg_id, subject = send_email(contact, dry_run=args.dry_run)
        if msg_id:
            _, plain_body, _ = compose_email(contact)
            update_contact(conn, contact, msg_id, subject, plain_body, gabby_week)
            conn.commit()
            sent += 1
            print(f"  ✓ Sent: \"{subject}\" | ID: {msg_id}")

        # Random delay between sends
        remaining = len(contacts) - i - 1
        if remaining > 0:
            delay = random.randint(MIN_DELAY_SEC, MAX_DELAY_SEC)
            if args.dry_run:
                delay = 1
            print(f"  Waiting {delay}s...")
            time.sleep(delay)

    conn.close()
    print(f"\nDone. {sent}/{len(contacts)} follow-up resends.")


if __name__ == "__main__":
    main()
