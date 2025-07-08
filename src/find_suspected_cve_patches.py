import sqlite3
import argparse
from import_cve_jsons import main as import_cve_jsons_main, create_linux_kernel_table


"""
find_suspected_cve_patches.py

file is used to combine functionality of importing the cves in the 2024 cve json folders

how to use:
---------------------------------

1st: Import CVEs and create the kernel table
    - python3 src/find_suspected_cve_patches.py --import-cves

2nd: Find suspected CVE patches
    - python3 src/find_suspected_cve_patches.py --find-suspected

3rd: Populate git pull table in suspected database (omit the limit to use the entire lkml-data-2024.db emails or optionally limit to an amount)
    - python3 src/find_suspected_cve_patches.py --populate-gitpull --limit 10000

"""

# i think you might need to change the path to remove the "lkml-patch-analysis/" , i have this project in a folder titled lkml-patch-analysis

DB_PATH = "lkml-patch-analysis/lkml-data-2024.db" # this should stay the same, we are keeping the original email data in this database
CVE_DB_PATH = "lkml-patch-analysis/suspected_cve_patches.db"  # this is the database where we store the suspected CVE patches data
SUSPECTED_CVE_DB = "lkml-patch-analysis/suspected_cve_patches.db" # now stored in the same place as all cve data


def import_cves_and_create_kernel_table():
    """
    Imports cve jsons into the suspected_cve_patches.db and creates the linux_kernel_cves table
    using the import_cve_jsons.py file
    """
    import_cve_jsons_main()
    print("Creationg linux_kernel_cves table")
    create_linux_kernel_table(SUSPECTED_CVE_DB)


def populate_git_pull_table_in_suspected_db(src_db=DB_PATH, dst_db=SUSPECTED_CVE_DB, limit=None):
    """
    Create and populate the git_pull_emails table in the suspected_cve_patches.db
    by extracting git pull emails from the mails table in the main database.
    Optionally limit the number of emails processed.
    """
    src_conn = sqlite3.connect(src_db)
    src_cursor = src_conn.cursor()
    dst_conn = sqlite3.connect(dst_db)
    dst_cursor = dst_conn.cursor()

    # Create the table if it doesn't exist
    dst_cursor.execute("""
        CREATE TABLE IF NOT EXISTS git_pull_emails (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            html_content TEXT,
            pull_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    patterns = [
        ("LIKE '%[GIT PULL]%'", "GIT_PULL"),
        ("LIKE '%Re: [GIT PULL]%'", "GIT_PULL_REPLY")
    ]
    total_inserted = 0
    for pattern, pull_type in patterns:
        query = f"""
            SELECT id, title, url, html_content FROM mails
            WHERE title {pattern}
              AND id NOT IN (SELECT id FROM git_pull_emails)
        """
        if limit:
            query += f" LIMIT {limit}"
        src_cursor.execute(query)
        rows = src_cursor.fetchall()
        if rows:
            dst_cursor.executemany("""
                INSERT OR IGNORE INTO git_pull_emails (id, title, url, html_content, pull_type)
                VALUES (?, ?, ?, ?, ?)
            """, [(row[0], row[1], row[2], row[3], pull_type) for row in rows])
            total_inserted += len(rows)
    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    print(f"Inserted {total_inserted} git pull emails into git_pull_emails table in {dst_db}")

def export_suspected_cve_patches(src_db = DB_PATH, dst_db = SUSPECTED_CVE_DB):
    """
    Exports suspected CVE patches from the source database to the destination database.
    This function creates the destination table if it does not exist and copies data from the source database.
    I only made this to centralize the cve data into one database.
    """


    src_conn = sqlite3.connect(src_db)
    src_cursor = src_conn.cursor()
    dst_conn = sqlite3.connect(dst_db)
    dst_cursor = dst_conn.cursor()

    # first make the table in the new database
    dst_cursor.execute("""
        CREATE TABLE IF NOT EXISTS suspected_cve_patches (
            email_id INTEGER PRIMARY KEY,
            subject TEXT,
            url TEXT,
            match_cve_id TEXT,
            match_type TEXT,
            match_keyword TEXT
        )
    """)

    # now copy the data from the source database to the destination database
    src_cursor.execute("SELECT email_id, subject, url, match_cve_id, match_type, match_keyword FROM suspected_cve_patches")
    rows = src_cursor.fetchall()
    dst_cursor.executemany("""
        INSERT OR REPLACE INTO suspected_cve_patches
        (email_id, subject, url, match_cve_id, match_type, match_keyword)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)

    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    print(f"Exported {len(rows)} suspected_cve_patches to {dst_db}")

def get_linux_kernel_cves(db_path=SUSPECTED_CVE_DB):
    """Fetches Linux kernel CVEs from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT cve_id, title FROM linux_kernel_cves")
    cves = cursor.fetchall()
    conn.close()
    return cves

def get_existing_cve_patch_ids(db_path=SUSPECTED_CVE_DB):
    """Fetches existing CVE patch email IDs from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT email_id FROM cve_patches")
    ids = set(row[0] for row in cursor.fetchall())
    conn.close()
    return ids

def create_suspected_table():
    """
    Creates the suspected_cve_patches table in the database if it does not exist.
    """
    conn = sqlite3.connect(SUSPECTED_CVE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suspected_cve_patches (
            email_id INTEGER PRIMARY KEY,
            subject TEXT,
            url TEXT,
            match_cve_id TEXT,
            match_type TEXT,
            match_keyword TEXT
        )
    """)
    conn.commit()
    conn.close()

def find_and_store_suspected_patches():
    """
    Finds suspected CVE patches based on titles in the emails and stores them in the database.
    This function retrieves CVE IDs and titles, checks for matches in email subjects,
    and inserts suspected patches into the suspected_cve_patches table.
    It uses a substring match on the email subject to find potential CVE patches.
    """
    cves = get_linux_kernel_cves()
    #existing_ids = get_existing_cve_patch_ids()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    insert_cursor = conn.cursor()

    for cve_id, cve_title in cves:
        if not cve_title or len(cve_title) < 8:
            continue
        # Use LIKE for substring match to find which patch emails will be discussing the cves
        cursor.execute("""
            SELECT id, title, url FROM mails
            WHERE LOWER(title) LIKE ?
              AND id NOT IN (SELECT email_id FROM cve_patches)
        """, (f"%{cve_title.lower()}%",))
        for email_id, subject, url in cursor.fetchall():
            insert_cursor.execute("""
                INSERT OR IGNORE INTO suspected_cve_patches
                (email_id, subject, url, match_cve_id, match_type, match_keyword)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (email_id, subject, url, cve_id, "title_substring", cve_title))
    conn.commit()
    conn.close()
    print("Title-based suspected CVE patches stored.")

def main():
    parser = argparse.ArgumentParser(
        description="LKML Patch Analysis: Import CVEs and find suspected CVE patches."
    )

    # import cves from the json files cve list 
    parser.add_argument(
        "--import-cves",
        action="store_true",
        help="Import CVE JSONs and create the linux_kernel_cves table in the suspected_cve_patches.db"
    )

    # find suspected CVE patches from the lkml data db and store them in the suspected_cve_patches table
    # by substring match
    parser.add_argument(
        "--find-suspected",
        action="store_true",
        help="Find and store suspected CVE patches in the suspected_cve_patches table"
    )

    # Git pull email population
    parser.add_argument(
        "--populate-gitpull",
        action="store_true",
        help="Populate git_pull_emails table in suspected_cve_patches.db from mails table"
    )

    # limit for the gitpull importing
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of emails processed when populating git_pull_emails"
    )


    args = parser.parse_args()

    if args.import_cves:
        print("Importing CVEs and creating linux_kernel_cves table...")
        import_cves_and_create_kernel_table()
        print("Done importing CVEs and creating linux_kernel_cves table.")

    if args.find_suspected:
        print("Finding and storing suspected CVE patches...")
        create_suspected_table()
        find_and_store_suspected_patches()
        print("Done finding and storing suspected CVE patches.")

    if args.populate_gitpull:
        print("Populating git_pull_emails table...")
        populate_git_pull_table_in_suspected_db(limit=args.limit)
        print("Done populating git_pull_emails table.")

    if not (args.import_cves or args.find_suspected or args.populate_gitpull):
        parser.print_help()

if __name__ == "__main__":
    main()