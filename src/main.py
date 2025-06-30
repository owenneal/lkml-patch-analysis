"""
LKML Email Graph Analysis Tool

This script analyzes Linux Kernel Mailing List (LKML) emails stored in an SQLite database
and creates a graph representation showing relationships between emails, particularly 
focusing on patch series and discussion threads.

Usage:
    python main.py [--analyze-only] [--sample-size SIZE]

Key Features:
- Parses HTML email content to extract metadata and relationships
- Groups related emails (patch versions, discussion threads)
- Creates a graph database using NetworkX
- Provides interactive visualization using Pyvis
"""

import argparse
import networkx as nx
from typing import Dict

from data_access import get_patch_emails, analyze_database_coverage, get_patch_emails2
from graph_builder import create_evolution_graph, analyze_graph_components, create_evolution_graph2
from visualization import visualize_evolution_graph
from batch_processor import create_batch_processor
from case_study import analyze_patch_merge_status, generate_case_study_report, verify_merge_indicators
from email_parser import find_and_map_git_pull_patches, find_git_pull_emails_regex, check_git_pull_in_database
try:
    from neo4j_export import export_connected_subgraph_to_neo4j, test_connectivity_queries
    NEO4J_READY = True
except ImportError:
    print("Neo4j not available, skipping Neo4j export features.")
    NEO4J_READY = False

"""
    Parse command-line arguments
    easier to use than hardcoding values or using a switch statement.
"""
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="LKML Email Graph Analysis Tool"
    )

    parser.add_argument("--setup-git-pull-table", action="store_true",
                        help="Set up git pull table in the database")
    
    parser.add_argument("--analyze-only", action="store_true",
                       help="Only analyze data, don't create visualizations")
    
    parser.add_argument("--sample-size", type=int, default=1000,
                       help="Number of emails to process (default: 1000)")
    
    # Neo4j export options
    parser.add_argument("--export-neo4j", action="store_true",
                       help="Export graph to Neo4j database")
    
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687",
                       help="Neo4j connection URI")
    
    parser.add_argument("--neo4j-user", default="neo4j",
                       help="Neo4j username")
    
    parser.add_argument("--neo4j-password", default="2025internshiplkml",
                       help="Neo4j password")
    
    # batch processing
    parser.add_argument("--full-scale", action="store_true",
                       help="Process all emails using thread-aware batching")
    
    parser.add_argument("--batch-size", type=int, default=5000,
                       help="Target emails per batch (default: 5000)")
    

    # case study options
    parser.add_argument("--case-study", action="store_true",
                       help="Generate case study report for patch merging status")
    
    parser.add_argument("--text-report", action="store_true",
                        help="Generate text report for case study")
    
    parser.add_argument("--report-file", type=str, default="merge_indicators_report.txt",
                       help="Output file for text report (default: merge_indicators_report.txt)")
    
    return parser.parse_args()



"""Debug function to examine relationship quality"""
def debug_relationships(G: nx.DiGraph, email_data: Dict, limit: int = 5) -> None:
    
    
    print("\n=== RELATIONSHIP DEBUGGING ===")
    
    # check for any patch evolution chains v1-v2
    evolution_edges = [(u, v) for u, v, d in G.edges(data=True) 
                      if d.get('evolution_type') == 'version_upgrade']
    
    print(f"\n--- Version Evolution Examples ({len(evolution_edges)} total) ---")
    for i, (source, target) in enumerate(evolution_edges[:limit]):
        source_data = email_data.get(source, {})
        target_data = email_data.get(target, {})
        
        print(f"Evolution {i+1}:")
        print(f"  From: {source} - {source_data.get('subject', 'Unknown')[:50]}...")
        print(f"  To:   {target} - {target_data.get('subject', 'Unknown')[:50]}...")
        print(f"  Version: {G.nodes[source].get('patch_version')} → {G.nodes[target].get('patch_version')}")
        print()
    
    # check series progression chains
    series_edges = [(u, v) for u, v, d in G.edges(data=True) 
                   if d.get('evolution_type') == 'series_progression']
    
    print(f"\n--- Series Progression Examples ({len(series_edges)} total) ---")
    for i, (source, target) in enumerate(series_edges[:limit]):
        source_data = email_data.get(source, {})
        target_data = email_data.get(target, {})
        
        print(f"Series {i+1}:")
        print(f"  From: {source} - {source_data.get('subject', 'Unknown')[:50]}...")
        print(f"  To:   {target} - {target_data.get('subject', 'Unknown')[:50]}...")
        print(f"  Series: {G.nodes[source].get('series_info')} → {G.nodes[target].get('series_info')}")
        print()
    
    # check thread reply chains
    thread_edges = [(u, v) for u, v, d in G.edges(data=True) 
                   if d.get('relationship') == 'thread_reply']
    
    print(f"\n--- Thread Reply Examples ({len(thread_edges)} total) ---")
    for i, (source, target) in enumerate(thread_edges[:limit]):
        source_data = email_data.get(source, {})
        target_data = email_data.get(target, {})
        
        print(f"Thread {i+1}:")
        print(f"  From: {source} - {source_data.get('subject', 'Unknown')[:50]}...")
        print(f"  To:   {target} - {target_data.get('subject', 'Unknown')[:50]}...")
        print(f"  Time: {G.nodes[source].get('chronological_order')} → {G.nodes[target].get('chronological_order')}")
        print()





def validate_merge_detection(patch_analysis: Dict, email_data: Dict, G: nx.DiGraph, sample_size: int = 10) -> None:
    """
    Manually validate merge detection accuracy on a sample.
    """
    print("\n" + "="*70)
    print("MERGE DETECTION VALIDATION")
    print("="*70)
    
    # Get samples from different probability ranges
    sorted_patches = sorted(patch_analysis.items(), key=lambda x: x[1]['merge_probability'], reverse=True)
    
    high_prob = [p for p in sorted_patches if p[1]['merge_probability'] >= 0.7][:3]
    med_prob = [p for p in sorted_patches if 0.3 <= p[1]['merge_probability'] < 0.7][:3]
    low_prob = [p for p in sorted_patches if p[1]['merge_probability'] < 0.3][:3]
    
    print("\n=== HIGH PROBABILITY SAMPLES ===")
    for signature, analysis in high_prob:
        show_validation_sample(signature, analysis, email_data, G)
    
    print("\n=== MEDIUM PROBABILITY SAMPLES ===")
    for signature, analysis in med_prob:
        show_validation_sample(signature, analysis, email_data, G)
    
    print("\n=== LOW PROBABILITY SAMPLES ===")
    for signature, analysis in low_prob:
        show_validation_sample(signature, analysis, email_data, G)

def show_validation_sample(signature: str, analysis: Dict, email_data: Dict, G: nx.DiGraph) -> None:
    """
    Show a detailed sample for manual validation.
    """
    print(f"\nPatch: {signature[:50]}...")
    print(f"Status: {analysis['status']} ({analysis['merge_probability']:.2%})")
    print(f"Signals: {analysis['merge_signals']}")
    
    # Find and show actual email content
    for node_id in G.nodes():
        email = email_data.get(node_id, {})
        if email.get('patch_info'):
            from email_parser import extract_patch_signature_improved
            node_signature = extract_patch_signature_improved(email.get('subject', ''))
            if node_signature == signature:
                merge_info = email.get('merge_info', {})
                if merge_info.get('merge_signals'):
                    print(f"Evidence from Email {node_id}:")
                    body = email.get('message_body', '')[:200] + "..." if email.get('message_body') else "No body"
                    print(f"  Body snippet: {body}")
                    break


def setup_git_pull_table():
    """
    Ensure the git pull table exists in the database.
    """
    from data_access import create_git_pull_table, populate_git_pull_table, get_connection
    print("Setting up git pull table...")
    create_git_pull_table()

    # check if the table is already populated
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM git_pull_emails")
    count = cursor.fetchone()[0]
    if count == 0:
        print("Populating git pull table with existing data...")
        populate_git_pull_table()
    else:
        print(f"Git pull table already populated with {count} entries.")



def main():
    """Main function for the LKML Email Graph Analysis Tool"""
    args = parse_arguments()

    if args.sample_size >= 2000:
        check_git_pull_in_database()

    if args.setup_git_pull_table:
        setup_git_pull_table()
        return
    
    # Handle full-scale batch processing
    if args.full_scale:
        processor = create_batch_processor(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password
        )
        
        stats = processor.process_thread_aware_batches(
            batch_size=args.batch_size,
            export_to_neo4j=args.export_neo4j
        )
        
        print(f"\n=== FINAL STATISTICS ===")
        print(f"Total emails processed: {stats.get('total_emails', 0)}")
        print(f"Total graph nodes: {stats.get('total_nodes', 0)}")
        print(f"Total graph edges: {stats.get('total_edges', 0)}")
        return
    
    # Regular single-batch processing for development
    analyze_database_coverage()
    emails = get_patch_emails(limit=args.sample_size)
    
    print(f"\nCreating patch evolution graph from {len(emails)} emails...")
    graph, email_data, patch_groups = create_evolution_graph2(emails)

    #git_pull_patch_mapping = find_and_map_git_pull_patches(email_data)
    git_pull_emails = find_git_pull_emails_regex(email_data)

    if git_pull_emails:
        print("\n" + "="*60)
        print("FOUND [GIT PULL] EMAILS")
        print("="*60)
        for pull_id, info in git_pull_emails.items():
            print(f"\n[GIT PULL] Email {pull_id}: {info['subject']}")
            # For now, just show we found them - skip the linking
    else:
        print("\nNo [GIT PULL] emails found in this sample.")

    # if git_pull_patch_mapping:
    #     print("\n" + "="*60)
    #     print("GIT PULL EMAILS AND THEIR REFERENCED PATCHES")
    #     print("="*60)
    #     for pull_id, info in git_pull_patch_mapping.items():
    #         pull_email = email_data.get(pull_id, {})
    #         print(f"\n[GIT PULL] Email {pull_id}: {pull_email.get('subject', '')}")
    #         print(f"  Patch names referenced: {info['patch_names']}")
    #         for patch_name, linked_ids in info['linked_emails'].items():
    #             if linked_ids:
    #                 print(f"    Patch '{patch_name}' linked to email IDs: {linked_ids}")
    #             else:
    #                 print(f"    Patch '{patch_name}' not found in emails.")
    # else:
    #     print("\nNo git pull emails found in this sample.")

    # Debug for smaller samples to make sure the nodes are actually being connected
    if args.sample_size <= 100:
        debug_relationships(graph, email_data)
        
        print("\n=== HIGH-CONNECTIVITY NODES ===")
        for node_id in graph.nodes():
            in_degree = graph.in_degree(node_id)
            out_degree = graph.out_degree(node_id)
            total_degree = in_degree + out_degree
            
            if total_degree > 5:
                email = email_data.get(node_id, {})
                subject = email.get('subject', 'Unknown')[:60]
                print(f"Node {node_id}: {in_degree} in, {out_degree} out")
                print(f"  Subject: {subject}...")
                print()
    
    analyze_graph_components(graph, email_data)
    
    # Export to Neo4j if requested
    if args.export_neo4j and NEO4J_READY:
        print(f"\n=== EXPORTING TO NEO4J ===")
        try:
            export_connected_subgraph_to_neo4j(
                graph, email_data,
                uri=args.neo4j_uri,
                user=args.neo4j_user,
                password=args.neo4j_password
            )
            print("✅ Neo4j export completed!")
        except Exception as e:
            print(f"❌ Neo4j export failed: {e}")
    
    if not args.analyze_only:

        # case study before the visualization
        if args.case_study:
            print("\n" + "="*50)
            print("CONDUCTING PATCH MERGE CASE STUDY")
            print("="*50)
            
            patch_analysis = analyze_patch_merge_status(graph, email_data)
            generate_case_study_report(patch_analysis)

            if args.sample_size <= 2000:  # Only for smaller samples to avoid spam
                verify_merge_indicators(patch_analysis, email_data, graph)

            if args.text_report:
                 from case_study import generate_merge_indicators_text_report
                 generate_merge_indicators_text_report(
                patch_analysis, email_data, graph, output_file=args.report_file
            )



        visualize_evolution_graph(graph, email_data, component_limit=15, max_nodes=300)
        validate_merge_detection(patch_analysis, email_data, graph)
    print("\nAnalysis complete!")



if __name__ == "__main__":
    main()