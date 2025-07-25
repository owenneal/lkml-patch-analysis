import sqlite3
import argparse
from openai import OpenAI
from ..core.data_access import get_all_cve_ids, get_patch_emails_by_ids, get_cve_ids_by_category
from ..core.email_parser import parse_email_content


"""
This script categorizes Linux kernel patch threads based on their content using an LLM.
It retrieves patch emails for each CVE ID from a SQLite database, analyzes the content,
and updates the database with the determined category.

It requires the OpenAI Python client library and a local instance of the OpenAI API, but
could easily be adapted to use a different LLM or API.




The categories that the llm prompt can choose from are currently:
    - Memory Management (e.g., buffer overflow, use-after-free, memory leak)
    - Race Condition
    - Improper Input Validation
    - Logic Error / Incorrect Calculation
    - Security Feature Bypass
    - Resource Management (e.g., file descriptor leak, resource lock issue)
    - NULL Pointer Dereference
    - Other (please specify)

"""

SUSPECTED_CVE_DB = "suspected_cve_patches.db"
LKML_DATA_DB = "lkml-data-2024.db"
MAX_PROMPT_CHARS = 7000 #need to limit the char size for the llm context window of 4096 tokens

client = OpenAI(base_url="http://localhost:1234/v1", api_key="not-needed")

def add_category_column():
    """
    Add a 'category' column to the suspected_cve_patches table if it doesn't exist.
    """
    try:
        conn = sqlite3.connect(SUSPECTED_CVE_DB)
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE suspected_cve_patches ADD COLUMN category TEXT")
        print("Added 'category' column to suspected_cve_patches table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name: category" in str(e):
            print("Column 'category' already exists.")
        else:
            print(f"Error adding column: {e}")
    finally:
        if conn:
            conn.commit()
            conn.close()

def get_patch_details_for_cve(cve_id):
    """
    Get patch emails for a specific CVE ID from the suspected_cve_patches table.
    """
    try:
        conn = sqlite3.connect(SUSPECTED_CVE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT email_id FROM suspected_cve_patches WHERE match_cve_id = ?", (cve_id,))
        email_ids = [row[0] for row in cursor.fetchall()]
        full_emails = get_patch_emails_by_ids(email_ids)
        return full_emails
    except Exception as e:
        print(f"Error retrieving patch details for CVE {cve_id}: {e}")
    finally:
        if conn:
            conn.close()


def categorize_patch_thread(cve_id, patch_emails):
    """
    uses an llm to categorize a patch thread based on the emails in it.
    """
    thread_content = []
    for _, subject, _, html_content in patch_emails:
        parsed_content = parse_email_content(html_content)
        body = parsed_content.get("message_body", "")
        content = f"--- Email Subject: {subject} ---\n{body}\n"
        thread_content.append(content)
    full_thread_text = "\n".join(thread_content)


    if len(full_thread_text) > MAX_PROMPT_CHARS:
        print(f"Warning: Full thread content for CVE {cve_id} exceeds {MAX_PROMPT_CHARS} characters. Truncating.")
        full_thread_text = full_thread_text[:MAX_PROMPT_CHARS]

    prompt = f"""
    Analyze the following Linux kernel patch thread for vulnerability {cve_id}.
    The thread consists of one or more emails, including subjects and their text bodies.
    Based on the full context, what is the most likely category of the vulnerability being fixed?

    Full Patch Thread Content:
    {full_thread_text}

    Choose the most specific category possible from the list below. If a specific bug type fits, choose it. If not, choose the general high-level category.
    1. Memory Management Bugs
        - Buffer Overflow
        - Use-After-Free
        - Memory Leak
        - Out-of-Bounds Access
        - Double Free
        - Uninitialized Memory Use
        - Invalid Free / Corruption of Slab Metadata
    2. Race Conditions
        - TOCTOU (Time-Of-Check to Time-Of-Use)
        - Improper Locking or Missing Locking
        - Atomicity Violations
        - Deadlock / Livelock
    3. Improper Input Validation
        - User-Controlled Input Not Sanitized
        - Integer Overflow / Underflow
        - Signedness Bugs
        - Improper Bounds Checking
    4. Logic Errors / Incorrect Computation
        - Incorrect Conditionals
        - Off-by-One Errors
        - Miscalculated Buffer Sizes or Lengths
    5. Security Feature Bypass
        - Credential Leaks or Misuse
        - Incorrect Privilege Checks
        - Reference Counting Errors
    6. Resource Management Bugs
        - File Descriptor Leaks
        - Socket or Netlink Resource Leaks
        - Improper Lock Handling
        - Improper IRQ or Timer Resource Cleanup
        - Dangling Pointers After Resource Free
    7. NULL Pointer Dereference
        - Unchecked Pointer Returned by Allocator or Lookup
        - Dereference After Failure Path
    8. Initialization and Finalization Issues
        - Incorrect or Missed Initialization
        - Improper Cleanup in Error Paths
        - Mismatched Init/Exit in Loadable Kernel Modules
    9. API Misuse
        - Wrong API for Context
        - Violating Pre/Post-conditions of Kernel Interfaces
    10. Concurrency and Synchronization Bugs
        - Improper Use of Memory Barriers
        - Mishandled Interrupt Context vs. Process Context
        - Improper RCU (Read-Copy-Update) Usage
    11. Hardware Interaction Bugs
        - Faulty MMIO/PIO Access
        - Improper DMA Buffer Management
        - Incorrect Handling of Hardware Interrupts
    12. Error Code Handling
        - Error Propagation Failures
        - Swallowed Error Codes
    13. Other (please specify)

    Provide only the category name as your answer. Or if you have another category for it provide that instead.
    """

    try:
        completion = client.chat.completions.create(
            model="gemma-3-4b",
            messages=[
                {"role": "system", "content": "You are an expert Linux kernel security analyst that categorizes vulnerabilities based on patch content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        category = completion.choices[0].message.content.strip()
        return category
    except Exception as e:
        print(f"Error categorizing patch thread for CVE {cve_id}: {e}")
        return "Other"



def update_cve_category(cve_id, category):
    """
    Update the category of a specific CVE ID in the suspected_cve_patches table.
    """
    try:
        conn = sqlite3.connect(SUSPECTED_CVE_DB)
        cursor = conn.cursor()
        cursor.execute("UPDATE suspected_cve_patches SET category = ? WHERE match_cve_id = ?", (category, cve_id))
        print(f"Updated category for CVE {cve_id} to '{category}'.")
    except Exception as e:
        print(f"Error updating CVE category for {cve_id}: {e}")
    finally:
        if conn:
            conn.commit()
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Categorize CVE patch threads using an LLM.")
    parser.add_argument("--limit", type=int, help="Limit the number of CVEs to process.")
    parser.add_argument("--setup", action="store_true", help="Add the 'category' column to the database and exit.")
    parser.add_argument("--redo-other", action="store_true", help="Redo processing for CVEs with 'Other' category.")
    parser.add_argument("--start-after", type=str, help="The last successfully processed CVE ID to start processing after.")
    args = parser.parse_args()

    if args.setup:
        add_category_column()
        return

    if args.redo_other:
        cve_ids = get_cve_ids_by_category("Other")
    else:
        cve_ids = get_all_cve_ids() 

    if args.start_after:
        try:
            # Find the index of the CVE to start after
            start_index = cve_ids.index(args.start_after) + 1
            cve_ids = cve_ids[start_index:]
            print(f"Resuming process. Starting with CVE {cve_ids[0] if cve_ids else 'end of list'}.")
        except ValueError:
            print(f"Warning: CVE ID '{args.start_after}' not found. Starting from the beginning of the list.")

    if args.limit:
        cve_ids = cve_ids[:args.limit]
    print(f"Processing {len(cve_ids)} CVEs...")
    for cve_id in cve_ids:
        print(f"\nProcessing CVE {cve_id}...")
        patch_emails = get_patch_details_for_cve(cve_id)
        if not patch_emails:
            print(f"No patch emails found for {cve_id}. Skipping.")
            continue

        category = categorize_patch_thread(cve_id, patch_emails)
        if category:
            update_cve_category(cve_id, category)
        else:
            print(f"Failed to categorize CVE {cve_id}.")

if __name__ == "__main__":
    main()