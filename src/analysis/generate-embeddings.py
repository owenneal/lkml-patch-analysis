import sqlite3
import argparse
import pickle
import pandas as pd
import networkx as nx
from sentence_transformers import SentenceTransformer
from ..core.data_access import get_patch_emails_by_ids
from ..core.email_parser import parse_email_content
from ..core.graph_builder import create_patch_evolution_graph_linux

SUSPECTED_CVE_DB = 'suspected_cve_patches.db'
COMMIT_REPORT_CSV = "final_cve_analysis_report_20250722_cleaned.csv" # use the latest cleaned report
EMBEDDINGS_OUTPUT_FILE = "cve_embeddings.pkl"


def get_full_thread_text_for_cve(cve_id: str) -> str:
    """
    Retrieve the full text of the email thread for a given CVE ID.
    """
    conn = sqlite3.connect(SUSPECTED_CVE_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT email_id FROM suspected_cve_patches WHERE match_cve_id = ?", (cve_id,))
    email_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    if not email_ids:
        return ""

    patch_emails = get_patch_emails_by_ids(list(email_ids))
    G, email_data = create_patch_evolution_graph_linux(patch_emails)
    try:
        sorted_nodes = list(nx.topological_sort(G))
    except nx.NetworkXUnfeasible:
        print(f"  - Warning: Cycle detected in graph for {cve_id}. Falling back to chronological sort.")
        sorted_nodes = sorted(G.nodes(), key=lambda nid: G.nodes[nid].get('chronological_order', 0))

    thread_content = []
    for node_id in sorted_nodes:
        parsed_content = email_data.get(node_id, {})
        subject = parsed_content.get('subject', 'No Subject')
        body = parsed_content.get('message_body', '').strip()
        if body:
            thread_content.append(f"Subject: {subject}\n\n{body}")

    return "\n\n--- NEXT EMAIL IN THREAD ---\n\n".join(thread_content)



def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for CVE patch threads.")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of CVEs to process (0 for all).")
    args = parser.parse_args()

    model = SentenceTransformer('all-MiniLM-L6-v2')
    try:
        df = pd.read_csv(COMMIT_REPORT_CSV)
        cve_ids = df['CVE_ID'].unique().tolist()
    except FileNotFoundError:
        print(f"Error: The file {COMMIT_REPORT_CSV} does not exist.")
        return
    
    if args.limit > 0:
        cve_ids = cve_ids[:args.limit]

    embeddings = {}
    for i, cve_id in enumerate(cve_ids):
        print(f"Processing CVE {i + 1}/{len(cve_ids)}: {cve_id}")
        full_text = get_full_thread_text_for_cve(cve_id)
        if not full_text:
            print(f"No emails found for CVE {cve_id}. Skipping.")
            continue

        vector = model.encode(full_text, convert_to_tensor=False)
        embeddings[cve_id] = vector

    print(f"Generated embeddings for {len(embeddings)} CVEs.")
    with open(EMBEDDINGS_OUTPUT_FILE, 'wb') as f:
        pickle.dump(embeddings, f)

    print(f"Embeddings saved to {EMBEDDINGS_OUTPUT_FILE}")

if __name__ == "__main__":
    main()

    
    