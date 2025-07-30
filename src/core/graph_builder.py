"""
Graph building functionality for LKML email analysis.

This module provides functions to create and analyze a graph representation
of email relationships based on patch topics and thread relationships.
"""

import networkx as nx
import re
from collections import defaultdict
from typing import Dict, List, Tuple
from .email_parser import parse_email_content, extract_patch_signature_improved, extract_temporal_info


def _process_emails_and_create_nodes(emails: List[Tuple], G: nx.DiGraph) -> Tuple[Dict, Dict, Dict]:
    """
    Process all emails, add them as nodes to the graph, and collect grouping data.
    
    Args:
        emails: List of (id, title, url, html_content) tuples
        G: NetworkX DiGraph to add nodes to
        
    Returns:
        Tuple of (email_data, patch_groups, thread_groups)
    """
    patch_groups = defaultdict(list) #groups related patches by signature
    thread_groups = defaultdict(list) #groups related emails by thread URL
    email_data = {}
    
    print(f"Processing {len(emails)} emails and creating nodes...")
    
    for email_id, title, url, html_content in emails:
        try:
            # Parse email content into structured data
            parsed_data = parse_email_content(html_content)
            email_data[email_id] = parsed_data
            
            # Extract temporal and versioning information
            chronological_order, version_num, series_position, series_total, parsed_date = extract_temporal_info(email_data, email_id)
            
            # Add email as a node with comprehensive attributes
            G.add_node(email_id, 
                      # Basic email metadata
                      subject=parsed_data['subject'],
                      author=parsed_data['from_author'],
                      date=parsed_data['date'],
                      parsed_date=parsed_date,
                      url=url,
                      
                      # Patch-specific metadata
                      is_patch=parsed_data['patch_info'] is not None,
                      patch_version=parsed_data['patch_info']['version'] if parsed_data['patch_info'] else None,
                      version_num=version_num,
                      
                      # Series information
                      series_info=parsed_data['patch_info']['series_info'] if parsed_data['patch_info'] else '',
                      series_position=series_position,
                      series_total=series_total,
                      
                      # Temporal ordering
                      chronological_order=chronological_order,
                      merge_info=parsed_data['merge_info'])
            
            
            # Group emails by normalized patch signature
            if parsed_data['subject']:
                patch_sig = extract_patch_signature_improved(parsed_data['subject'])
                if patch_sig:
                    patch_groups[patch_sig].append(email_id)
            
            # Group emails by thread/conversation
            for thread_msg in parsed_data['thread_messages']:
                thread_url = thread_msg['url']
                thread_groups[thread_url].append(email_id)
                
        except Exception as e:
            print(f"Error processing email {email_id}: {e}")
            continue
    
    return email_data, patch_groups, thread_groups



def _create_in_reply_to_edges(G: nx.DiGraph, email_data: Dict) -> int:

    msgid_to_node = {}
    for node_id, data in email_data.items():
        msgid = data.get('message_id')
        if msgid:
            msgid_to_node[msgid] = node_id

    added_edges = 0
    for node_id, data in email_data.items():
        parent_msgid = data.get('in_reply_to')
        if parent_msgid and parent_msgid in msgid_to_node:
            parent_node_id = msgid_to_node[parent_msgid]
            if not G.has_edge(parent_node_id, node_id):
                G.add_edge(parent_node_id, node_id,
                          relationship='in_reply_to',
                          weight=0.5,
                          evolution_type='discussion')
                added_edges += 1

    print(f"Added {added_edges} in-reply-to edges")
    return added_edges


def _create_patch_evolution_edges(G: nx.DiGraph, patch_groups: Dict) -> int:
    """
    Create edges representing patch evolution and series progression.
    
    Args:
        G: NetworkX DiGraph to add edges to
        patch_groups: Dictionary grouping emails by patch signature
        
    Returns:
        Number of edges added
    """
    edges_added = 0
    
    print("Creating patch evolution edges...")
    
    for patch_sig, email_ids in patch_groups.items():
        if len(email_ids) > 1:
            # Sort emails by: version number, then series position, then time
            email_ids.sort(key=lambda eid: (
                G.nodes[eid]['version_num'],
                G.nodes[eid]['series_position'],
                G.nodes[eid]['chronological_order']
            ))
            
            # Create directed edges showing evolution progression
            for i in range(len(email_ids) - 1):
                current_email = email_ids[i]
                next_email = email_ids[i + 1]
                
                # Get version and series information for both emails
                current_version = G.nodes[current_email]['version_num']
                next_version = G.nodes[next_email]['version_num']
                current_series = G.nodes[current_email]['series_position']
                next_series = G.nodes[next_email]['series_position']
                
                # Determine the type of relationship based on version and series changes
                if current_version < next_version:
                    # Version evolution: v1 -> v2, v2 -> v3
                    G.add_edge(current_email, next_email,
                              relationship='patch_evolution',
                              weight=2.0,
                              evolution_type='version_upgrade')
                    edges_added += 1
                elif current_version == next_version and current_series < next_series:
                    # Series progression: 1/7 -> 2/7 -> 3/7
                    G.add_edge(current_email, next_email,
                              relationship='patch_series',
                              weight=1.5,
                              evolution_type='series_progression')
                    edges_added += 1
                else:
                    # Same topic discussion
                    G.add_edge(current_email, next_email,
                              relationship='same_patch_topic', 
                              weight=1.0,
                              evolution_type='discussion')
                    edges_added += 1
    
    return edges_added


def _create_thread_reply_edges(G: nx.DiGraph, thread_groups: Dict) -> int:
    """
    Create edges representing thread conversation flow.
    
    Args:
        G: NetworkX DiGraph to add edges to
        thread_groups: Dictionary grouping emails by thread
        
    Returns:
        Number of edges added
    """
    edges_added = 0
    
    print("Creating thread reply edges...")
    
    for thread_url, email_ids in thread_groups.items():
        if len(email_ids) > 1:

            # remove duplicates first
            email_ids = list(set(email_ids))

            if len(email_ids) <= 1:  # skip if only one email after removing self loops
                continue

            # Sort by actual timestamp for true chronological order
            email_ids.sort(key=lambda eid: G.nodes[eid]['chronological_order'])
            
            # Create conversation chain based on temporal order
            for i in range(len(email_ids) - 1):
                current_email = email_ids[i]
                next_email = email_ids[i+1]
                
                # Only add thread edge if not already connected by patch relationship
                if not G.has_edge(current_email, next_email):
                    G.add_edge(current_email, next_email,
                              relationship='thread_reply',
                              weight=0.8,
                              evolution_type='discussion')
                    edges_added += 1
    
    return edges_added


def _create_thread_reply_edges2(G: nx.DiGraph, thread_groups: Dict, email_data: Dict) -> int:
    """
    Create edges representing logical conversation flow.
    
    Focuses on showing how patches evolve through discussion.
    """
    edges_added = 0
    
    print("Creating thread reply edges...")
    
    for thread_url, email_ids in thread_groups.items():
        if len(email_ids) > 1:
            # Remove duplicates first
            email_ids = list(set(email_ids))
            
            if len(email_ids) <= 1:  # Skip if only one email after deduplication
                continue
            
            # Sort by logical conversation order
            email_ids.sort(key=lambda eid: _get_conversation_order_key(eid, G, email_data))
            
            # Create conversation chain showing discussion flow
            for i in range(len(email_ids) - 1):
                current_email = email_ids[i]
                next_email = email_ids[i+1]
                
                # Prevent self-loops
                if current_email == next_email:
                    continue
                
                # Only add thread edge if not already connected by patch relationship
                if not G.has_edge(current_email, next_email):
                    # Determine the type of discussion relationship
                    relationship_type = _determine_discussion_relationship(current_email, next_email, G, email_data)
                    
                    G.add_edge(current_email, next_email,
                              relationship='thread_reply',
                              weight=0.8,
                              evolution_type='discussion',
                              discussion_type=relationship_type)
                    edges_added += 1
    
    return edges_added


def _get_conversation_order_key(email_id: int, G: nx.DiGraph, email_data: Dict) -> tuple:
    """
    Create a sorting key that prioritizes logical conversation flow over strict timing.
    """
    email = email_data.get(email_id, {})
    subject = email.get('subject', '') or ''  # Handle None subjects
    
    # Determine email type for ordering
    is_reply = subject.lower().startswith('re:') if subject else False
    is_patch = G.nodes[email_id].get('is_patch', False)
    version_num = G.nodes[email_id].get('version_num', 0) or 0
    series_position = G.nodes[email_id].get('series_position', 0) or 0
    chronological_order = G.nodes[email_id].get('chronological_order', 0) or 0
    
    # Create ordering tuple: (reply_priority, patch_priority, version, series, time)
    reply_priority = 1 if is_reply else 0  # Non-replies first
    patch_priority = 0 if is_patch else 1  # Patches before discussions
    
    return (reply_priority, patch_priority, version_num, series_position, chronological_order)


def _determine_discussion_relationship(current_id: int, next_id: int, G: nx.DiGraph, email_data: Dict) -> str:
    """
    Determine the specific type of discussion relationship for LLM context.
    """
    current_email = email_data.get(current_id, {})
    next_email = email_data.get(next_id, {})
    
    current_subject = current_email.get('subject', '') or ''  # Handle None subjects
    next_subject = next_email.get('subject', '') or ''        # Handle None subjects
    
    current_is_patch = G.nodes[current_id].get('is_patch', False)
    next_is_patch = G.nodes[next_id].get('is_patch', False)
    
    current_is_reply = current_subject.lower().startswith('re:') if current_subject else False
    next_is_reply = next_subject.lower().startswith('re:') if next_subject else False
    
    # Categorize the relationship type
    if current_is_patch and next_is_reply:
        return 'patch_to_review'  # Original patch → Review/feedback
    elif current_is_reply and next_is_patch:
        return 'review_to_patch'  # Review/feedback → Updated patch
    elif current_is_reply and next_is_reply:
        return 'review_discussion'  # Review → Counter-review/discussion
    elif current_is_patch and next_is_patch:
        return 'patch_comparison'  # Patch → Related patch
    else:
        return 'general_discussion'  # Other discussion flow


def _create_enhanced_discussion_edges(G: nx.DiGraph, email_data: Dict) -> int:
    """
    Create additional edges to show patch-review-update cycles for LLM analysis.
    
    This finds patterns like: [PATCH v1] → Re: [PATCH v1] → [PATCH v2]
    """
    edges_added = 0
    
    print("Creating enhanced discussion flow edges...")
    
    # Find patch-review-update cycles
    patch_nodes = [nid for nid in G.nodes() if G.nodes[nid].get('is_patch', False)]
    
    for patch_id in patch_nodes:
        patch_email = email_data.get(patch_id, {})
        patch_subject = patch_email.get('subject', '') or ''  # Handle None subjects
        patch_signature = extract_patch_signature_improved(patch_subject)
        
        if not patch_signature:
            continue
        
        # Find replies to this patch
        replies = []
        for other_id in G.nodes():
            other_email = email_data.get(other_id, {})
            other_subject = other_email.get('subject', '') or ''  # Handle None subjects
            
            # Check if this is a reply to our patch
            if other_subject and other_subject.lower().startswith('re:'):
                other_signature = extract_patch_signature_improved(other_subject)
                if other_signature and patch_signature in other_signature:
                    replies.append(other_id)
        
        # Connect patch to its replies
        for reply_id in replies:
            if not G.has_edge(patch_id, reply_id):
                G.add_edge(patch_id, reply_id,
                          relationship='patch_review',
                          weight=1.2,
                          evolution_type='review_feedback')
                edges_added += 1
        
        # Find next version of this patch and connect via reviews
        next_version_num = G.nodes[patch_id].get('version_num', 0) + 1
        
        for other_id in G.nodes():
            if (G.nodes[other_id].get('version_num', 0) == next_version_num and
                G.nodes[other_id].get('is_patch', False)):
                
                other_email = email_data.get(other_id, {})
                other_subject = other_email.get('subject', '') or ''  # Handle None subjects
                other_signature = extract_patch_signature_improved(other_subject)
                
                if other_signature and patch_signature == other_signature:
                    # Connect through review chain: patch → reviews → next_patch
                    for reply_id in replies:
                        if not G.has_edge(reply_id, other_id):
                            G.add_edge(reply_id, other_id,
                                      relationship='review_to_update',
                                      weight=1.5,
                                      evolution_type='feedback_incorporation')
                            edges_added += 1
                    break
    
    return edges_added


def _print_evolution_statistics(G: nx.DiGraph) -> None:
    """
    Print comprehensive statistics about the patch evolution graph.
    
    Args:
        G: NetworkX DiGraph to analyze
    """
    print("\n=== PATCH EVOLUTION GRAPH STATISTICS ===")
    print(f"Nodes (emails): {G.number_of_nodes()}")
    print(f"Edges (relationships): {G.number_of_edges()}")
    print(f"Connected components: {nx.number_weakly_connected_components(G)}")
    
    # Analyze specific evolution patterns
    evolution_edges = [(u, v) for u, v, d in G.edges(data=True) 
                      if d.get('evolution_type') == 'version_upgrade']
    series_edges = [(u, v) for u, v, d in G.edges(data=True) 
                  if d.get('evolution_type') == 'series_progression']
    
    print(f"Version evolution edges (v1→v2): {len(evolution_edges)}")
    print(f"Series progression edges (4/7→5/7): {len(series_edges)}")


def create_basic_email_graph(emails: List[Tuple]) -> Tuple[nx.DiGraph, Dict, Dict]:
    """
    Create a basic email relationship graph using simple grouping rules.
    
    This function creates a directed graph where:
    - Each email is a node
    - Edges represent relationships (same patch topic, thread replies)
    - Uses basic grouping without advanced ordering
    
    Args:
        emails: List of tuples containing (email_id, title, url, html_content)
        
    Returns:
        Tuple containing:
        - NetworkX DiGraph: The relationship graph
        - Dict: Parsed email data for each email_id
        - Dict: Groups of emails by patch signature
    """
    # Create a directed graph
    G = nx.DiGraph()
    
    # Data structures for grouping
    patch_groups = defaultdict(list)
    thread_groups = defaultdict(list)
    email_data = {}
    
    print(f"Building basic graph from {len(emails)} emails...")
    
    # Step 1: Add all emails as nodes and collect grouping data
    for email_id, title, url, html_content in emails:
        try:
            parsed_data = parse_email_content(html_content)
            email_data[email_id] = parsed_data
            
            # Add email as a node with basic attributes
            G.add_node(email_id, 
                      subject=parsed_data['subject'],
                      author=parsed_data['from_author'],
                      date=parsed_data['date'],
                      url=url,
                      is_patch=parsed_data['patch_info'] is not None,
                      patch_version=parsed_data['patch_info']['version'] if parsed_data['patch_info'] else None)
            
            # Group by patch signature
            if parsed_data['subject']:
                patch_sig = extract_patch_signature_improved(parsed_data['subject'])
                if patch_sig:
                    patch_groups[patch_sig].append(email_id)
            
            # Group by thread relationships
            for thread_msg in parsed_data['thread_messages']:
                thread_url = thread_msg['url']
                thread_groups[thread_url].append(email_id)
                
        except Exception as e:
            print(f"Error processing email {email_id}: {e}")
            continue
    
    # Step 2: Add edges between related emails
    edges_added = 0
    
    # Add edges within patch groups (same topic)
    for patch_sig, email_ids in patch_groups.items():
        if len(email_ids) > 1:
            # Create edges between all emails in the same patch group
            for i, email1 in enumerate(email_ids):
                for email2 in email_ids[i+1:]:
                    G.add_edge(email1, email2, 
                              relationship='same_patch_topic',
                              weight=1.0)
                    edges_added += 1
    
    # Add edges within thread groups (conversation flow)
    for thread_url, email_ids in thread_groups.items():
        if len(email_ids) > 1:
            # Sort by email ID (assuming chronological order)
            email_ids.sort()
            # Create chain of edges (conversation flow)
            for i in range(len(email_ids) - 1):
                G.add_edge(email_ids[i], email_ids[i+1], 
                          relationship='thread_reply',
                          weight=0.8)
                edges_added += 1
    
    # Print graph statistics
    print("\n=== BASIC GRAPH STATISTICS ===")
    print(f"Nodes (emails): {G.number_of_nodes()}")
    print(f"Edges (relationships): {G.number_of_edges()}")
    print(f"Connected components: {nx.number_weakly_connected_components(G)}")
    
    return G, email_data, patch_groups


def create_evolution_graph(emails: List[Tuple]) -> Tuple[nx.DiGraph, Dict, Dict]:
    """
    Create an graph that properly tracks patch evolution over time.
    
    This is the main function used by the application. It creates a sophisticated
    graph that understands patch version evolution, series progression, and
    chronological ordering based on actual timestamps.
    
    Args:
        emails: List of tuples containing (email_id, title, url, html_content)
        
    Returns:
        Tuple containing:
        - NetworkX DiGraph: Advanced relationship graph
        - Dict: Parsed email data for each email_id  
        - Dict: Groups of emails by patch signature
    """
    print(f"Building improved patch evolution graph from {len(emails)} emails...")
    
    # Create a directed graph for representing email relationships
    G = nx.DiGraph()
    
    # Step 1: Process all emails and create nodes with comprehensive attributes
    email_data, patch_groups, thread_groups = _process_emails_and_create_nodes(emails, G)
    
    # Step 2: Create sophisticated edges with proper temporal and version ordering
    patch_edges_added = _create_patch_evolution_edges(G, patch_groups)
    thread_edges_added = _create_thread_reply_edges(G, thread_groups)
    
    # Step 3: Print comprehensive statistics
    _print_evolution_statistics(G)
    
    return G, email_data, patch_groups


def create_evolution_graph2(emails: List[Tuple]) -> Tuple[nx.DiGraph, Dict, Dict]:
    """
    Create a graph optimized for LLM analysis of patch evolution and discussion flow.
    """
    print(f"Building LLM-focused patch evolution graph from {len(emails)} emails...")
    
    # Create a directed graph for representing email relationships
    G = nx.DiGraph()
    
    # Step 1: Process all emails and create nodes with comprehensive attributes
    email_data, patch_groups, thread_groups = _process_emails_and_create_nodes(emails, G)

    patch_edges_added = _create_patch_evolution_edges(G, patch_groups)
    thread_edges_added = _create_thread_reply_edges2(G, thread_groups, email_data)
    discussion_edges_added = _create_enhanced_discussion_edges(G, email_data)
    
    # add the merge liklihood logic here
    # each email node can also have a patch group merge likelihood attribute
    # this will be used to determine how likely a patch is to be merged based on discussion
    # from case_study import analyze_patch_merge_status
    # patch_analysis = analyze_patch_merge_status(G, email_data)
    
    _print_evolution_statistics(G)
    print(f"Added {patch_edges_added} patch evolution edges")
    print(f"Added {thread_edges_added} thread reply edges") 
    #print(f"Added {in_reply_edges_added} in-reply-to edges")
    print(f"Added {discussion_edges_added} discussion flow edges")
    
    return G, email_data, patch_groups


def analyze_graph_components(G, email_data):
    """
    Analyze the structure of connected components in the graph.
    
    Connected components are groups of emails that are related to each other
    through any path of relationships. This function helps understand:
    - How many separate discussion topics exist
    - Which topics have the most activity
    - What the size distribution looks like
    
    Args:
        G: NetworkX directed graph
        email_data: Dictionary containing parsed email information
    """
    # Get all connected components and sort by size (largest first)
    components = list(nx.weakly_connected_components(G))
    components.sort(key=len, reverse=True)
    
    print("=== GRAPH COMPONENT ANALYSIS ===")
    print(f"Total connected components: {len(components)}")
    
    # Count isolated vs connected emails
    isolated_count = sum(1 for c in components if len(c) == 1)
    connected_count = sum(1 for c in components if len(c) > 1)
    
    print(f"Isolated nodes (size 1): {isolated_count}")
    print(f"Connected groups (size 2+): {connected_count}")
    
    # Show details about the largest connected components
    print(f"\nTop 15 connected components:")
    for i, component in enumerate(components[:15]):
        if len(component) > 1:
            print(f"Component {i+1}: {len(component)} emails")
            
            # Show a sample email from this component to understand the topic
            sample_email = list(component)[0]
            if sample_email in email_data:
                subject = email_data[sample_email]['subject']
                print(f"  Sample: Email {sample_email}: {subject[:60]}...")
        else:
            print(f"Component {i+1}: {len(component)} emails (isolated)")
            if i > 10:  # Don't show too many isolated nodes
                break
    
    # Calculate cumulative node counts for different component limits
    total_nodes_by_limit = {}
    total_nodes = 0
    components_with_multiple = [c for c in components if len(c) > 1]
    
    # Calculate running totals
    for i, component in enumerate(components_with_multiple):
        total_nodes += len(component)
        total_nodes_by_limit[i+1] = total_nodes
    
    # Show how many nodes would be included with different limits
    print(f"\nNodes included by component limit:")
    for limit in [1, 3, 5, 10, 15, 20]:
        if limit in total_nodes_by_limit:
            print(f"  Limit {limit}: {total_nodes_by_limit[limit]} nodes")
        elif limit <= len(components_with_multiple):
            print(f"  Limit {limit}: Not enough multi-node components")



def create_in_reply_to_graph(emails):
    G = nx.DiGraph()
    email_data = {}

    msgid_to_node = {}
    for email_id, title, url, html_content in emails:
        parsed = parse_email_content(html_content)
        email_data[email_id] = parsed
        G.add_node(email_id, subject=parsed.get('subject', ''), author=parsed.get('from_author', ''), url=url)
        msgid = parsed.get('message_id')
        if msgid:
            msgid_to_node[msgid] = email_id

    edges_added = 0
    for email_id, data in email_data.items():
        parent_msgid = data.get('in_reply_to')
        if parent_msgid and parent_msgid in msgid_to_node:
            parent_node_id = msgid_to_node[parent_msgid]
            if not G.has_edge(parent_node_id, email_id):
                G.add_edge(parent_node_id, email_id, relationship='in_reply_to', weight=0.5)
                edges_added += 1

    print(f"Added {edges_added} in-reply-to edges")
    return G, email_data


def extract_patch_sig_and_version(subject):
    """
    Extracts the patch signature and Linux version from the patch email subject.
    Also gets version, and series information for the patch thread.
    """
    if subject is None:
        subject = ''
    patch_sig = extract_patch_signature_improved(subject)
    version_match = re.search(r'v(\d+)', subject)
    version_num = int(version_match.group(1)) if version_match else 1
    linux_match = re.search(r'\[PATCH\s+([0-9.]+)\]', subject)
    linux_version = linux_match.group(1) if linux_match else None
    series_match = re.search(r'(\d+)/(\d+)', subject)
    series_pos = int(series_match.group(1)) if series_match else None
    series_total = int(series_match.group(2)) if series_match else None
    return patch_sig, version_num, linux_version, series_pos, series_total


def _add_patch_nodes(G, emails):
    email_data = {}
    patch_nodes = {}
    for email_id, title, url, html_content in emails:
        parsed = parse_email_content(html_content)
        email_data[email_id] = parsed
        subject = parsed.get('subject') or ''
        chronological_order, _, _, _, _ = extract_temporal_info(email_data, email_id)
        patch_sig, version_num, linux_version, _, _ = extract_patch_sig_and_version(subject)
        if patch_sig and not subject.lower().startswith('re:'): #only have starting emails for threads be the roots
            patch_nodes[(patch_sig, linux_version, version_num)] = email_id
        G.add_node(email_id, subject=subject, author=parsed.get('from_author', ''), 
                   url=url, patch_signature=patch_sig, linux_version=linux_version, 
                   date=parsed.get('date', ''), chronological_order=chronological_order)
    return email_data, patch_nodes

def _add_patch_nodes_linux(G, emails):
    email_data = {}
    patch_nodes = defaultdict(list)
    for email_id, title, url, html_content in emails:
        parsed = parse_email_content(html_content)
        email_data[email_id] = parsed
        subject = parsed.get('subject') or ''
        chronological_order, version_num, series_pos, series_total, parsed_date = extract_temporal_info(email_data, email_id)
        patch_sig, version_num, linux_version, series_pos, series_total = extract_patch_sig_and_version(subject)
        is_patch = '[PATCH' in subject.upper()
        G.add_node(email_id, subject=subject, author=parsed.get('from_author', ''), url=url,
                   patch_signature=patch_sig, version_num=version_num, linux_version=linux_version,
                   series_pos=series_pos, series_total=series_total, is_patch=is_patch,
                   chronological_order=chronological_order, parsed_date=parsed_date)
        if is_patch and patch_sig:
            patch_nodes[(patch_sig, linux_version)].append(email_id)
    return email_data, patch_nodes

def _add_patch_nodes_and_metadata(G, emails):
    """
    get data from patch signatures for the version, series position 
    """
    email_data = {}
    patch_nodes = defaultdict(list)  # patch_sig -> list of email_ids
    for email_id, title, url, html_content in emails:
        parsed = parse_email_content(html_content)
        email_data[email_id] = parsed
        subject = parsed.get('subject', '')
        patch_sig = extract_patch_signature_improved(subject)
        version_match = re.search(r'v(\d+)', subject)
        version_num = int(version_match.group(1)) if version_match else 1
        series_match = re.search(r'(\d+)/(\d+)', subject)
        series_pos = int(series_match.group(1)) if series_match else None
        series_total = int(series_match.group(2)) if series_match else None
        is_patch = '[PATCH' in subject.upper()
        G.add_node(email_id, subject=subject, author=parsed.get('from_author', ''), url=url,
                   patch_signature=patch_sig, version_num=version_num,
                   series_pos=series_pos, series_total=series_total, is_patch=is_patch)
        if is_patch and patch_sig:
            patch_nodes[patch_sig].append(email_id)
    return email_data, patch_nodes

def _add_patch_evolution_and_series_edges_linux(G, patch_nodes):
    for (patch_sig, linux_version), email_ids in patch_nodes.items():
        # Sort by version, then series position
        sorted_ids = sorted(email_ids, key=lambda eid: (
            G.nodes[eid]['version_num'],
            G.nodes[eid]['series_pos'] if G.nodes[eid]['series_pos'] is not None else 0
        ))
        for i in range(len(sorted_ids) - 1):
            curr_id = sorted_ids[i]
            next_id = sorted_ids[i + 1]
            curr_ver = G.nodes[curr_id]['version_num']
            next_ver = G.nodes[next_id]['version_num']
            curr_series = G.nodes[curr_id]['series_pos']
            next_series = G.nodes[next_id]['series_pos']
            if next_ver > curr_ver:
                G.add_edge(curr_id, next_id, relationship='version_evolution', weight=2.0)
            elif next_series and curr_series and next_series > curr_series and curr_ver == next_ver:
                G.add_edge(curr_id, next_id, relationship='series_progression', weight=1.5)

def _add_reply_edges(G, email_data):
    # Connect replies only to their direct parent
    msgid_to_node = {data.get('message_id'): eid for eid, data in email_data.items() if data.get('message_id')}
    for eid, data in email_data.items():
        parent_msgid = data.get('in_reply_to')
        if parent_msgid and parent_msgid in msgid_to_node:
            parent_id = msgid_to_node[parent_msgid]
            if not G.has_edge(parent_id, eid):
                G.add_edge(parent_id, eid, relationship='reply', weight=1.0)

def create_patch_evolution_graph_linux(emails):
    G = nx.DiGraph()
    email_data, patch_nodes = _add_patch_nodes_linux(G, emails)
    _add_patch_evolution_and_series_edges_linux(G, patch_nodes)
    _add_reply_edges(G, email_data)
    print(f"Created patch evolution graph (with Linux version) with {len(G.nodes())} nodes and {len(G.edges())} edges")
    return G, email_data



def _add_version_evolution_edges(G, patch_nodes):
    for (patch_sig, linux_version, version_num), email_id in patch_nodes.items():
        # Find all patch nodes with the same signature and linux_version
        patch_versions = []
        for node_id in G.nodes:
            node = G.nodes[node_id]
            if (node.get('patch_signature') == patch_sig and
                node.get('linux_version') == linux_version and
                node_id != email_id and
                not node['subject'].lower().startswith('re:')):
                patch_versions.append((node.get('version_num', 1), node_id))
        patch_versions.append((G.nodes[email_id].get('version_num', 1), email_id))
        patch_versions.sort()
        for i in range(len(patch_versions) - 1):
            v1_id = patch_versions[i][1]
            v2_id = patch_versions[i+1][1]
            if not G.has_edge(v1_id, v2_id):
                G.add_edge(v1_id, v2_id, relationship='version_evolution', weight=2.0)


def _add_patch_edges(G, email_data, patch_nodes):
    for email_id, parsed in email_data.items():
        subject = parsed.get('subject') or ''
        patch_sig, version_num, linux_version, _, _ = extract_patch_sig_and_version(subject)
        if subject.lower().startswith('re:') and patch_sig:
            patch_key = (patch_sig, linux_version, version_num)
            patch_node_id = patch_nodes.get(patch_key)
            
            if patch_node_id and patch_node_id != email_id:
                G.add_edge(patch_node_id, email_id, relationship='reply_to_patch', weight=1.0)


def create_patch_name_version_graph(emails):
    G = nx.DiGraph()
    email_data, patch_nodes = _add_patch_nodes(G, emails)
    _add_patch_edges(G, email_data, patch_nodes)
    _add_version_evolution_edges(G, patch_nodes)
    print(f"Created patch name/version graph with {len(G.nodes())} nodes and {len(G.edges())} edges")
    return G, email_data


