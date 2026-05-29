"""
Seed peer_outreach_contacts from the main CRM database.
Filters for General Managers with valid emails, not suppressed.

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
DB_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def fetch_gms_from_crm(limit=None):
    """Pull GMs from the existing prospect tables in the same database."""
    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT
            c.id AS source_contact_id,
            c.first_name,
            c.last_name,
            c.email,
            c.job_title AS role,
            d.company_name AS dealership_name,
            d.domain AS dealership_domain,
            CASE WHEN c.phone_numbers IS NOT NULL AND jsonb_array_length(c.phone_numbers) > 0
                 THEN c.phone_numbers->>0 ELSE NULL END AS phone
        FROM prospect_dealership_contacts c
        JOIN prospect_dealerships d ON c.dealership_id = d.id
        WHERE c.email IS NOT NULL
          AND c.email != ''
          AND c.is_active = true
          AND c.is_unsubscribed = false
          AND c.job_title ILIKE '%general manager%'
        ORDER BY c.id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    cur.execute(query)
    contacts = cur.fetchall()
    cur.close()
    conn.close()
    return contacts


def import_contacts(contacts, dry_run=False):
    """Insert contacts into peer_outreach_contacts, skipping duplicates."""
    conn = get_db()
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
                dealership_name, phone, status, outreach_week
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', 1)
        """, (
            c["source_contact_id"], c["first_name"], c["last_name"],
            c["email"], c["role"], c["dealership_name"], c["phone"]
        ))
        imported += 1

    conn.commit()
    cur.close()
    conn.close()

    return imported, skipped


def main():
    parser = argparse.ArgumentParser(description="Seed peer outreach contacts from CRM")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--limit", type=int, help="Max contacts to import")
    args = parser.parse_args()

    print("Fetching GMs from prospect tables...")
    contacts = fetch_gms_from_crm(limit=args.limit)
    print(f"Found {len(contacts)} GMs with valid emails")

    if not contacts:
        print("No contacts found.")
        return

    print("Importing to peer_outreach_contacts...")
    imported, skipped = import_contacts(contacts, args.dry_run)

    print(f"\nDone. Imported: {imported}, Skipped (already exists): {skipped}")


if __name__ == "__main__":
    main()
