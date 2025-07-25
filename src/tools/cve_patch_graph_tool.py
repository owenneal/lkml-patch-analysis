import argparse
import sqlite3
from ..core.data_access import get_patch_emails_by_ids, get_all_cve_ids
from ..core.email_parser import parse_email_content
from ..core.graph_builder import create_patch_evolution_graph_linux, create_in_reply_to_graph, create_patch_name_version_graph
from ..core.visualization import visualize_evolution_graph

SUSPECTED_CVE_DB = "suspected_cve_patches.db" # Path to the database file, will probably need to remove the lkml-patch-analysis/ part if you have the project in a folder titled lkml-patch-analysis


def export_email_bodies_by_subject(keyword, output_file="matched_email_bodies.txt", db_path="lkml-patch-analysis/lkml-data-2024.db"):
    """
    Export the body text of all emails with a subject containing the keyword to a text file.
    Each email is separated and includes its ID, subject, and URL.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, url, html_content
        FROM mails
        WHERE LOWER(title) LIKE ?
        ORDER BY id
    """, (f"%{keyword.lower()}%",))
    results = cursor.fetchall()
    conn.close()

    with open(output_file, "w", encoding="utf-8") as f:
        for eid, subject, url, html_content in results:
            body = parse_email_content(html_content).get("message_body", "")
            f.write(f"=== EMAIL ID: {eid} ===\n")
            f.write(f"Subject: {subject}\n")
            f.write(f"URL: {url}\n")
            f.write("Body:\n")
            f.write(body.strip() if body else "[No body found]")
            f.write("\n\n" + "="*60 + "\n\n")
    print(f"Exported {len(results)} emails to {output_file}")

def test_search_patch_subjects(keyword, db_path="lkml-patch-analysis/lkml-data-2024.db"):
    """
    Search the LKML database for emails whose subject contains the given keyword string.
    Prints all matching email IDs, subjects, and URLs.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, url
        FROM mails
        WHERE LOWER(title) LIKE ?
    """, (f"%{keyword.lower()}%",))
    results = cursor.fetchall()
    conn.close()
    print(f"Found {len(results)} emails with subject containing '{keyword}':")
    for eid, subject, url in results:
        print(f"Email ID: {eid}\nSubject: {subject}\nURL: {url}\n")

def get_patch_emails_for_cve(cve_id, db_path = SUSPECTED_CVE_DB):
    """
    Retrieve patch emails for a specific CVE ID from the database.
    """

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT email_id, subject, url
        FROM suspected_cve_patches
        WHERE match_cve_id = ?
    """, (cve_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_full_patch_emails(email_ids, limit = 10000):
    """
    Retrieve full patch emails for a list of email IDs from main lkml data database.
    """
    emails = get_patch_emails_by_ids(email_ids, limit)
    filtered = [e for e in emails if e[0] in email_ids]
    return filtered

def print_all_cve_ids(db_path = SUSPECTED_CVE_DB):
    """
    print out all of the cve ids available from the suspected cve patches table
    """
    ids = get_all_cve_ids(db_path)
    print(f"Found {len(ids)} unique CVE IDs")
    for id in ids:
        print(id)


def main():
    #test_search_patch_subjects("xen/events: close evtchn after mapping cleanup")
    #export_email_bodies_by_subject("xen/events: close evtchn after mapping cleanup", "xen_evtchn_email_bodies.txt")
    parser = argparse.ArgumentParser(description="Query and visualize patch emails for a given CVE ID.")
    parser.add_argument("cve_id", nargs="?", help="CVE ID to query (e.g., CVE-2024-26687)")
    parser.add_argument("--list-cves", action="store_true",  help="Print all unique CVE IDs found in the database")
    parser.add_argument("--graph", action="store_true", help="Create and visualize the evolution graph for the CVE patch email thread")
    parser.add_argument("--limit", type=int, default=10000, help="Limit the number of emails to retrieve (default: 10000)")
    args = parser.parse_args()


    if args.list_cves:
        print_all_cve_ids()
        return
    
    if not args.cve_id:
        print("No cve id provided. Use --list-cves to see all available options and then specify a cve id.")
        return

    print(f"Retrieving patch emails for {args.cve_id}...")
    patch_refs = get_patch_emails_for_cve(args.cve_id)
    if not patch_refs:
        print(f"No patch emails found for {args.cve_id}.")
        return
    
    print(f"Found {len(patch_refs)} patch emails for {args.cve_id}.")
    for eid, subject, url in patch_refs:
        print(f"Email ID: {eid}, Subject: {subject}, URL: {url}")

    if args.graph:
        print("Creating patch email graph...")
        email_ids = [eid for eid, _, _ in patch_refs]
        patch_emails = get_full_patch_emails(email_ids, args.limit)
        if not patch_emails:
            print("No full patch emails found for the specified IDs.")
            return
        #graph, email_data = create_patch_evolution_graph_linux(patch_emails)
        #graph, email_data = creae_in_reply_to_graph(patch_emails)
        graph, email_data = create_patch_name_version_graph(patch_emails) #so far best working
        output_file = f"patch_evolution_graph_{args.cve_id.replace('-', '_')}.html"
        visualize_evolution_graph(graph, email_data, component_limit=10, max_nodes=200, output_file=output_file)  # Adjust component_limit and max_nodes as needed

        print("Graph visualization complete. Check the output files for details.")

if __name__ == "__main__":
    main()
 