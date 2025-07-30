import sqlite3
import argparse
import re
import csv
from collections import defaultdict
from datetime import datetime
from ..core.data_access import get_all_cve_ids, get_git_pull_emails, get_patches_for_cve, get_patch_emails_by_ids
from ..core.email_parser import parse_email_content, extract_patch_info, extract_series_position
from .git_pull_case_study import extract_commit_authors_and_subjects, extract_commit_hashes

SUSPECTED_CVE_DB = "suspected_cve_patches.db"

def normalize_subject(subject: str) -> str:
    """Normalize the email subject by converting to lowercase, removing prefixes like "Re:" and "[patch]", and stripping whitespace."""
    subject = subject.lower()
    subject = re.sub(r'^(re:\s*|\[patch[^\]]*\]\s*)', '', subject).strip()
    return subject


def find_base_patch_url(emails: list) -> str:
    """Finds the base patch URL from a list of emails for a CVE."""
    if not emails:
        return ""

    base_email_url = None
    lowest_score = (float('inf'), float('inf'), float('inf'))  # (series_pos, version, email_id)

    for email_id, subject, url in emails:
        patch_info = extract_patch_info(subject)
        if not patch_info or patch_info.get('is_reply'):
            continue

        version_str = patch_info.get('version', 'v1')
        digits = ''.join(filter(str.isdigit, version_str))
        version_num = int(digits) if digits else 0
        series_pos, _ = extract_series_position(patch_info.get('series_info'))

        current_score = (series_pos, version_num, email_id)
        if current_score < lowest_score:
            lowest_score = current_score
            base_email_url = url

    return base_email_url if base_email_url else min(emails, key=lambda e: e[0])[2]


def build_git_pull_dict():
    """
    Builds a lookup table of patches contained in the GIT PULL emails
    """
    pull_emails = get_git_pull_emails()
    patch_to_pull_map = defaultdict(list)

    for _, _, url, html_content, _ in pull_emails:
        parsed_content = parse_email_content(html_content)
        if not parsed_content:
            continue
        body = parsed_content.get("message_body", "")
        if not body:
            continue
        commits = extract_commit_authors_and_subjects(body)
        for commit in commits:
            normalized_patch = normalize_subject(commit['subject'])
            if url not in patch_to_pull_map[normalized_patch]:
                patch_to_pull_map[normalized_patch].append(url)

    return patch_to_pull_map


def build_commit_hash_to_pull_dict():
    """
    Builds a lookup table of commit hashes contained in the GIT PULL emails
    """
    pull_emails = get_git_pull_emails()
    commit_to_pull_map = defaultdict(list)

    for _, _, url, html_content, _ in pull_emails:
        body = parse_email_content(html_content).get("message_body", "")
        if not body:
            continue

        hashes = extract_commit_hashes(body)
        for commit_hash in hashes:
            if url not in commit_to_pull_map[commit_hash]:
                commit_to_pull_map[commit_hash].append(url)

    return commit_to_pull_map



def find_commit_hashes_in_cve_thread(cve_patches) -> set:
    """
    Finds commit hashes in the CVE thread patches.
    Returns a set of commit hashes found in the patches.
    """
    if not cve_patches:
        return set()

    email_ids = [patch[0] for patch in cve_patches]
    full_emails = get_patch_emails_by_ids(email_ids)
    found_hashes = set()
    for _, _, _, html_content in full_emails:
        body = parse_email_content(html_content).get("message_body", "")
        if not body:
            continue
        hashes = extract_commit_hashes(body)
        found_hashes.update(hashes)

    return found_hashes


def write_csv_report(data, output_file):
    """Writes the verification data to a CSV file."""
    if not data:
        print("No matched CVEs found to write to report.")
        return

    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            #writer.writerow(['CVE_ID', 'Base_Patch_URL', 'Matched_Patch_Subject', 'Git_Pull_URL'])
            writer.writerow(['CVE_ID', 'Base_Patch_URL', 'Found_Commit_Hash', 'Git_Pull_URL'])
            writer.writerows(data)
        print(f"Successfully generated report: {output_file}")
    except IOError as e:
        print(f"Error writing to file {output_file}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Verify if CVE patches appear in GIT PULL emails and generate a CSV report.")
    default_filename = f"cve_gitpull_report_{datetime.now().strftime('%Y%m%d')}.csv"
    parser.add_argument("--output", type=str, default=default_filename, help=f"Output CSV file name (default: {default_filename})")
    parser.add_argument("--limit", type=int, help="Limit the number of CVEs to process.")
    args = parser.parse_args()

    cve_ids = get_all_cve_ids(db_path=SUSPECTED_CVE_DB)
    if args.limit:
        cve_ids = cve_ids[:args.limit]

    #git_pull_lookup = build_git_pull_dict()
    commit_hash_lookup = build_commit_hash_to_pull_dict()
    report_data = []

    print(f"\nChecking {len(cve_ids)} CVEs for inclusion in GIT PULLs...")
    for cve_id in cve_ids:
        cve_patches = get_patches_for_cve(cve_id, db_path=SUSPECTED_CVE_DB)
        if not cve_patches:
            continue
        
        base_url = find_base_patch_url(cve_patches)
        thread_commit_hashes = find_commit_hashes_in_cve_thread(cve_patches)

        for commit_hash in thread_commit_hashes:
            if commit_hash in commit_hash_lookup:
                for pull_url in commit_hash_lookup[commit_hash]:
                    report_data.append((cve_id, base_url, commit_hash, pull_url))
                # Once a hash from this thread is found, we can stop checking other hashes for this CVE.
                break 
        
        # for _, subject, _ in cve_patches:
        #     normalized_subject = normalize_subject(subject)
        #     if normalized_subject in git_pull_lookup:
        #         for pull_url in git_pull_lookup[normalized_subject]:
        #             report_data.append((cve_id, base_url, subject, pull_url))
        #         # Once a patch from the CVE thread is found in a pull request, we can stop checking other patches for this CVE.
        #         break 
    
    write_csv_report(report_data, args.output)

if __name__ == "__main__":
    main()