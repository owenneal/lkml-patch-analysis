"""
Email parsing functionality for LKML emails.

This module contains functions to parse HTML email content and extract
structured information such as metadata, patch information, and thread relationships.
"""

import re
from typing import Dict, Optional, Set, List
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import sqlite3
from utils import get_best_email_body

_maintainer_emails_cache = None



'''
Load maintainer emails from the database.
This function connects to the SQLite database and retrieves all maintainer emails,
caching the results for future calls to improve performance.
'''
def load_maintainer_emails() -> Set[str]:
    global _maintainer_emails_cache
    if _maintainer_emails_cache is not None:
        return _maintainer_emails_cache
    
    maintainer_emails = set()
    try:
        conn = sqlite3.connect('maintainers.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM maintainers")
        rows = cursor.fetchall()

        for row in rows:
            maintainer_emails.add(row[0].strip().lower())

        conn.close()
        print(f"Loaded {len(maintainer_emails)} maintainer emails from database.")

    except sqlite3.Error as e:
        print(f"Error loading maintainers from database: {e}")
        maintainer_emails = set()

    _maintainer_emails_cache = maintainer_emails
    return maintainer_emails


def is_maintainer_email(email: str) -> bool:
    if not email:
        return False
    
    maintainer_emails = load_maintainer_emails()
    email_match = re.search(r'<([^>]+)>', email)
    if email_match:
        email = email_match.group(1) #extract the email address from angle brackets

    return email.strip().lower() in maintainer_emails



'''
Extract maintainer signals from email content.
This function scans the email content for maintainer signatures such as
"Reviewed-by", "Acked-by", "Tested-by", and "Signed-off-by".
It checks if the email address in the signature matches any known maintainer emails
and returns a list of signals indicating the type of maintainer action.
'''
def extract_maintainer_signals_from_content(content: str) -> List[str]:
    signals = []
    maintainer_emails = load_maintainer_emails()

    maintainer_signature_patterns = [
        r'reviewed-by:\s*([^<]*<[^>]+>)',
        r'acked-by:\s*([^<]*<[^>]+>)', 
        r'tested-by:\s*([^<]*<[^>]+>)',
        r'signed-off-by:\s*([^<]*<[^>]+>)'
    ]

    for pattern in maintainer_signature_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            signature_line = match.group(1)
            email_match = re.search(r'<([^>]+)>', signature_line)
            if email_match and email_match.group(1).lower().strip() in maintainer_emails:
                signal_type = pattern.split(':')[0].replace('\\s*', '').replace('r', 'R')
                signals.append(f'maintainer_{signal_type.lower().replace("-", "_")}')
    
    return signals



"""
    Extract indicators that suggest a patch is being merged or accepted.
    Use subject and content to identify merge signals. And assign confidence scores
    based on the strength of the signals detected.


    subject: Email subject line
    content: Email message body
    Returns:
        Dictionary with merge indicators:
            - is_merge_candidate: Boolean indicating if this is a merge candidate
            - merge_signals: List of detected merge signals
            - confidence_score: Float indicating confidence level of merge detection
"""
def extract_merge_indicators(subject: str, content: str, from_author: str = "") -> Dict:
    """
    Extract indicators that suggest a patch is being merged or accepted.
    Enhanced with maintainer database lookup.
    """
    merge_indicators = {
        'is_merge_candidate': False,
        'merge_signals': [],
        'confidence_score': 0.0
    }
    
    subject_lower = subject.lower() if subject else ''
    content_lower = content.lower() if content else ''
    
    # check if sender is a maintainer
    is_from_maintainer = is_maintainer_email(from_author)
    
    # very strong signals - definitive merge indicators
    very_strong_signals = [
        'applied, thanks',     # Common maintainer response
        'thanks, applied',     # Common maintainer response
        #'queued for',          # "queued for next release"
        'will be merged',      # Explicit merge statement
    ]
    
    # medium signals - but get boosted if from maintainer
    maintainer_boosted_signals = [
        'looks good', 'lgtm', 'nice work', 'thanks for'
    ]
    
    # check very strong signals (anyone can indicate these)
    for signal in very_strong_signals:
        if signal in content_lower or signal in subject_lower:
            merge_indicators['merge_signals'].append(signal)
            merge_indicators['confidence_score'] += 5.0
    
    # check for maintainer-specific signals in content
    maintainer_signals = extract_maintainer_signals_from_content(content)
    for signal in maintainer_signals:
        merge_indicators['merge_signals'].append(signal)
        merge_indicators['confidence_score'] += 4.0  # High confidence for maintainer signals
    
    # check regular signals, but boost if from maintainer
    regular_signals = ['acked-by:', 'reviewed-by:', 'tested-by:']
    for signal in regular_signals:
        if signal in content_lower:
            if is_from_maintainer:
                merge_indicators['merge_signals'].append(f'maintainer_{signal.replace(":", "").replace("-", "_")}')
                merge_indicators['confidence_score'] += 4.0
            else:
                merge_indicators['merge_signals'].append(signal)
                merge_indicators['confidence_score'] += 1.5  # Lower confidence for non-maintainers
    
    # Medium signals get boosted if from maintainer
    for signal in maintainer_boosted_signals:
        if signal in content_lower:
            boost = 3.0 if is_from_maintainer else 1.0
            merge_indicators['merge_signals'].append(signal)
            merge_indicators['confidence_score'] += boost
    
    # Special boost for maintainer responses
    if is_from_maintainer and merge_indicators['merge_signals']:
        merge_indicators['confidence_score'] += 2.0
        merge_indicators['merge_signals'].append('from_maintainer')
    
    merge_indicators['is_merge_candidate'] = merge_indicators['confidence_score'] >= 4.0
    return merge_indicators



def extract_merge_indicators2(subject: str, content: str, from_author: str = "") -> dict:
    """
    Extract more precise merge indicators that actually suggest acceptance.
    """
    merge_indicators = {
        'is_merge_candidate': False,
        'merge_signals': [],
        'confidence_score': 0.0
    }

    subject_lower = subject.lower() if subject else ''
    content_lower = content.lower() if content else ''
    from_author_lower = from_author.lower() if from_author else ''

    # Strong signals (very likely merged indicators)
    strong_signals = [
        'applied to', 'queued to', 'merged to', 'committed to', 'added to',
        'picked up', 'in linux-next', 'pulled into', 'landed in', 'committed as',
        'pushed to', 'will appear in', 'applied, thanks'
    ]
    
    # Medium signals (acceptance indicators, but not definitive)
    medium_signals = [
        'looks good', 'lgtm', 'acked-by:', 'tested-by:'
    ]
    
    # Weak signals (only count if from maintainer or in specific context)
    weak_signals = [
        'reviewed-by:', 'signed-off-by:'
    ]

    # Check strong signals
    for signal in strong_signals:
        if signal in content_lower:
            merge_indicators['merge_signals'].append(signal)
            merge_indicators['confidence_score'] += 4.0

    # Check medium signals
    for signal in medium_signals:
        if signal in content_lower:
            merge_indicators['merge_signals'].append(signal)
            merge_indicators['confidence_score'] += 2.0

    # Check weak signals - only count if from known maintainer or specific context
    known_maintainers = ['torvalds', 'gregkh', 'davem', 'akpm', 'sashal', 'jikos']
    is_from_maintainer = any(maintainer in from_author_lower for maintainer in known_maintainers)
    
    for signal in weak_signals:
        if signal in content_lower:
            # Only count if from maintainer or in reply context
            if is_from_maintainer or 'thanks' in content_lower or 'applied' in content_lower:
                merge_indicators['merge_signals'].append(signal)
                merge_indicators['confidence_score'] += 1.0

    # Boost confidence if multiple signals present
    if len(merge_indicators['merge_signals']) > 2:
        merge_indicators['confidence_score'] += 1.0

    merge_indicators['is_merge_candidate'] = merge_indicators['confidence_score'] >= 3.0
    return merge_indicators


def check_maintainer_context(subject: str, content: str) -> float:
    """
    Check if the email is from a maintainer or mentions maintainer actions.
    """
    score = 0.0
    
    # Common maintainer email patterns
    maintainer_patterns = [
        'maintainer',
        'subsystem.*maintainer',
        'tree.*maintainer', 
        'from.*maintainer',
        'by.*maintainer'
    ]
    
    
    for pattern in maintainer_patterns:
        if re.search(pattern, content):
            score += 1.0
            break
    
    # Check for official actions
    official_actions = [
        'pulling.*into',
        'merging.*into', 
        'taking.*patch',
        'will.*apply',
        'going.*upstream'
    ]
    
    for pattern in official_actions:
        if re.search(pattern, content):
            score += 1.5
            break
    
    return score

def check_official_tree_mentions(content: str) -> float:
    """
    Check for mentions of official kernel trees.
    """
    score = 0.0
    
    official_trees = [
        'linux-next',
        'mainline',
        'linus.*tree',
        'stable.*tree',
        'maintainer.*tree',
        'upstream',
        'git\.kernel\.org'
    ]
    
    for tree in official_trees:
        if re.search(tree, content):
            score += 0.5
            break
    
    return score


def parse_email_content(html_content: str) -> Dict:

    soup = BeautifulSoup(html_content, 'html.parser') # html parser for the email content

    # initialize the email data structure
    # with default values
    email_data = {
        'from_author': None,
        'date': None,
        'subject': None,
        'message_body': None,
        'message_id': None,  # not extracted here, but can be added if needed
        'in_reply_to': None,
        'thread_messages': [],
        'patch_info': None,
        'merge_info': None
    }


    # Extract metadata from tables
    # LKML emails store the metadata in HTML tables
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr') # find all rows in the table
        for row in rows:
            cells = row.find_all('td') # find all cells in the row
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                
                # store html metadata based on label
                if label.lower() == 'message-id':
                    email_data['message_id'] = value
                elif label.lower() == 'in-reply-to':
                    email_data['in_reply_to'] = value
                elif label == 'From': 
                    email_data['from_author'] = value
                elif label == 'Date':
                    email_data['date'] = value
                elif label == 'Subject':
                    email_data['subject'] = value
    
    # Extract message body
    # LKML emails have the main content in a <pre> tag with itemprop="articleBody"
    pre_tag = soup.find('pre', {'itemprop': 'articleBody'})
    if pre_tag:
        email_data['message_body'] = pre_tag.get_text()

    plain_text_body = get_best_email_body(email_data['message_body'] or "")
    email_data['message_body'] = plain_text_body if plain_text_body else email_data['message_body']

    
    # Extract thread information
    # stored in an unordered list with class 'threadlist'
    # gets all links to related emails in the thread
    thread_list = soup.find('ul', class_='threadlist')
    if thread_list:
        thread_links = thread_list.find_all('a')
        for link in thread_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if href.startswith('/lkml/'):
                email_data['thread_messages'].append({
                    'url': href,
                    'text': text
                })
    
    # Check if this is a patch
    if email_data['subject']:
        email_data['patch_info'] = extract_patch_info(email_data['subject'])


    # try to find merge indicators
    # in the subject and message body
    merge_information = extract_merge_indicators(
        email_data['subject'], 
        email_data['message_body'] or ''
    )

    email_data['merge_info'] = merge_information
    
    return email_data


def extract_patch_info(subject: str) -> Optional[Dict]:
    """
    Extract patch information from email subject.
    
    Args:
        subject: Email subject line
        
    Returns:
        Dictionary with patch metadata or None if not a patch
    """

    # Regex patterns to match different patch subject formats
    # \[PATCH\s* - Literal "[PATCH" followed by optional whitespace
    # ([v\d+]*) - Capture group for version (v1, v2, etc.) - optional
    # \s*(\d+/\d+)? - Optional series info like "3/5" 
    # \s*\] - Closing bracket with optional whitespace
    # \s*(.*) - Capture the rest as patch title

    patch_patterns = [
        r'\[PATCH\s*([v\d+]*)\s*(\d+/\d+)?\s*\]\s*(.*)',
        r'\[RFC\s*PATCH\s*([v\d+]*)\s*(\d+/\d+)?\s*\]\s*(.*)',
        r'Re:\s*\[PATCH\s*([v\d+]*)\s*(\d+/\d+)?\s*\]\s*(.*)'
    ]
    
    for pattern in patch_patterns:
        match = re.match(pattern, subject, re.IGNORECASE)
        if match:
            version = match.group(1) if match.group(1) else 'v1' 
            series = match.group(2) if match.group(2) else None # e.g. "3/5" series info
            title = match.group(3) if match.group(3) else '' # patch title
            
            return {
                'is_patch': True,
                'version': version,
                'series_info': series,
                'patch_title': title.strip(),
                'is_reply': subject.strip().lower().startswith('re:')
            }
    
    return None


def extract_patch_signature_improved(subject: str) -> Optional[str]:
    """
    Extract a normalized patch signature for grouping related patches.
    
    Args:
        subject: Email subject line
        
    Returns:
        Normalized signature for grouping or None if invalid
    """

    if not subject:
        return None
    subject = subject.strip()

    while subject.lower().startswith('re:'):
        subject = subject[3:].strip()
    patch_patterns = [
        r'\[PATCH\s*(?:v\d+)?\s*(?:\d+/\d+)?\s*\]\s*(.*)',
        r'\[RFC\s*PATCH\s*(?:v\d+)?\s*(?:\d+/\d+)?\s*\]\s*(.*)',
        r'\[.*?PATCH.*?\]\s*(.*)',
    ]
    
    for pattern in patch_patterns:
        match = re.match(pattern, subject, re.IGNORECASE)
        if match:
            core_title = match.group(1).strip()
            normalized = normalize_title(core_title)
            return normalized if normalized else None
    
    normalized = normalize_title(subject)
    return normalized if normalized else None


def normalize_title(title: str) -> str:
    """
    Normalize a title for better matching.
    
    Args:
        title: Raw title text
        
    Returns:
        Normalized title
    """

    if not title:
        return ""
    title = title.lower().strip()
    title = re.sub(r'[.!?]+$', '', title)
    title = re.sub(r'\s+', ' ', title) # \s+ means one or more whitespace characters
    title = re.sub(r'\s*:\s*', ': ', title)
    return title.strip()


def parse_email_date(date_str):
    """
    Parse email date string into datetime object.
    
    Args:
        date_str: Date string from email
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # LKML dates are usually in format like "Tue, 28 Feb 2024 10:30:45 +0000"
        parsed_date = date_parser.parse(date_str)
        return parsed_date
    except Exception as e:
        # If parsing fails, return None
        # prevents crashes on invalid date formats
        print(f"Failed to parse date: {date_str} - {e}")
        return None


def extract_series_position(series_info):
    """
    Extract numeric position from series info.

    Extracts the current position and total number of patches in a series
    for better grouping and sorting of patch emails.
    
    Args:
        series_info: String like '4/7'
        
    Returns:
        Tuple of (position, total) or (0, 0) if invalid
    """

    if not series_info:
        return (0, 0)
    
    # Match pattern like "4/7" or "2/5"
    # using regex to extract current and total
    # parentheses are used to capture groups
    match = re.match(r'(\d+)/(\d+)', series_info)
    if match:
        current = int(match.group(1)) # first number is the current patch
        total = int(match.group(2)) # total patches in the series
        return (current, total)
    
    return (0, 0)


def extract_temporal_info(email_data, email_id):
    """
    Extract improved temporal information for chronological ordering.
    
    Args:
        email_data: Dictionary of email data
        email_id: Email ID
        
    Returns:
        Tuple of (chronological_order, version_num, series_position, series_total, parsed_date)
    """

    email = email_data.get(email_id, {})
    
    # parse the actual date for chronological ordering
    date_str = email.get('date', '')
    parsed_date = parse_email_date(date_str)
    
    # Use parsed date timestamp if available, otherwise fall back to email ID
    if parsed_date:
        chronological_order = parsed_date.timestamp()
    else:
        chronological_order = email_id  # Fallback
    
    # Extract patch version and series information
    patch_info = email.get('patch_info')
    if patch_info:
        version = patch_info.get('version', 'v1')
        # Convert version to numeric for sorting (v1=1, v2=2, etc.)
        version_num = int(re.search(r'\d+', version).group()) if re.search(r'\d+', version) else 1
        
        series_info = patch_info.get('series_info', '')
        series_position, series_total = extract_series_position(series_info)
        
        return chronological_order, version_num, series_position, series_total, parsed_date
    
    return chronological_order, 0, 0, 0, parsed_date


def find_git_pull_emails(email_data: dict) -> dict:
    """
    Find emails that contain [GIT PULL] requests with enhanced debugging.
    """
    git_pull_emails = {}
    total_emails = len(email_data)
    subjects_checked = 0
    pattern_matches = {pattern: 0 for pattern in ['[git pull]', 'git pull', 'please pull', 'pull request']}
    
    print(f"Searching for git pull emails in {total_emails} emails...")

    for email_id, email in email_data.items():
        subject = email.get('subject', '')
        if not subject:
            continue
            
        subjects_checked += 1
        subject_lower = subject.lower()
        
        # Print first few subjects for debugging
        if subjects_checked <= 10:  # Increased to see more samples
            print(f"Sample subject {subjects_checked}: {subject}")
        
        # Check for git pull patterns
        git_pull_patterns = [
            '[git pull]',
            'git pull', 
            'please pull',
            'pull request'
        ]

        found_match = False
        for pattern in git_pull_patterns:
            if pattern in subject_lower:
                print(f"✓ Found git pull email {email_id}: {subject}")
                print(f"  Matched pattern: '{pattern}'")
                pattern_matches[pattern] += 1
                
                body = email.get('message_body', '') or email.get('body_text', '')
                git_pull_emails[email_id] = {
                    'subject': subject,
                    'body': body
                }
                found_match = True
                break
        
        # Debug: Check for potential near-misses
        if not found_match and 'git' in subject_lower:
            print(f"  Near miss - contains 'git': {subject}")
    
    print(f"Checked {subjects_checked} email subjects")
    print(f"Pattern matches: {pattern_matches}")
    print(f"Found {len(git_pull_emails)} git pull emails")
    return git_pull_emails


def find_git_pull_emails_regex(email_data: dict) -> dict:
    """
    Find [GIT PULL] emails using regex patterns similar to patch detection.
    """
    git_pull_emails = {}
    total_emails = len(email_data)
    subjects_checked = 0
    
    print(f"Searching for [GIT PULL] emails in {total_emails} emails using regex...")
    
    # Regex patterns for git pull emails (similar to patch patterns)
    git_pull_patterns = [
        r'\[GIT\s+PULL\]',           # [GIT PULL] - most common
        r'\[git\s+pull\]',           # [git pull] - lowercase variant
        r'\[Git\s+Pull\]',           # [Git Pull] - title case
        r'Re:\s*\[GIT\s+PULL\]',     # Re: [GIT PULL] - replies
        r'Re:\s*\[git\s+pull\]',     # Re: [git pull] - lowercase replies
    ]
    
    for email_id, email in email_data.items():
        subject = email.get('subject', '')
        if not subject:
            continue
            
        subjects_checked += 1
        
        # Print first few subjects for debugging
        if subjects_checked <= 5:
            print(f"Sample subject {subjects_checked}: {subject}")
        
        # Check each regex pattern
        found_match = False
        for pattern in git_pull_patterns:
            if re.search(pattern, subject, re.IGNORECASE):
                print(f"✓ Found [GIT PULL] email {email_id}: {subject}")
                print(f"  Matched pattern: '{pattern}'")
                
                body = email.get('message_body', '') or email.get('body_text', '')
                git_pull_emails[email_id] = {
                    'subject': subject,
                    'body': body
                }
                found_match = True
                break
        
        # Also check for other git pull variants
        if not found_match:
            other_patterns = [
                r'please\s+pull',
                r'git\s+tree',
                r'pull\s+from',
                r'tree\s+pull'
            ]
            
            for pattern in other_patterns:
                if re.search(pattern, subject, re.IGNORECASE):
                    print(f"✓ Found git pull variant {email_id}: {subject}")
                    print(f"  Matched variant pattern: '{pattern}'")
                    
                    body = email.get('message_body', '') or email.get('body_text', '')
                    git_pull_emails[email_id] = {
                        'subject': subject,
                        'body': body
                    }
                    found_match = True
                    break
    
    print(f"Checked {subjects_checked} email subjects")
    print(f"Found {len(git_pull_emails)} [GIT PULL] emails")
    
    # Show some examples
    if git_pull_emails:
        print(f"\nFirst few [GIT PULL] emails found:")
        for i, (email_id, info) in enumerate(list(git_pull_emails.items())[:5]):
            print(f"  {i+1}. {email_id}: {info['subject']}")
    
    return git_pull_emails


def check_git_pull_in_database():
    """
    Check what git pull emails are actually in the database.
    """
    from data_access import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check for different git pull patterns in database
    patterns = [
        "LIKE '%[GIT PULL]%'",
        "LIKE '%[git pull]%'", 
        "LIKE '%GIT PULL%'",
        "LIKE '%git pull%'",
        "LIKE '%please pull%'",
        "LIKE '%PULL REQUEST%'",
        "LIKE '%pull request%'"
    ]
    
    print("Checking database for git pull patterns:")
    total_found = 0
    
    for pattern in patterns:
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM mails 
            WHERE title {pattern}
        """)
        count = cursor.fetchone()[0]
        print(f"  {pattern}: {count} emails")
        total_found += count
        
        # Show examples for non-zero counts
        if count > 0 and count <= 10:
            cursor.execute(f"""
                SELECT id, title 
                FROM mails 
                WHERE title {pattern}
                LIMIT 5
            """)
            examples = cursor.fetchall()
            for email_id, title in examples:
                print(f"    Example: {email_id}: {title}")
    
    print(f"Total git pull related emails: {total_found}")
    conn.close()


def parse_patch_names_from_git_pull(body: str) -> List[str]:
    """
    Parse patch names from a git pull request body.
    
    Args:
        body: Body text of the git pull request
        
    Returns:
        List of patch names extracted from the body
    """
    patch_names = []
    
    in_commit_section = False
    for line in body.splitlines():
        line = line.strip()
        
        if re.match(r'^-+$', line.strip()):
            in_commit_section = not in_commit_section
            continue

        if in_commit_section:
            if re.match(r'^\s{4,}[\w/:\- ]+', line):
                patch_names.append(line.strip())
            # Or lines like: "Author Name (N):" or "Author Name <email>:" (skip)
            elif re.match(r'^[\w .\-()]+<.*>:', line):
                continue
            # Or lines like: "    - fix ..." (for shortlog)
            elif re.match(r'^\s*-\s+.+', line):
                patch_names.append(line.strip('- ').strip())

    return patch_names

def link_patch_names_to_emails(patch_names: List[str], email_data: dict) -> dict:
    """
    Link patch names to their corresponding email IDs.
    
    Args:
        patch_names: List of patch names
        email_data: Dictionary of email data
        
    Returns:
        Dictionary mapping patch names to email IDs
    """
    patch_links = {}
    for patch_name in patch_names:
        patch_links[patch_name] = []
        for email_id, email in email_data.items():
            subject = email.get('subject', '').lower()
            if patch_name.lower().split(':')[0] in subject:
                patch_links[patch_name].append(email_id)
    return patch_links

def find_and_map_git_pull_patches(email_data: dict) -> dict:
    """
    Find git pull emails and map patches to them.
    
    Args:
        email_data: Dictionary of email data
    Returns:
        Dictionary with git pull emails and their patches

    """

    git_pull_emails = find_git_pull_emails(email_data)
    res = {}
    for email_id, info in git_pull_emails.items():
        patch_names = parse_patch_names_from_git_pull(info['body'])
        linked_emails = link_patch_names_to_emails(patch_names, email_data)
        res[email_id] = {
            'patch_names': patch_names,
            'linked_emails': linked_emails,
        }
    return res

