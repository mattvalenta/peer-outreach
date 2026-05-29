"""
Seed peer_outreach_contacts from the clients database (sales_companies + sales_contacts).
Filters for General Managers with valid emails.

Reads from:  clients DB (sales_contacts + sales_companies)
Writes to:   sales_crm DB (peer_outreach_contacts)

Usage:
  python3 seed_contacts.py --dry-run          # Preview what would be imported
  python3 seed_contacts.py                     # Import for real
  python3 seed_contacts.py --limit 50          # Import max 50 contacts
"""

import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

# ── Config ──────────────────────────────────────────────
CLIENTS_DB_URL = os.environ.get("CLIENTS_DB_URL", "")
SALES_CRM_DB_URL = os.environ.get("SALES_CRM_DB_URL", os.environ.get("DATABASE_URL", ""))


def get_clients_db():
    return psycopg2.connect(CLIENTS_DB_URL, cursor_factory=RealDictCursor)


def get_sales_crm_db():
    return psycopg2.connect(SALES_CRM_DB_URL, cursor_factory=RealDictCursor)


def get_bad_emails():
    """Get set of bad email addresses from sales_crm.bad_emails for filtering."""
    conn = get_sales_crm_db()
    cur = conn.cursor()
    cur.execute("SELECT LOWER(email) AS email FROM bad_emails")
    bad = {row['email'] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return bad


def fetch_gms_from_clients(limit=None):
    """Pull GMs from the clients database (sales_contacts + sales_companies)."""
    conn = get_clients_db()
    cur = conn.cursor()

    query = """
        SELECT
            c.id::text AS source_contact_id,
            c.first_name,
            c.last_name,
            COALESCE(NULLIF(c.email_1, ''), NULLIF(c.email_2, ''), NULLIF(c.personal_email, '')) AS email,
            c.title AS role,
            co.company_name AS dealership_name,
            co.city AS dealership_city,
            co.state AS dealership_state,
            c.contact_phone_1 AS phone
        FROM sales_contacts c
        JOIN sales_companies co ON c.company_id = co.id
        WHERE c.title_category IN ('General Manager', 'Owner')
          AND (NULLIF(c.email_1, '') IS NOT NULL
            OR NULLIF(c.email_2, '') IS NOT NULL
            OR NULLIF(c.personal_email, '') IS NOT NULL)
        ORDER BY c.created_at
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    cur.execute(query)
    contacts = cur.fetchall()
    cur.close()
    conn.close()
    return contacts


def import_contacts(contacts, dry_run=False):
    """Insert contacts into peer_outreach_contacts in sales_crm DB, skipping duplicates."""
    conn = get_sales_crm_db()
    cur = conn.cursor()

    imported = 0
    skipped = 0

    for c in contacts:
        # Check if already imported
        cur.execute(
            "SELECT id FROM peer_outreach_contacts WHERE source_contact_id = %s AND email = %s",
            (c["source_contact_id"], c["email"])
        )
        if cur.fetchone():
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] {c['first_name']} {c['last_name']} — {c['dealership_name']} ({c['email']})")
            imported += 1
            continue

        cur.execute("""
            INSERT INTO peer_outreach_contacts (
                source_contact_id, first_name, last_name, email, role,
                dealership_name, dealership_city, dealership_state, phone,
                status, outreach_week
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', 1)
        """, (
            c["source_contact_id"], c["first_name"], c["last_name"],
            c["email"], c["role"], c["dealership_name"],
            c["dealership_city"], c["dealership_state"], c["phone"]
        ))
        imported += 1

    conn.commit()
    cur.close()
    conn.close()

    return imported, skipped


def main():
    parser = argparse.ArgumentParser(description="Seed peer outreach contacts from clients DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--limit", type=int, help="Max contacts to import")
    args = parser.parse_args()

    print("Fetching GMs from clients database...")
    contacts = fetch_gms_from_clients(limit=args.limit)
    print(f"Found {len(contacts)} GMs with valid emails")

    # Filter out bad emails
    print("Loading bad email suppression list...")
    bad_emails = get_bad_emails()
    print(f"{len(bad_emails)} bad emails in suppression list")
    contacts = [c for c in contacts if c['email'].lower() not in bad_emails]
    print(f"{len(contacts)} contacts after removing bad emails")

    if not contacts:
        print("No contacts found.")
        return

    print("Importing to peer_outreach_contacts (sales_crm)...")
    imported, skipped = import_contacts(contacts, args.dry_run)

    print(f"\nDone. Imported: {imported}, Skipped (already exists): {skipped}")


if __name__ == "__main__":
    main()
