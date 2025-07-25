import sqlite3
import argparse
import re
import csv
from datetime import datetime
from ..core.data_access import get_all_cve_ids, get_patches_for_cve, get_patch_emails_by_ids
from ..core.email_parser import parse_email_content, extract_patch_info, extract_series_position, extract_filenames_from_diff

COMMIT_DB_PATH = "commits.db"
SUSPECTED_CVE_DB = "suspected_cve_patches.db"
GIT_LOG_PATH = "gitlog_2024.txt"

def normalize_subject(subject: str) -> str:
    """Normalize the email subject by converting to lowercase, removing prefixes like "Re:" and "[patch]", and stripping whitespace."""
    subject = subject.lower()
    subject = re.sub(r'^(re:\s*|\[patch[^\]]*\]\s*)', '', subject).strip()
    return subject

def create_and_populate_commit_db():
    """
    Parses the git log and populates the commis.db sqlite database.
    """
    
    try:
        if sqlite3.connect(COMMIT_DB_PATH).execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commits'").fetchone():
            print("Commit database already exists. Skipping creation.")
            return
    except sqlite3.OperationalError:
        pass # Table does not exist, we will create it

    print("Creating commit database...")
    conn = sqlite3.connect(COMMIT_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE commits (
            hash TEXT PRIMARY KEY,
            subject TEXT
        )
    """)

    with open(GIT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    commits = content.split('<commit_begin>\n')
    for commit_data in commits:
        if not commit_data.strip():
            continue
        
        lines = commit_data.strip().split('\n')
        commit_hash = lines[0]
        
        # Find the date line, the subject is on the next line
        subject_line_ind = -1
        for i, line in enumerate(lines):
            if re.search(r'\s\d{4}\s[+-]\d{4}$', line): # look for a date line like '... 2025 -0700'
                subject_line_ind = i + 1
                break
        if subject_line_ind == -1 or subject_line_ind >= len(lines):
            continue
        subject = lines[subject_line_ind]

        cursor.execute(
            "INSERT OR IGNORE INTO commits (hash, subject) VALUES (?, ?)",
            (commit_hash, normalize_subject(subject))
        )

    conn.commit()
    conn.close()
    print("Commit database created successfully.")



def write_commit_cve_report(report_data, output_file="cve_commit_report.csv"):
    """
    Writes the CVE commit report to a CSV file.
    """
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['CVE ID', 'Commit Hash', 'Subject', 'Commit URL'])
        writer.writerows(report_data)
    print(f"Report written to {output_file}")



def connect_cve_patch_subjects_to_commits(limit: int = 100):
    """
    Connects CVE patch subjects to commits in the database.
    """
    cve_ids = get_all_cve_ids()
    if limit > 0:
        cve_ids = cve_ids[:limit]
    report_data = []
    conn = sqlite3.connect(COMMIT_DB_PATH)
    cursor = conn.cursor()

    print(f"Attempting to link {len(cve_ids)} CVE IDs to commits...")

    for cve_id in cve_ids:
        cve_patches = get_patches_for_cve(cve_id)
        if not cve_patches:
            print(f"No patches found for CVE {cve_id}. Skipping.")
            continue

        match_found_for_cve = False
        for _, subject, _ in cve_patches:
            normalized_subject = normalize_subject(subject)
            cursor.execute(
                "SELECT hash FROM commits WHERE subject = ?",
                (normalized_subject,)
            )
            commit_hash = cursor.fetchone()
            if commit_hash:
                commit_url = f"https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/commit/?id={commit_hash[0]}"
                report_data.append((cve_id, commit_hash[0], subject, commit_url))
                print(f"Linked CVE {cve_id} to commit {commit_hash[0]} with subject: {subject}")
                match_found_for_cve = True
                break
        if not match_found_for_cve:
            print(f"No matching commit found for CVE {cve_id} with subject: {subject}")
    return report_data


def main():
    parser = argparse.ArgumentParser(description="Link CVE patches to commits in the Linux kernel.")
    parser.add_argument('--create-db', action='store_true', help="Create and populate the commit database.")
    parser.add_argument('--connect-cve', action='store_true', help="Connect CVE patches to commits.")
    parser.add_argument('--limit', type=int, default=100, help="Limit the number of CVEs to process (default: 100).")


    args = parser.parse_args()
    if args.create_db:
        create_and_populate_commit_db()
    if args.connect_cve:
        report_data = connect_cve_patch_subjects_to_commits(limit=args.limit)
        write_commit_cve_report(report_data)

if __name__ == "__main__":
    main()
    print("Commit database creation script completed.")