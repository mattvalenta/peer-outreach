"""
Seed peer_outreach_contacts from the main CRM database.
Filters for General Managers with valid emails, not suppressed.

Usage:
  python3 seed_contacts.py --dry-run          # Preview what would be imported
  python3 seed_contacts.py                     # Import for real
"""

import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

# ── Config ──────────────────────────────────────────────
# Main CRM database (read-only — data lives here)
MAIN_DB_URL = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--main-db" else None

# Target sales_crm database (where peer outreach tables live)
TARGET_DB_URL = os.environ.get("DATABASE_URL", "")


def get_main_db():
    """Connect to the main CRM database. Override URL via --main-db flag."""
    if MAIN_DB_URL:
        return psycopg2.connect(MAIN_DB_URL, cursor_factory=RealDictCursor)
    # Default — you'll update this to your actual CRM connection
    url = os.environ.get("MAIN_CRM_DATABASE_URL", TARGET_DB_URL)
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def get_target_db():
    return psycopg2.connect(TARGET_DB_URL, cursor_factory=RealDictCursor)


def fetch_gms_from_crm():
    """Pull GMs from the main CRM. UPDATE THIS QUERY to match your actual schema."""
    conn = get_main_db()
    cur = conn.cursor()

    # Query the main CRM's contact tables.
    # Adjust table/column names to match your actual CRM schema.
    cur.execute("""
        SELECT
            c.first_name,
            c.last_name,
            c.email,
            c.role,
            d.name AS dealership_name,
            d.brand AS dealership_brand,
            d.city AS dealership_city,
            d.state AS dealership_state,
            c.phone,
            c.id AS source_contact_id
        FROM prospect_dealership_contacts c
        JOIN prospect_dealerships d ON c.prospect_dealership_id = d.id
        LEFT JOIN email_validations ev ON ev.email = c.email
        WHERE c.email IS NOT NULL
          AND c.email != ''
          AND c.role ILIKE '%general manager%'
          AND (ev.is_valid IS NULL OR ev.is_valid = TRUE)
          AND (ev.is_unsubscribed IS NULL OR ev.is_unsubscribed = FALSE)
          AND c.is_unsubscribed IS NOT TRUE
        ORDER BY c.id
    """)

    contacts = cur.fetchall()
    cur.close()
    conn.close()
    return contacts


def import_contacts(contacts, dry_run=False):
    """Insert contacts into peer_outreach_contacts, skipping duplicates."""
    conn = get_target_db()
    cur = conn.cursor()

    imported = 0
    skipped = 0

    for c in contacts:
        # Check if already imported
        cur.execute("SELECT id FROM peer_outreach_contacts WHERE source_contact_id = %s AND email = %s",
                    (c["source_contact_id"], c["email"]))
        if cur.fetchone():
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] {c['first_name']} {c['last_name']} — {c['dealership_name']} ({c['dealership_brand']})")
            imported += 1
            continue

        cur.execute("""
            INSERT INTO peer_outreach_contacts (
                first_name, last_name, email, role, dealership_name,
                dealership_brand, dealership_city, dealership_state,
                phone, source_contact_id, status, outreach_week
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', 1)
        """, (
            c["first_name"], c["last_name"], c["email"], c["role"],
            c["dealership_name"], c["dealership_brand"],
            c["dealership_city"], c["dealership_state"],
            c["phone"], c["source_contact_id"]
        ))
        imported += 1

    conn.commit()
    cur.close()
    conn.close()

    return imported, skipped


def main():
    parser = argparse.ArgumentParser(description="Seed peer outreach contacts from CRM")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--main-db", type=str, help="Main CRM database URL (override default)")
    args = parser.parse_args()

    # Override main DB if provided
    global MAIN_DB_URL
    if args.main_db:
        MAIN_DB_URL = args.main_db

    print("Fetching GMs from CRM...")
    contacts = fetch_gms_from_crm()
    print(f"Found {len(contacts)} GMs with valid emails")

    if not contacts:
        print("No contacts found. Check your CRM query.")
        return

    print("Importing to peer_outreach_contacts...")
    imported, skipped = import_contacts(contacts, args.dry_run)

    print(f"\nDone. Imported: {imported}, Skipped (already exists): {skipped}")


if __name__ == "__main__":
    main()
