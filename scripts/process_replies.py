"""
Peer Outreach — Reply Handler (Gmail IMAP + SMTP)

Polls Gabby's Gmail inbox for new replies to outreach emails.
Classifies intent, sends lead notifications to growth@paramountals.com,
generates auto-replies for positive intent — all via Gmail SMTP.

Usage:
  python3 process_replies.py                    # Process unread replies
  python3 process_replies.py --dry-run          # Preview only
  python3 process_replies.py --mark-read        # Also mark as read after processing
"""

import os
import sys
import imaplib
import smtplib
import ssl
import email
import time
import argparse
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from email.header import decode_header

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta

# ── Config ──────────────────────────────────────────────
DB_URL = os.environ.get("SALES_CRM_DB_URL", os.environ.get("DATABASE_URL", ""))

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
IMAP_EMAIL = "gabby@trafficdriver.ai"
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = "gabby@trafficdriver.ai"
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

FROM_EMAIL = "gabby@trafficdriver.ai"
FROM_NAME = "Gabby Pals"
GROWTH_EMAIL = "growth@paramountals.com"

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


def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def decode_mime_header(value):
    """Decode a MIME-encoded header to a string."""
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def extract_email_address(from_field):
    """Extract bare email from a From: header like 'Name <email>' or just 'email'."""
    if not from_field:
        return ""
    name, addr = parseaddr(from_field)
    return addr.lower().strip()


def get_body_text(msg):
    """Extract plain text body from an email.message object."""
    if msg.is_multipart():
        # Prefer plain text, fall back to HTML
        html_body = None
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disp:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
            elif content_type == "text/html" and html_body is None:
                payload = part.get_payload(decode=True)
                if payload:
                    html_body = payload.decode("utf-8", errors="replace")
        if html_body:
            # Strip HTML tags for basic text
            clean = re.sub(r'<[^>]+>', ' ', html_body)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return clean
        return ""
    else:
        payload = msg.get_payload(decode=True)
        return payload.decode("utf-8", errors="replace") if payload else ""


def classify_intent(body_text, subject):
    """
    Classify reply intent. Returns: positive, negative, ooo, bounce, unclear.
    Uses keyword matching + basic heuristics.
    """
    text = f"{subject or ''} {body_text or ''}".lower()

    # Out of office patterns
    ooo_patterns = ["out of office", "out of the office", "vacation", "on leave",
                    "away from", "returning on", "auto-reply", "autoreply", "automatic reply",
                    "out of office reply", "ooo"]
    if any(p in text for p in ooo_patterns):
        return "ooo"

    # Negative patterns
    negative_patterns = ["not interested", "no thanks", "stop emailing", "unsubscribe",
                         "remove me", "don't contact", "do not contact", "take me off",
                         "not a good fit", "please stop", "stop sending",
                         "remove from your list", "spam"]
    if any(p in text for p in negative_patterns):
        return "negative"

    # Bounce indicators
    bounce_patterns = ["mailbox full", "address not found", "user unknown",
                       "mailbox unavailable", "does not exist", "mail delivery",
                       "delivery status notification", "undeliverable",
                       "failed permanently", "550", "551", "552", "553", "554"]
    if any(p in text for p in bounce_patterns):
        return "bounce"

    # Positive patterns
    positive_patterns = ["interested", "tell me more", "let's talk", "call me",
                         "give me a call", "set up a call", "schedule", "send more",
                         "would like to learn", "how does it work", "what's the cost",
                         "pricing", "demo", "trial", "yes", "sounds good",
                         "send over", "would love to", "let's connect",
                         "happy to", "open to", "available", "learn more",
                         "i'm interested", "set something up", "how much",
                         "what do you charge", "send info", "send me info",
                         "would like more", "more information"]
    if any(p in text for p in positive_patterns):
        return "positive"

    # Short replies with interest signals
    if len(text) < 50:
        short_positive = ["yes", "interested", "tell me", "call", "please",
                          "more info", "sure", "ok", "sounds interesting", "thanks",
                          "thank you", "sounds good"]
        if any(p in text for p in short_positive):
            return "positive"

    return "unclear"


def find_contact(from_email):
    """Match reply sender back to a contact in the DB."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, first_name, last_name, email, dealership_name, dealership_brand, "
        "phone, role, dealership_city, dealership_state "
        "FROM peer_outreach_contacts WHERE LOWER(email) = LOWER(%s)",
        (from_email,)
    )
    contact = cur.fetchone()
    cur.close()
    conn.close()
    return contact


def send_smtp(to_email, to_name, subject, plain_body, html_body=None, in_reply_to=None):
    """Send an email via Gmail SMTP. Optionally thread as a reply."""
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    msg["To"] = formataddr((to_name or "", to_email))
    msg["Subject"] = subject
    msg["Message-ID"] = f"peer-outreach-reply-{int(time.time())}@trafficdriver.ai"

    # Threading: reply in the same conversation
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return msg["Message-ID"]
    except Exception as e:
        print(f"  SMTP error sending to {to_email}: {e}")
        return None


def send_lead_notification(contact, reply_body, reply_subject, last_sent_body, last_sent_subject, dry_run=False):
    """Send lead notification to growth@paramountals.com."""
    fn = contact["first_name"]
    ln = contact["last_name"]
    dealer = contact["dealership_name"]
    subject = f"[Peer Outreach] Lead: {fn} {ln} — {dealer}"

    plain_body = f"""Lead from peer outreach — positive reply

    Contact: {fn} {ln}
    Role: {contact['role']}
    Dealership: {dealer}
    Brand: {contact['dealership_brand']}
    Email: {contact['email']}
    Phone: {contact['phone'] or 'N/A'}
    Location: {contact['dealership_city']}, {contact['dealership_state']}

    Gabby sent (subject: {last_sent_subject}):
    {last_sent_body}

    Their Reply:
    Subject: {reply_subject}
    {reply_body}

    Status: Awaiting follow-up from Gabby
    """

    html_body = f"""
    <h3>Lead from peer outreach — positive reply</h3>
    <hr>
    <strong>Contact Details:</strong><br>
    Name: {fn} {ln}<br>
    Role: {contact['role']}<br>
    Dealership: {dealer}<br>
    Brand: {contact['dealership_brand']}<br>
    Email: {contact['email']}<br>
    Phone: {contact['phone'] or 'N/A'}<br>
    Location: {contact['dealership_city']}, {contact['dealership_state']}<br>
    <hr>
    <strong>Gabby sent (subject: {last_sent_subject}):</strong><br>
    <pre style="white-space:pre-wrap;font-family:Arial,sans-serif;">{last_sent_body}</pre>
    <hr>
    <strong>Their Reply:</strong><br>
    Subject: {reply_subject}<br>
    <br>
    {reply_body}
    <hr>
    <em>Status: Awaiting follow-up from Gabby</em>
    """

    if dry_run:
        print(f"  [DRY RUN] Lead notification would go to {GROWTH_EMAIL}")
        return "dry-run-lead"

    return send_smtp(GROWTH_EMAIL, "Growth", subject, plain_body, html_body)


def generate_auto_reply(contact, original_reply_text, original_subject):
    """Generate Gabby's conversational auto-reply."""
    fn = contact["first_name"] or "there"
    dealer = contact["dealership_name"] or "your store"

    body = f"""Hi {fn},

Thanks for getting back to me. I'd love to set up a quick call to walk through what this could look like for {dealer}. No rush, just whenever works on your end.

What's your schedule look like next week?"""

    # Use Re: prefix with original subject
    subj = original_subject
    if subj and not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"

    return subj or "Re: your reply", body


def send_auto_reply(contact, subject, body, dry_run=False, original_msg_id=None):
    """Send Gabby's auto-reply back to the contact, threaded in the same conversation."""
    plain = body + "\n\n" + SIGNATURE_PLAIN
    html = "<pre style='white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#333;margin:0;'>" + body + "</pre><br>" + SIGNATURE_HTML

    if dry_run:
        print(f"  [DRY RUN] Auto-reply would go to {contact['email']}")
        return "dry-run-auto"

    return send_smtp(contact["email"], contact["first_name"], subject, plain, html, in_reply_to=original_msg_id)


def process_reply(from_email, reply_subject, reply_body, dry_run=False, original_msg_id=None):
    """Process a single reply end-to-end."""
    print(f"\nProcessing reply from {from_email}: \"{reply_subject}\"")

    # 1. Match to contact
    contact = find_contact(from_email)
    if not contact:
        print(f"  No contact match for {from_email}, skipping")
        return

    print(f"  Matched: {contact['first_name']} {contact['last_name']} ({contact['dealership_name']})")

    # 2. Classify intent
    intent = classify_intent(reply_body, reply_subject)
    print(f"  Intent: {intent}")

    # 3. Act based on intent
    conn = get_db()
    cur = conn.cursor()

    if intent == "positive" or intent == "unclear":
        # Fetch last email Gabby sent to this contact
        cur.execute("""
            SELECT subject, body_text FROM peer_outreach_log
            WHERE contact_id = %s ORDER BY created_at DESC LIMIT 1
        """, (contact["id"],))
        last_sent = cur.fetchone()
        last_sent_subject = last_sent["subject"] if last_sent else "(unknown)"
        last_sent_body = last_sent["body_text"] if last_sent and last_sent["body_text"] else "(not recorded)"

        # Send lead notification
        lead_id = send_lead_notification(contact, reply_body, reply_subject, last_sent_body, last_sent_subject, dry_run)
        lead_sent = lead_id is not None

        # Generate and send auto-reply
        reply_subj, reply_body_text = generate_auto_reply(contact, reply_body, reply_subject)
        auto_id = send_auto_reply(contact, reply_subj, reply_body_text, dry_run, original_msg_id=original_msg_id)
        auto_sent = auto_id is not None

        # Update contact
        cur.execute("""
            UPDATE peer_outreach_contacts
            SET status = 'conversation', reply_intent = %s, last_reply_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (intent, contact["id"]))

        # Log reply
        cur.execute("""
            INSERT INTO peer_outreach_replies (contact_id, from_email, subject, body_text, intent, lead_notification_sent, auto_reply_sent, message_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (contact["id"], from_email, reply_subject, reply_body, intent, lead_sent, auto_sent, original_msg_id))

        print(f"  ✓ Lead notification: {'sent' if lead_sent else 'failed'}")
        print(f"  ✓ Auto-reply: {'sent' if auto_sent else 'failed'}")

    elif intent == "negative":
        cur.execute("""
            UPDATE peer_outreach_contacts
            SET status = 'suppressed', reply_intent = 'negative', last_reply_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (contact["id"],))

        cur.execute("""
            INSERT INTO peer_outreach_replies (contact_id, from_email, subject, body_text, intent, message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (contact["id"], from_email, reply_subject, reply_body, intent, original_msg_id))

        print(f"  ✓ Marked suppressed")

    elif intent == "ooo":
        cur.execute("""
            UPDATE peer_outreach_contacts
            SET reply_intent = 'ooo', last_reply_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (contact["id"],))

        cur.execute("""
            INSERT INTO peer_outreach_replies (contact_id, from_email, subject, body_text, intent, message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (contact["id"], from_email, reply_subject, reply_body, intent, original_msg_id))

        print(f"  ✓ Logged OOO — will retry next cycle")

    elif intent == "bounce":
        cur.execute("""
            UPDATE peer_outreach_contacts
            SET status = 'suppressed', reply_intent = 'bounce', last_reply_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (contact["id"],))

        cur.execute("""
            INSERT INTO peer_outreach_replies (contact_id, from_email, subject, body_text, intent, message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (contact["id"], from_email, reply_subject, reply_body, intent, original_msg_id))

        print(f"  ✓ Marked as bounce — suppressed")

    conn.commit()
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Process peer outreach replies via Gmail IMAP")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    print("Connecting to Gmail IMAP...")
    context = ssl.create_default_context()
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context)
    mail.login(IMAP_EMAIL, IMAP_PASSWORD)
    mail.select("inbox")

    # Search for unseen messages only
    _, messages = mail.search(None, "UNSEEN")
    msg_nums = messages[0].split()
    
    print(f"Unread messages: {len(msg_nums)}")
    msg_nums = msg_nums

    if not msg_nums:
        print("No new replies to process.")
        mail.logout()
        return

    processed = 0
    for num in msg_nums:
        _, msg_data = mail.fetch(num, "(RFC822)")
        for response_part in msg_data:
            if not isinstance(response_part, tuple):
                continue

            msg = email.message_from_bytes(response_part[1])

            # Extract sender
            from_field = decode_mime_header(msg["From"])
            from_email = extract_email_address(from_field)

            # Skip our own sent messages
            if from_email == FROM_EMAIL.lower():
                continue

            # Extract subject
            msg_subject = decode_mime_header(msg["Subject"])

            # Extract Message-ID for threading
            original_msg_id = decode_mime_header(msg.get("Message-ID", "")).strip()

            # Skip if already processed (check message_id in replies table)
            if original_msg_id:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT id FROM peer_outreach_replies WHERE message_id = %s", (original_msg_id,))
                if cur.fetchone():
                    print(f"  Already processed: {from_email} (msg {original_msg_id[:40]}), skipping")
                    cur.close()
                    conn.close()
                    # Still mark as read
                    if not args.dry_run:
                        mail.store(num, "+FLAGS", "\\Seen")
                    continue
                cur.close()
                conn.close()

            # Extract body
            body_text = get_body_text(msg)
            if not body_text:
                body_text = "(no text body)"

            # Truncate for logging
            body_preview = body_text[:500]

            process_reply(from_email, msg_subject, body_text, args.dry_run, original_msg_id=original_msg_id)
            processed += 1

            # Always mark as read after processing
            if not args.dry_run:
                mail.store(num, "+FLAGS", "\\Seen")

    mail.close()
    mail.logout()

    print(f"\nDone. Processed {processed} replies.")


if __name__ == "__main__":
    main()
