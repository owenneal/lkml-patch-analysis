import sqlite3
import argparse
import csv
from datetime import datetime
from ..core.data_access import get_all_cve_ids, get_patches_for_cve
from ..core.utils import clean_csv_final_report
from .link_cve_to_commit import normalize_subject # Re-use the normalizer

SUSPECTED_CVE_DB = "suspected_cve_patches.db"
COMMIT_DB_PATH = "commits.db"

def get_cve_category_and_base_url(cve_id: str) -> tuple[str, str]:
    """
    Retrieves the category and the URL of the base patch for a given CVE ID.
    """
    conn = sqlite3.connect(SUSPECTED_CVE_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT category FROM suspected_cve_patches WHERE match_cve_id = ? LIMIT 1", (cve_id,))
    result = cursor.fetchone()
    category = result[0] if result else "N/A"

    # try to find the base patch URL
    patches = get_patches_for_cve(cve_id)
    base_url = min(patches, key=lambda p: p[0])[2] if patches else "N/A"
    
    conn.close()
    return category, base_url

def find_matching_commit(cve_id: str, commit_cursor) -> tuple[str, str]:
    """
    Finds the matching commit hash for a CVE by searching patch subjects.
    Returns the commit hash and the commit URL.
    """
    cve_patches = get_patches_for_cve(cve_id)
    if not cve_patches:
        return None, None

    for _, subject, _ in cve_patches:
        normalized_subject = normalize_subject(subject)
        commit_cursor.execute("SELECT hash FROM commits WHERE subject = ?", (normalized_subject,))
        result = commit_cursor.fetchone()
        if result:
            commit_hash = result[0]
            commit_url = f"https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/commit/?id={commit_hash}"
            return commit_hash, commit_url
            
    return None, None

def main():
    """
    Generates a final report combining CVE categories with their final merged commit info.
    """
    parser = argparse.ArgumentParser(description="Generate a combined report of CVE categories and their linked git commits.")
    parser.add_argument('--limit', type=int, default=0, help="Limit the number of CVEs to process (0 for all).")
    args = parser.parse_args()

    conn_cve = sqlite3.connect(SUSPECTED_CVE_DB)
    cve_ids = [row[0] for row in conn_cve.execute("SELECT DISTINCT match_cve_id FROM suspected_cve_patches WHERE category IS NOT NULL").fetchall()]
    conn_cve.close()

    if args.limit > 0:
        cve_ids = cve_ids[:args.limit]

    print(f"Found {len(cve_ids)} categorized CVEs to process for the final report.")

    conn_commit = sqlite3.connect(COMMIT_DB_PATH)
    commit_cursor = conn_commit.cursor()

    report_data = []
    for cve_id in cve_ids:
        category, base_url = get_cve_category_and_base_url(cve_id)
        commit_hash, commit_url = find_matching_commit(cve_id, commit_cursor)

        if not commit_hash:
            # If no commit was found, still include it in the report to show it was processed.
            commit_hash = "Not Found"
            commit_url = "N/A"

        report_data.append((cve_id, category, base_url, commit_hash, commit_url))
        print(f"Processed {cve_id} -> Category: {category}, Commit Found: {'Yes' if commit_url != 'N/A' else 'No'}")

    conn_commit.close()

    output_file = f"final_cve_analysis_report_{datetime.now().strftime('%Y%m%d')}.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['CVE_ID', 'Vulnerability_Category', 'Base_Patch_URL', 'Merged_Commit_Hash', 'Merged_Commit_URL'])
        writer.writerows(report_data)
    clean_csv_final_report(input_path=output_file, remove_not_found=True)

    print(f"\nFinal report generated successfully: {output_file}")

if __name__ == "__main__":
    main()