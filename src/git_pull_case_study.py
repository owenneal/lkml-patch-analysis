import re
from typing import List, Dict, Tuple
from data_access import get_connection, get_patch_emails, get_git_pull_emails
from email_parser import parse_email_content, extract_patch_signature_improved, normalize_title
from bs4 import BeautifulSoup
import difflib
import requests

#xjtuwxg xiaoguang github user name

GIT_PULL_EMAILS = 6021

def get_best_email_body(html_content: str) -> str:
    """
    Try to extract the best possible plain text body from an email's HTML content.
    Uses parse_email_content, but falls back to get_plaintext_body if the result is empty or flat.
    """
    parsed = parse_email_content(html_content)
    body = parsed.get('message_body', '') or ''
    if body.count('\n') < 5 or len(body.splitlines()) <= 1:
        body = get_plaintext_body(html_content)
    return body



def extract_commit_authors_and_subjects(body: str) -> List[Dict]:
    """
    Extract commit authors and their commit subjects from a git pull email body.
    Looks for lines like 'Name (N):' and collects indented lines as commit subjects.
    """
    commits = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Match author line: Name (N):
        author_match = re.match(r'^(.+?)\s*\((\d+)\):\s*$', line)
        if author_match:
            author = author_match.group(1).strip()
            expected_count = int(author_match.group(2))
            j = i + 1
            commit_count = 0
            # collect indented commit lines
            while j < len(lines):
                commit_line = lines[j]
                # commit lines are indented (at least 4 spaces, often 6)
                if re.match(r'^\s{4,}', commit_line):
                    commit_subject = commit_line.strip()
                    if commit_subject:
                        commits.append({
                            'author': author,
                            'subject': commit_subject,
                            'expected_count': expected_count
                        })
                        commit_count += 1
                    j += 1
                else:
                    break
            i = j
        else:
            i += 1
    return commits


def organize_git_pull_patches(limit: int = 100):
    """
    Organize GIT PULL emails and their patch subjects.
    Returns a dict: {email_id: {'title': ..., 'patches': [list of patch subjects]}}
    """
    pulls = get_git_pull_emails(limit)
    organized = {}
    for email_id, title, url, html_content, pull_type in pulls:
        parsed = parse_email_content(html_content)
        body = parsed.get('message_body', '')


        # If the body is a single long line, try extracting plain text from HTML
        if body.count('\n') < 5 or len(body.splitlines()) <= 1:
            print("Body looks flat, extracting plain text from HTML...")
            body = get_plaintext_body(html_content)


        # print(f"Email {email_id} body length: {len(body)}")
        # print("First 20 lines of body:")
        # for i, line in enumerate(body.splitlines()[:20]):
        #     print(f"{i+1:2d}: {line}")


        commits = extract_commit_authors_and_subjects(body)
        patch_subjects = [c['subject'] for c in commits]
        organized[email_id] = {
            'title': title,
            'patches': patch_subjects,
            'body': body
        }
    return organized



def get_plaintext_body(html_content: str) -> str:
    """
    Extract plain text from HTML, preserving line breaks.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    # Replace <br> and <p> with newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_before("\n")
    text = soup.get_text("\n")
    # Remove excessive blank lines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()



def build_patch_look_up(patch_emails):
    """
    Build a lookup dictionary for patches by email ID.
    """

    lookup = {}
    for email_id, title, url, html_content in patch_emails:
        subject = title.strip().lower()
        subject = re.sub(r'^re:\s*', '', subject)
        subject = re.sub(r'\[patch[^\]]*\]\s*', '', subject)
        subject = subject.strip()
        if subject not in lookup:
            lookup[subject] = []
        lookup[subject].append(email_id)
    return lookup


def link_git_pull_patches_to_threads(organized_git_pulls, patch_subject_lookup):
    """
    For each GIT PULL email, link its patch subjects to patch email IDs.
    Returns a dict: {git_pull_id: {'title': ..., 'patch_links': [(patch_subject, [email_ids])]}}
    """
    linked = {}
    for email_id, info in organized_git_pulls.items():
        patch_links = []
        for patch_subject in info['patches']:
            norm_patch = patch_subject.strip().lower()
            norm_patch = re.sub(r'^re:\s*', '', norm_patch)
            norm_patch = re.sub(r'\[patch[^\]]*\]\s*', '', norm_patch)
            norm_patch = norm_patch.strip()
            email_ids = patch_subject_lookup.get(norm_patch, [])
            patch_links.append((patch_subject, email_ids))
        linked[email_id] = {
            'title': info['title'],
            'patch_links': patch_links
        }
    return linked

def link_git_pull_patches_to_threads_sql(organized_git_pulls):
    """
    For each GIT PULL email, link its patch subjects to patch email IDs using SQL.
    Returns a dict: {git_pull_id: {'title': ..., 'patch_links': [(patch_subject, [email_ids])]}}
    """
    linked = {}
    conn = get_connection()
    for email_id, info in organized_git_pulls.items():
        patch_links = []
        for patch_subject in info['patches']:
            email_ids = find_patch_email_ids_by_subject(conn, patch_subject)
            patch_links.append((patch_subject, email_ids))
        linked[email_id] = {
            'title': info['title'],
            'patch_links': patch_links
        }
    conn.close()
    return linked


def find_patch_email_ids_by_subject(conn, patch_subject):
    """
    Find patch email IDs where the title matches the given patch subject (case-insensitive).
    Returns a list of email IDs.
    """
    # Normalize subject for matching
    norm_subject = patch_subject.strip().lower()
    norm_subject = re.sub(r'^re:\s*', '', norm_subject)
    norm_subject = re.sub(r'\[patch[^\]]*\]\s*', '', norm_subject)
    norm_subject = norm_subject.strip()

    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM mails
        WHERE LOWER(title) LIKE ?
    """, (f"%{norm_subject}%",))
    results = [row[0] for row in cursor.fetchall()]
    return results


def extract_commit_hashes(body: str) -> List[str]:
    """
    Extract all 40-character commit hashes from a GIT PULL email body.
    """
    # SHA hashes are 40 hex digits
    if not body:
        print("Empty body, no commit hashes to extract.")
        return []
    return re.findall(r'\b[0-9a-f]{40}\b', body, re.IGNORECASE)



def find_patch_emails_by_commit_hash(conn, commit_hash: str) -> List[int]:
    """
    Find patch email IDs where the commit hash appears in the title or body.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM mails
        WHERE html_content LIKE ? OR title LIKE ?
    """, (f"%{commit_hash}%", f"%{commit_hash}%"))
    return [row[0] for row in cursor.fetchall()]


def get_github_commit_info(repo: str, commit_hash: str, github_token: str = None) -> dict:
    """
    Fetch commit info from GitHub for a given repo and commit hash.
    repo: 'owner/repo' (e.g., 'torvalds/linux')
    commit_hash: 40-character SHA-1 hash
    github_token: (optional) GitHub personal access token for higher rate limits

    Returns a dict with commit info, or None if not found.
    """
    url = f"https://api.github.com/repos/{repo}/commits/{commit_hash}"
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        return {
            "sha": data["sha"],
            "subject": data["commit"]["message"].splitlines()[0],
            "full_message": data["commit"]["message"],
            "author": data["commit"]["author"]["name"],
            "date": data["commit"]["author"]["date"],
            "files": [f["filename"] for f in data.get("files", [])],
            "diff": "\n\n".join(f.get("patch", "") for f in data.get("files", []) if "patch" in f),
            "url": data["html_url"]
        }
    else:
        print(f"Commit {commit_hash} not found in {repo} (status {resp.status_code})")
        return None



if __name__ == "__main__":
    organized = organize_git_pull_patches(limit=30) # adjust limit as needed, 30 is just for testing
    conn = get_connection()

    # for pull_id, info in organized.items():
    #     # html_content = info.get('html_content', '')
    #     # body = get_best_email_body(html_content)
    #     body = info.get('body', '')

    #     commit_hashes = extract_commit_hashes(body)
    #     if commit_hashes:
    #         print(f"\nGIT PULL Email {pull_id}: {info['title']}")
    #         print(f"  Found commit hashes: {commit_hashes}")
    #         for commit_hash in commit_hashes:
    #             patch_email_ids = find_patch_emails_by_commit_hash(conn, commit_hash)
    #             if patch_email_ids:
    #                 print(f"    Hash {commit_hash} found in patch emails: {patch_email_ids}")
    #             else:
    #                 print(f"    Hash {commit_hash} NOT found in any patch emails")
    # conn.close()


    linked_patches = link_git_pull_patches_to_threads_sql(organized)

    matched_count = 0
    unmatched_count = 0

    for pull_id, info in linked_patches.items():
        print(f"\nGIT PULL Email {pull_id}: {info['title']}")
        for patch_subject, email_ids in info['patch_links']:
            if email_ids:
                print(f"  Patch '{patch_subject}' found in patch emails: {email_ids}")
                matched_count += 1
            else:
                print(f"  Patch '{patch_subject}' NOT found in patch emails")
                unmatched_count += 1

    # Group unmatched patches by GIT PULL email
    # unmatched_by_email = {}
    # for pull_id, info in linked_patches.items():
    #     for patch_subject, email_ids in info['patch_links']:
    #         if not email_ids:
    #             if pull_id not in unmatched_by_email:
    #                 unmatched_by_email[pull_id] = {
    #                     "title": info['title'],
    #                     "patches": []
    #                 }
    #             unmatched_by_email[pull_id]["patches"].append(patch_subject)

    # # Write grouped report
    # with open("unmatched_patches.txt", "w", encoding="utf-8") as f:
    #     for pull_id, entry in unmatched_by_email.items():
    #         f.write(f"GIT PULL Email {pull_id}: {entry['title']}\n")
    #         for patch in entry["patches"]:
    #             f.write(f"  Unmatched Patch: {patch}\n")
    #         f.write("\n")

    # print(f"\nMatched patches: {matched_count}")
    # print(f"Unmatched patches: {unmatched_count}")
    # print(f"Logged {unmatched_count} unmatched patches to unmatched_patches.txt")


    # both matched and unmatched patches by email in the report instead of just unmatched
    report_by_email = {}
    for pull_id, info in linked_patches.items():
        if pull_id not in report_by_email:
            report_by_email[pull_id] = {
                "title": info['title'],
                "matched": [],
                "unmatched": []
            }
        for patch_subject, email_ids in info['patch_links']:
            if email_ids:
                report_by_email[pull_id]["matched"].append((patch_subject, email_ids))
            else:
                report_by_email[pull_id]["unmatched"].append(patch_subject)

    # Write report
    with open("patch_report.txt", "w", encoding="utf-8") as f:
        for pull_id, entry in report_by_email.items():
            f.write(f"GIT PULL Email {pull_id}: {entry['title']}\n")
            if entry["matched"]:
                f.write("  Matched patches:\n")
                for patch, ids in entry["matched"]:
                    f.write(f"    {patch} --> Patch Email IDs: {ids}\n")
            if entry["unmatched"]:
                f.write("  Unmatched patches:\n")
                for patch in entry["unmatched"]:
                    f.write(f"    {patch}\n")
            f.write("\n")


    # For each GIT PULL email, try to fetch commit info for unmatched patches
    repo = "torvalds/linux"
    github_token = None
    
    with open("unmatched_patch_commits.txt", "w", encoding="utf-8") as commit_log:
        for pull_id, entry in report_by_email.items():
            if entry["unmatched"]:
                commit_log.write(f"GIT PULL Email {pull_id}: {entry['title']}\n")
                body = organized[pull_id]['body']
                commit_hashes = extract_commit_hashes(body)
                for commit_hash in commit_hashes:
                    commit_info = get_github_commit_info(repo, commit_hash, github_token)
                    if commit_info:
                        commit_log.write(f"  Commit info for hash {commit_hash}:\n")
                        commit_log.write(f"    Subject: {commit_info['subject']}\n")
                        commit_log.write(f"    Author: {commit_info['author']}\n")
                        commit_log.write(f"    Date: {commit_info['date']}\n")
                        commit_log.write(f"    URL: {commit_info['url']}\n")
                        commit_log.write(f"    Files: {commit_info['files']}\n")
                        commit_log.write(f"    Message:\n{commit_info['full_message']}\n\n")
                commit_log.write("\n")



    # print the organized GIT PULL emails and their patch subjects
    # for email_id, info in organized.items():
    #     print(f"\nGIT PULL Email {email_id}: {info['title']}")
    #     if info['patches']:
    #         print("  Patch subjects:")
    #         for i, patch in enumerate(info['patches'], 1):
    #             print(f"    {i}. {patch}")
    #     else:
    #         print("  (No patch subjects found in this email)")



