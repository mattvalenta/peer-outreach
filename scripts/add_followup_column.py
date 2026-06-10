#!/usr/bin/env python3
"""
Migration: Add followup_sent_at column to peer_outreach_contacts.

This column tracks when the auto@paramountals.net follow-up email was last sent
for each contact. Used by send_followup_emails.py to determine which contacts
are due for a follow-up.

Usage:
  python3 scripts/add_followup_column.py              # Apply migration
  python3 scripts/add_followup_column.py --dry-run     # Preview only
"""

import os
import sys
import argparse
import psycopg2

DB_URL = os.environ.get("SALES_CRM_DB_URL", os.environ.get("DATABASE_URL", ""))


def column_exists(cur, table, column):
    """Check if a column exists in a table."""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, (table, column))
    return cur.fetchone()[0]


def apply_migration(dry_run=False):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    if column_exists(cur, "peer_outreach_contacts", "followup_sent_at"):
        print("Column 'followup_sent_at' already exists. Skipping.")
        cur.close()
        conn.close()
        return

    if dry_run:
        print("[DRY RUN] Would execute:")
        print("  ALTER TABLE peer_outreach_contacts ADD COLUMN followup_sent_at TIMESTAMP;")
        print("  CREATE INDEX idx_peer_outreach_followup ON peer_outreach_contacts (followup_sent_at);")
        cur.close()
        conn.close()
        return

    cur.execute("""
        ALTER TABLE peer_outreach_contacts
        ADD COLUMN followup_sent_at TIMESTAMP;
    """)
    cur.execute("""
        CREATE INDEX idx_peer_outreach_followup
        ON peer_outreach_contacts (followup_sent_at);
    """)
    conn.commit()
    print("✓ Added 'followup_sent_at' column and index.")

    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Add followup_sent_at column")
    parser.add_argument("--dry-run", action="store_true", help="Preview without applying")
    args = parser.parse_args()

    if not DB_URL:
        print("ERROR: Set SALES_CRM_DB_URL or DATABASE_URL environment variable.")
        sys.exit(1)

    apply_migration(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
