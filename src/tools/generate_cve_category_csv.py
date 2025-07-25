import sqlite3
import csv
import argparse
from datetime import datetime
from ..core.email_parser import extract_patch_info, extract_series_position

"""
Script to generate a csv report which will include the initial patch email url of
a CVE related patch, its category, and the CVE id.
"""



SUSPECTED_CVE_DB = "suspected_cve_patches.db" # change as needed

def find_base_patch_email(cursor, cve_id):
    """
    Find the base patch email for a given CVE ID.
    """
    cursor.execute("SELECT email_id, subject, url FROM suspected_cve_patches WHERE match_cve_id = ?", (cve_id,))
    emails = cursor.fetchall()
    base_email_option = None
    base_email_url = None

    lowest_score = (float('inf'), float('inf'), float('inf'))  # (series_position, patch_position, email_id)
    for email_id, subject, url in emails:
        patch_info = extract_patch_info(subject)
        if not patch_info or patch_info.get('is_reply'):
            continue

        version_str = patch_info.get('version', 'v1')
        digits_from_version = ''.join(filter(str.isdigit, version_str))
        if digits_from_version:
            version_num = int(digits_from_version)
        else:
            version_num = 0

        series_position, _ = extract_series_position(subject)

        # we want the lowest series position, then lowest patch position, then if all else is equal, the lowest email_id
        current_score = (series_position, version_num, email_id)
        if current_score < lowest_score:
            lowest_score = current_score
            base_email_url = url

    if not base_email_url:
        min_email_id = min(emails, key=lambda e: e[0])
        return min_email_id[2]

    return base_email_url


def fetch_categorized_cves():
    """
    Fetch all CVEs and their categories from the suspected_cve_patches table.
    """
    try:
        conn = sqlite3.connect(SUSPECTED_CVE_DB)
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT match_cve_id, category
            FROM suspected_cve_patches
            WHERE category IS NOT NULL AND category != '' AND category != 'Other'
            ORDER BY match_cve_id;
        """
        cursor.execute(query)
        cve_list = cursor.fetchall()

        categorized_cves = []
        for cve_id, category in cve_list:
            base_email_url = find_base_patch_email(cursor, cve_id)
            if base_email_url:
                categorized_cves.append((cve_id, category, base_email_url))
        return categorized_cves
    except sqlite3.Error as e:
        print(f"Error fetching categorized CVEs: {e}")
        return []
    finally:
        conn.close()

def write_csv_report(data, output_file):
    """
    Write the categorized CVEs to a CSV file.
    """
    try:
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['CVE ID', 'Category', 'Base Patch Email Url'])
            writer.writerows(data)
        print(f"CSV report written to {output_file}")
    except Exception as e:
        print(f"Error writing CSV report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate a CSV report of categorized CVEs.")
    filename = f"cve_categories_{datetime.now().strftime('%Y%m%d')}.csv"
    parser.add_argument("--output", type=str, default=filename, help="Output CSV file name.")
    args = parser.parse_args()

    cve_data = fetch_categorized_cves()
    if cve_data:
        write_csv_report(cve_data, args.output)
        print("CSV report generation completed.")
    else:
        print("No categorized CVEs found.")

if __name__ == "__main__":
    main()
