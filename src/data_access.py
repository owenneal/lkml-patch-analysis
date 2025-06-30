"""
Database access functionality for LKML email analysis.

This module provides functions to connect to and query the SQLite database
containing LKML emails.
"""

import sqlite3
import re
from typing import List, Tuple
from collections import defaultdict

# database file path
DATABASE_FILE = 'lkml-patch-analysis/lkml-data-2024.db'

"""
    Get a connection to the SQLite database.
    
    Returns:
        SQLite connection object
"""
def get_connection():
    return sqlite3.connect(DATABASE_FILE)


"""
    Print database structure and sample data.

    Easier to read then using sqlite studio.
"""
def explore_database():
    conn = get_connection()
    
    # gets all the tables, only 2 but useful to see
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print("Tables in the database:")
    for table in tables:
        print(f"- {table[0]}")
    
    # show some sample data from each table
    for table in tables:
        table_name = table[0]
        print(f"\n--- Table: {table_name} ---")
        
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print("Columns:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
        sample_data = cursor.fetchall()
        print("Sample data:")
        for row in sample_data:
            print(f"  {row}")
    conn.close()


"""
    Get a sample of emails from the database.
    More than explore database, so just used to see what kind of content is in each email.
    
    Args:
        limit: Maximum number of emails to retrieve
    
    Returns:
        List of tuples containing (id, title, url, html_content)
"""
def get_sample_emails(limit: int = 10) -> List[Tuple]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url, html_content FROM mails LIMIT ?", (limit,))
    emails = cursor.fetchall()
    conn.close()
    return emails

"""
    Get patch-related emails from the database.
    Used to get emails that are related to patches, and eventually create a graph
    
    Args:
        limit: Maximum number of emails to retrieve
        
    Returns:
        List of tuples containing (id, title, url, html_content)
"""
def get_patch_emails(limit: int = 1000) -> List[Tuple]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, url, html_content FROM mails 
        WHERE title LIKE '%[PATCH%' OR title LIKE '%Re:%[PATCH%'
        ORDER BY id
        LIMIT ?
    """, (limit,))
    
    emails = cursor.fetchall()
    
    conn.close()
    return emails


"""
    Get patch-related emails from the database with pagination support.
    
    Args:
        limit: Maximum number of emails to retrieve
        offset: Number of emails to skip (for pagination)
        
    Returns:
        List of tuples containing (id, title, url, html_content)
"""
def get_patch_emails2(limit: int = 1000, offset: int = 0) -> List[Tuple]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, url, html_content FROM mails 
        WHERE title LIKE '%[PATCH%' OR title LIKE '%Re:%[PATCH%'
        ORDER BY id
        LIMIT ? OFFSET ?
    """, (limit, offset))
    
    emails = cursor.fetchall()
    conn.close()
    return emails

"""
    Get emails in batches that preserve complete discussion threads.
    Each batch contains complete conversation chains.
"""
def get_complete_thread_batches(batch_size: int = 1000) -> List[List[Tuple]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    # first, get ALL patch-related emails with their thread signatures
    cursor.execute("""
        SELECT id, title, url, html_content 
        FROM mails 
        WHERE title LIKE '%[PATCH%' OR title LIKE '%Re:%[PATCH%'
        ORDER BY id
    """)
    
    all_emails = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(all_emails)} total patch-related emails")
    
    # Group emails by thread signature to keep conversations together
    thread_groups = defaultdict(list)
    
    for email in all_emails:
        email_id, title, url, html_content = email
        
        # Extract thread signature (similar to your existing logic)
        thread_signature = extract_thread_signature(title)
        thread_groups[thread_signature].append(email)
    
    print(f"Found {len(thread_groups)} distinct conversation threads")
    
    # Create batches that keep complete threads together
    batches = []
    current_batch = []
    current_batch_size = 0
    
    for thread_signature, thread_emails in thread_groups.items():
        thread_size = len(thread_emails)
        
        # If adding this thread would exceed batch size, start new batch
        if current_batch_size + thread_size > batch_size and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_batch_size = 0
        
        # Add entire thread to current batch
        current_batch.extend(thread_emails)
        current_batch_size += thread_size
    
    # Add final batch if not empty
    if current_batch:
        batches.append(current_batch)
    
    print(f"Created {len(batches)} thread-aware batches")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}: {len(batch)} emails")
    
    return batches

"""
    Extract a signature that groups related emails in the same thread.
    This should be more aggressive than patch signature to capture discussions.
"""
def extract_thread_signature(title: str) -> str:


    if not title:
        return "unknown"
    
    # Remove common reply prefixes
    clean_title = title.lower()
    clean_title = re.sub(r'^re:\s*', '', clean_title)
    clean_title = re.sub(r'^fwd:\s*', '', clean_title)
    
    # Extract the core patch subject (remove version and series info for grouping)
    # [PATCH v2 3/5] driver: fix bug -> driver: fix bug
    patch_match = re.search(r'\[patch[^\]]*\]\s*(.+?)(?:\s*$)', clean_title)
    if patch_match:
        core_subject = patch_match.group(1).strip()
        # remove version indicators for grouping
        core_subject = re.sub(r'\s+v\d+\s*', ' ', core_subject)
        return core_subject.strip()
    
    # for non-patch emails, use the full subject
    return clean_title.strip()

"""
    General information about the database, such as total emails, ID range, 
    and counts of patch-related and reply emails.
"""
def analyze_database_coverage():

    conn = get_connection()
    cursor = conn.cursor()
    
    # get total  email count
    cursor.execute("SELECT COUNT(*) FROM mails")
    total_emails = cursor.fetchone()[0]
    
    # get email ID range
    cursor.execute("SELECT MIN(id), MAX(id) FROM mails")
    min_id, max_id = cursor.fetchone()
    
    print("=== DATABASE GENERAL ANALYSIS ===")
    print(f"Total emails in database: {total_emails:,}")
    print(f"Email ID range: {min_id} to {max_id}")
    
    # number of emails with patch-related titles
    cursor.execute("SELECT COUNT(*) FROM mails WHERE title LIKE '%[PATCH%'")
    patch_count = cursor.fetchone()[0]
    print(f"Patch emails: {patch_count:,} ({patch_count/total_emails*100:.2f}% of total)")
    
    # number of emails that are replies
    cursor.execute("SELECT COUNT(*) FROM mails WHERE title LIKE 'Re:%'")
    reply_count = cursor.fetchone()[0]
    print(f"Reply emails: {reply_count:,} ({reply_count/total_emails*100:.2f}% of total)")
    
    conn.close()


def create_git_pull_table():
    """
    Create a table to store git pull request information.
    This is useful for tracking pull requests related to patches.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS git_pull_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            html_content TEXT,
            pull_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print("Created git_pulls table if it did not exist.")


def populate_git_pull_table():
    conn = get_connection()
    cursor = conn.cursor()

    print("Populating git_pulls table with patch-related emails...")

    patterns = [
        ("LIKE '%[GIT PULL]%'", "GIT_PULL"),
        ("LIKE '%Re: [GIT PULL]%'", "GIT_PULL_REPLY")
    ]

    total_inserted = 0
    for pattern, pull_type in patterns:
        # first, check how many emails match this pattern, should be around 6500
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM mails 
            WHERE title {pattern}
            AND id NOT IN (SELECT id FROM git_pull_emails)
        """)
        count = cursor.fetchone()[0]
        print(f"  Found {count} emails matching '{pull_type}' pattern")

        if count > 0:
            # now we insert the emails into the git_pulls table
            cursor.execute(f"""
                INSERT INTO git_pull_emails (id, title, url, html_content, pull_type)
                SELECT id, title, url, html_content, '{pull_type}'
                FROM mails 
                WHERE title {pattern}
                AND id NOT IN (SELECT id FROM git_pull_emails WHERE id IS NOT NULL)
            """)
            inserted = cursor.rowcount
            total_inserted += inserted
            print(f"  Inserted {inserted} emails as '{pull_type}'")
    conn.commit()
    conn.close()


def get_git_pull_emails(limit: int = None) -> List[Tuple]:
    """
    Get only original GIT PULL emails (not replies) from the table.
    """
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT id, title, url, html_content, pull_type
        FROM git_pull_emails
        WHERE pull_type = 'GIT_PULL'
          AND LOWER(title) NOT LIKE 're: [git pull%'
        ORDER BY id DESC
    """
    if limit:
        query += f" LIMIT {limit}"
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results


def get_git_pull_statistics():
    """
    Get statistics about git pull request emails.
    
    Returns:
        Dictionary with counts of each pull type
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT pull_type, COUNT(*) 
        FROM git_pull_emails 
        GROUP BY pull_type
    """)
    
    stats = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return stats