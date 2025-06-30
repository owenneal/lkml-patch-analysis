"""
Batch processing functionality for large-scale graph creation.

This module handles processing 400k+ emails in manageable chunks while
preserving conversation relationships across batches.
"""

from typing import Dict, List, Tuple
import networkx as nx

from data_access import get_complete_thread_batches
from graph_builder import create_evolution_graph2

try:
    from neo4j_export import export_connected_subgraph_to_neo4j, test_connectivity_queries
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

"""Handles large-scale batch processing of email graphs."""
class BatchProcessor:
    
    def __init__(self, neo4j_uri: str = "bolt://localhost:7687", 
                 neo4j_user: str = "neo4j", 
                 neo4j_password: str = "2025internshiplkml"):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        
        if not NEO4J_AVAILABLE:
            print("Warning: Neo4j not available. Install neo4j package for database export.")

    
    """
        Process all emails in thread-aware batches.
        
        Args:
            batch_size: Target emails per batch (may vary to preserve threads)
            export_to_neo4j: Whether to export each batch to Neo4j
            
        Returns:
            Dictionary with processing statistics
    """
    def process_thread_aware_batches(self, batch_size: int = 5000, 
                                   export_to_neo4j: bool = True) -> Dict:
        
        if export_to_neo4j and not NEO4J_AVAILABLE:
            print("Error: Neo4j export requested but neo4j package not available")
            return {"error": "Neo4j not available"}
        
        print(f"=== THREAD-AWARE BATCH PROCESSING ===")
        print(f"Target batch size: {batch_size} emails")
        
        # Get all emails grouped by complete threads
        batches = get_complete_thread_batches(batch_size=batch_size)
        
        stats = {
            "total_batches": len(batches),
            "total_emails": 0,
            "total_nodes": 0,
            "total_edges": 0,
            "batches_processed": 0,
            "errors": []
        }
        
        print(f"Processing {len(batches)} thread-aware batches...")
        
        for batch_num, batch_emails in enumerate(batches):
            print(f"\n--- Processing Batch {batch_num + 1}/{len(batches)} ---")
            print(f"Emails in batch: {len(batch_emails)}")
            
            try:
                # Create graph for this batch (complete threads)
                graph, email_data, patch_groups = create_evolution_graph2(batch_emails)
                
                batch_nodes = graph.number_of_nodes()
                batch_edges = graph.number_of_edges()
                
                print(f"Graph created: {batch_nodes} nodes, {batch_edges} edges")
                
                # Update statistics
                stats["total_emails"] += len(batch_emails)
                stats["total_nodes"] += batch_nodes
                stats["total_edges"] += batch_edges
                
                # Export to Neo4j if requested
                if export_to_neo4j:
                    clear_db = (batch_num == 0)  # Only clear on first batch
                    print(f"Exporting to Neo4j (clear_db={clear_db})...")
                    
                    export_connected_subgraph_to_neo4j(
                        graph, 
                        email_data,
                        uri=self.neo4j_uri,
                        user=self.neo4j_user,
                        password=self.neo4j_password,
                        clear_existing=clear_db
                    )
                
                stats["batches_processed"] += 1
                print(f"✅ Batch {batch_num + 1} completed successfully")
                
            except Exception as e:
                error_msg = f"Batch {batch_num + 1} failed: {str(e)}"
                print(f"❌ {error_msg}")
                stats["errors"].append(error_msg)
                continue
        
        print(f"\n=== BATCH PROCESSING COMPLETE ===")
        print(f"Processed {stats['batches_processed']}/{stats['total_batches']} batches")
        print(f"Total emails: {stats['total_emails']}")
        print(f"Total graph nodes: {stats['total_nodes']}")
        print(f"Total graph edges: {stats['total_edges']}")
        
        if stats["errors"]:
            print(f"Errors encountered: {len(stats['errors'])}")
            for error in stats["errors"]:
                print(f"  - {error}")
        
        # Test final Neo4j connectivity if exported
        if export_to_neo4j and stats["batches_processed"] > 0:
            print("\nTesting final Neo4j connectivity...")
            try:
                test_connectivity_queries(
                    uri=self.neo4j_uri,
                    user=self.neo4j_user,
                    password=self.neo4j_password
                )
                print("✅ Neo4j connectivity test passed")
            except Exception as e:
                print(f"❌ Neo4j connectivity test failed: {e}")
        
        return stats

"""Factory function to create a BatchProcessor instance."""
def create_batch_processor(neo4j_uri: str = "bolt://localhost:7687",
                          neo4j_user: str = "neo4j", 
                          neo4j_password: str = "2025internshiplkml") -> BatchProcessor:
    return BatchProcessor(neo4j_uri, neo4j_user, neo4j_password)