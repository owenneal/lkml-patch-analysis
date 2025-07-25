"""
Neo4j export functionality for LKML email graph.

This module provides functions to export the NetworkX graph to Neo4j
to support LLM-based analysis of patch evolution.
"""
#2025internshiplkml
from typing import Dict, Tuple
import networkx as nx
from neo4j import GraphDatabase


def query_patch_evolution(uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "password") -> None:
    """
    Example Neo4j query to find patch evolution chains.
    
    Args:
        uri: Neo4j connection URI
        user: Neo4j username
        password: Neo4j password
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Query for patch evolution chains
        result = session.run("""
            MATCH path = (start:Email)-[:PATCH_EVOLUTION*]->(latest:Email)
            WHERE NOT (:Email)-[:PATCH_EVOLUTION]->(start)
            AND NOT (latest)-[:PATCH_EVOLUTION]->(:Email)
            RETURN path, 
                start.subject as initial_patch, 
                start.patch_version as initial_version,
                latest.subject as latest_patch,
                latest.patch_version as latest_version,
                length(path) as versions
            ORDER BY versions DESC
            LIMIT 10
        """)
        
        print("\n=== Top Patch Evolution Chains ===")
        for record in result:
            print(f"From v{record['initial_version']} to v{record['latest_version']} ({record['versions']} steps)")
            print(f"  Initial: {record['initial_patch'][:60]}...")
            print(f"  Latest: {record['latest_patch'][:60]}...")
            print()
    
    driver.close()


def export_connected_subgraph_to_neo4j(
        G: nx.DiGraph, 
        email_data: Dict, 
        uri: str = "bolt://localhost:7687", 
        user: str = "neo4j", 
        password: str = "2025internshiplkml",
        clear_existing: bool = True
    ) -> None:
    """
    Export a connected subgraph to Neo4j that mirrors the NetworkX visualization.
    """
    
    # Get components sorted by size (same as your visualization)
    components = list(nx.weakly_connected_components(G))
    components.sort(key=len, reverse=True)
    
    print(f"Found {len(components)} total components")
    print(f"Top 10 component sizes: {[len(c) for c in components[:10]]}")
    
    # Filter to components with multiple nodes (same as visualization)
    multi_node_components = [c for c in components if len(c) > 1]
    
    print(f"Components with multiple nodes: {len(multi_node_components)}")
    print(f"Top 10 multi-node component sizes: {[len(c) for c in multi_node_components[:10]]}")
    
    if not multi_node_components:
        print("No connected components found with multiple nodes!")
        return
    
    # The visualization logic in visualize_evolution_graph actually just takes the largest components
    selected_components = multi_node_components
    
    # Use same limits as your visualization
    component_limit = 15
    max_nodes = 300
    
    # Select nodes (same logic as visualization)
    nodes_to_include = set()
    components_included = 0
    
    for component in selected_components:
        if components_included >= component_limit:
            break
            
        if len(nodes_to_include) + len(component) <= max_nodes:
            nodes_to_include.update(component)
            components_included += 1
            print(f"Including component {components_included} with {len(component)} nodes")
        else:
            # Try to fit smaller components
            remaining_capacity = max_nodes - len(nodes_to_include)
            if len(component) <= remaining_capacity:
                nodes_to_include.update(component)
                components_included += 1
                print(f"Including component {components_included} with {len(component)} nodes")
            else:
                print(f"Skipping component with {len(component)} nodes (would exceed max_nodes)")
    
    print(f"Final selection: {len(nodes_to_include)} nodes from {components_included} components")
    
    # Create subgraph (same as visualization)
    subgraph = G.subgraph(nodes_to_include).copy()
    
    # Remove self-loops (same as visualization)
    self_loops = list(nx.selfloop_edges(subgraph))
    subgraph.remove_edges_from(self_loops)
    
    print(f"Final subgraph: {subgraph.number_of_nodes()} nodes, {subgraph.number_of_edges()} edges")
    
    # Show the actual components we're including
    subgraph_components = list(nx.weakly_connected_components(subgraph))
    subgraph_components.sort(key=len, reverse=True)
    print(f"Subgraph component sizes: {[len(c) for c in subgraph_components[:10]]}")
    
    # Rest of the export code remains the same...
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Clear existing data completely
        # print("Clearing existing data...")
        # session.run("MATCH (n) DETACH DELETE n")

        if clear_existing:
            print("Clearing existing data...")
            session.run("MATCH (n) DETACH DELETE n")
        
        # Drop existing indexes to avoid conflicts
        print("Dropping existing indexes...")
        try:
            session.run("DROP INDEX ON :Email(id)")
        except:
            pass  # Index might not exist
        
        try:
            session.run("DROP INDEX FOR (e:Email) ON (e.id)")
        except:
            pass  # Index might not exist
        
        print("Creating nodes...")
        # Create nodes from the connected subgraph
        for node_id in subgraph.nodes():
            node_data = G.nodes[node_id]
            email = email_data.get(node_id, {})
            
            # Get message body (the actual email content)
            message_body = email.get('message_body', '')
            
            # Truncate very long messages
            if len(message_body) > 5000:
                message_body = message_body[:5000] + "... [TRUNCATED]"
            
            # Create Cypher parameters
            params = {
                'id': node_id,
                'subject': node_data.get('subject', ''),
                'author': node_data.get('author', ''),
                'date': node_data.get('date', ''),
                'url': node_data.get('url', ''),
                'is_patch': node_data.get('is_patch', False),
                'patch_version': node_data.get('patch_version', ''),
                'version_num': node_data.get('version_num', 0),
                'series_info': node_data.get('series_info', ''),
                'series_position': node_data.get('series_position', 0),
                'series_total': node_data.get('series_total', 0),
                'message_body': message_body
            }
            
            # Create Email node
            session.run("""
                CREATE (e:Email {
                    id: $id,
                    subject: $subject,
                    author: $author,
                    date: $date,
                    url: $url,
                    is_patch: $is_patch,
                    patch_version: $patch_version,
                    version_num: $version_num,
                    series_info: $series_info,
                    series_position: $series_position,
                    series_total: $series_total,
                    message_body: $message_body
                })
            """, params)
        
        print("Creating relationships...")
        # Create ALL relationships from the subgraph (this preserves connectivity)
        for source, target, edge_data in subgraph.edges(data=True):
            relationship = edge_data.get('relationship', 'RELATED')
            evolution_type = edge_data.get('evolution_type', '')
            weight = edge_data.get('weight', 1.0)
            
            # Format relationship type for Neo4j
            rel_type = relationship.upper().replace(' ', '_')
            
            session.run(f"""
                MATCH (source:Email {{id: $source}}), (target:Email {{id: $target}})
                CREATE (source)-[r:{rel_type} {{weight: $weight, evolution_type: $evolution_type}}]->(target)
            """, {
                'source': source,
                'target': target,
                'weight': weight,
                'evolution_type': evolution_type
            })
        
        # Add index for performance (with error handling)
        print("Creating index...")
        try:
            session.run("CREATE INDEX FOR (e:Email) ON (e.id)")
            print("Index created successfully")
        except Exception as e:
            print(f"Index creation failed (might already exist): {e}")
        
        # Verify the export
        result = session.run("MATCH (n:Email) RETURN count(n) as nodes")
        node_count = result.single()["nodes"]
        
        result = session.run("MATCH ()-[r]->() RETURN count(r) as relationships")
        rel_count = result.single()["relationships"]
        
        print(f"Successfully exported: {node_count} nodes, {rel_count} relationships")
        
        # Show connectivity statistics
        result = session.run("""
            MATCH (n:Email)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, count(r) as degree
            RETURN 
                avg(degree) as avg_degree,
                max(degree) as max_degree,
                min(degree) as min_degree,
                count(n) as total_nodes
        """)
        
        stats = result.single()
        print(f"Connectivity stats - Avg degree: {stats['avg_degree']:.2f}, Max: {stats['max_degree']}, Min: {stats['min_degree']}")
    
    driver.close()


def test_connectivity_queries(uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "2025internshiplkml") -> None:
    """
    Test queries to verify connectivity is preserved using standard Cypher.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        print("\n=== CONNECTIVITY TEST ===")
        
        # Basic counts
        result = session.run("MATCH (n:Email) RETURN count(n) as total_nodes")
        total_nodes = result.single()["total_nodes"]
        print(f"Total nodes: {total_nodes}")
        
        result = session.run("MATCH ()-[r]->() RETURN count(r) as total_relationships")
        total_relationships = result.single()["total_relationships"]
        print(f"Total relationships: {total_relationships}")
        
        # Check relationship types
        result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) as relationship_type, count(r) as count
            ORDER BY count DESC
        """)
        
        print("\nRelationship types:")
        for record in result:
            print(f"  {record['relationship_type']}: {record['count']}")
        
        # Find connected components manually (simplified version)
        result = session.run("""
            MATCH (n:Email)
            WHERE NOT EXISTS((n)-[]->()) AND NOT EXISTS(()-[]->(n))
            RETURN count(n) as isolated_nodes
        """)
        
        isolated_nodes = result.single()["isolated_nodes"]
        connected_nodes = total_nodes - isolated_nodes
        print(f"\nConnected nodes: {connected_nodes}")
        print(f"Isolated nodes: {isolated_nodes}")
        
        # Show nodes with most connections
        result = session.run("""
            MATCH (n:Email)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, count(r) as degree
            WHERE degree > 0
            RETURN n.id as node_id, n.subject as subject, degree
            ORDER BY degree DESC
            LIMIT 5
        """)
        
        print("\nMost connected nodes:")
        for record in result:
            print(f"  Node {record['node_id']}: {record['degree']} connections")
            print(f"    Subject: {record['subject'][:50]}...")
        
        # Show largest connected groups using a simple traversal
        result = session.run("""
            MATCH (n:Email)
            OPTIONAL MATCH (n)-[]-(connected)
            WITH n, count(DISTINCT connected) as connections
            WHERE connections > 0
            RETURN connections, count(n) as nodes_with_this_many_connections
            ORDER BY connections DESC
            LIMIT 10
        """)
        
        print("\nNodes by connection count:")
        for record in result:
            print(f"  {record['nodes_with_this_many_connections']} nodes have {record['connections']} connections")
        
        # Show some patch evolution chains
        print("\n=== PATCH EVOLUTION CHAINS ===")
        result = session.run("""
            MATCH path = (start:Email)-[:PATCH_EVOLUTION*1..5]->(end:Email)
            RETURN start.id as start_id,
                   start.patch_version as start_version,
                   start.subject as start_subject,
                   end.id as end_id,
                   end.patch_version as end_version,
                   end.subject as end_subject,
                   length(path) as chain_length
            ORDER BY chain_length DESC
            LIMIT 5
        """)
        
        evolution_chains = list(result)
        if evolution_chains:
            for record in evolution_chains:
                print(f"Evolution chain ({record['chain_length']} steps):")
                print(f"  Start: {record['start_id']} ({record['start_version']}) - {record['start_subject'][:40]}...")
                print(f"  End:   {record['end_id']} ({record['end_version']}) - {record['end_subject'][:40]}...")
                print()
        else:
            print("No patch evolution chains found")
        
        # Show some series progression chains
        print("\n=== SERIES PROGRESSION CHAINS ===")
        result = session.run("""
            MATCH path = (start:Email)-[:PATCH_SERIES*1..3]->(end:Email)
            RETURN start.id as start_id,
                   start.series_info as start_series,
                   start.subject as start_subject,
                   end.id as end_id,
                   end.series_info as end_series,
                   end.subject as end_subject,
                   length(path) as chain_length
            ORDER BY chain_length DESC
            LIMIT 5
        """)
        
        series_chains = list(result)
        if series_chains:
            for record in series_chains:
                print(f"Series progression ({record['chain_length']} steps):")
                print(f"  Start: {record['start_id']} ({record['start_series']}) - {record['start_subject'][:40]}...")
                print(f"  End:   {record['end_id']} ({record['end_series']}) - {record['end_subject'][:40]}...")
                print()
        else:
            print("No series progression chains found")
        
        # Show some sample patch content
        print("\n=== SAMPLE PATCH CONTENT ===")
        result = session.run("""
            MATCH (e:Email)
            WHERE e.is_patch = true AND e.message_body IS NOT NULL AND e.message_body <> ''
            RETURN e.id as id, 
                   e.subject as subject, 
                   e.patch_version as version,
                   e.message_body as content
            LIMIT 3
        """)
        
        for record in result:
            print(f"\nPatch {record['id']} ({record['version']}):")
            print(f"Subject: {record['subject']}")
            print(f"Content preview: {record['content'][:200]}...")
            print("="*60)
    
    driver.close()


if __name__ == "__main__":
    from core.data_access import get_patch_emails, analyze_database_coverage
    from core.graph_builder import create_evolution_graph
    
    print("Getting emails (using same sample size as visualization)...")
    emails = get_patch_emails(limit=1000)
    
    print("Creating graph...")
    graph, email_data, patch_groups = create_evolution_graph(emails)
    
    print("Exporting connected subgraph to Neo4j...")
    export_connected_subgraph_to_neo4j(graph, email_data)
    
    print("Testing connectivity...")
    test_connectivity_queries()
    
    print("\nTest complete! Check Neo4j Browser at http://localhost:7474")
    print("\nTry these queries in Neo4j Browser:")
    print("1. MATCH (n:Email) RETURN count(n)")
    print("2. MATCH ()-[r]->() RETURN type(r), count(r)")
    print("3. MATCH (n:Email)-[r]-(m:Email) RETURN n, r, m LIMIT 50")