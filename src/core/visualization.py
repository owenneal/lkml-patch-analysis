"""
Visualization functionality for LKML email graphs.

This module provides functions to visualize email relationship graphs
using Pyvis for interactive web-based visualizations.
"""

import networkx as nx
from pyvis.network import Network


def visualize_basic_graph(G, email_data, component_limit=5):
    """
    Create a basic interactive visualization.
    
    Args:
        G: NetworkX graph
        email_data: Dictionary of email data
        component_limit: Maximum number of components to include
    """
    components = list(nx.weakly_connected_components(G))
    components.sort(key=len, reverse=True)
    
    # Create a new graph with only the largest components
    nodes_to_include = set()
    for component in components[:component_limit]:
        if len(component) > 1:
            nodes_to_include.update(component)
    
    # Create subgraph
    subgraph = G.subgraph(nodes_to_include)
    
    # Create Pyvis network
    net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")
    
    # Add nodes
    for node in subgraph.nodes():
        email = email_data.get(node, {})
        subject = email.get('subject', f'Email {node}')
        author = email.get('from_author', 'Unknown')
        is_patch = G.nodes[node].get('is_patch', False)
        
        # Color based on patch vs reply
        color = "#4CAF50" if is_patch else "#FF9800"
        size = 25 if is_patch else 15
        
        net.add_node(node, 
                    label=str(node),
                    title=f"Subject: {subject}\nAuthor: {author}",
                    color=color,
                    size=size)
    
    # Add edges
    for edge in subgraph.edges():
        relationship = G.edges[edge].get('relationship', 'related')
        weight = G.edges[edge].get('weight', 1.0)
        
        color = "#00FF00" if relationship == 'same_patch_topic' else "#0080FF"
        
        net.add_edge(edge[0], edge[1], 
                    title=relationship,
                    color=color,
                    width=weight*3)
    
    # Configure physics
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "stabilization": {"iterations": 100}
        }
    }
    """)
    
    # Save and show
    net.save_graph("email_graph_basic.html")
    print("Basic graph saved as 'email_graph_basic.html'")


def visualize_evolution_graph(G, email_data, component_limit=10, max_nodes=200, output_file="patch_evolution_graph.html"):
    """
    Create visualization showing patch evolution with temporal ordering.
    
    Args:
        G: NetworkX graph
        email_data: Dictionary of email data
        component_limit: Maximum number of components to include
        max_nodes: Maximum number of nodes to include
    """
    components = list(nx.weakly_connected_components(G))
    components.sort(key=len, reverse=True)
    
    # Filter to components with multiple nodes
    multi_node_components = [c for c in components if len(c) > 1]
    
    if not multi_node_components:
        print("No connected components found with multiple nodes!")
        return
    
    print(f"Found {len(multi_node_components)} components with evolution potential")
    
    # Select components and prioritize those with version evolution
    selected_components = []
    for component in multi_node_components[:component_limit]:
        # Check if this component has version evolution
        component_nodes = list(component)
        has_evolution = any(
            G.nodes[node].get('version_num', 0) > 1 
            for node in component_nodes
        )
        
        if has_evolution:
            selected_components.insert(0, component)
        else:
            selected_components.append(component)
    
    nodes_to_include = set()
    for component in selected_components:
        if len(nodes_to_include) + len(component) <= max_nodes:
            nodes_to_include.update(component)
        else:
            break
    
    print(f"Including {len(nodes_to_include)} nodes from {len(selected_components)} components")
    
    subgraph = G.subgraph(nodes_to_include).copy()
    self_loops = list(nx.selfloop_edges(subgraph))
    subgraph.remove_edges_from(self_loops)
    
    print(f"Visualizing {subgraph.number_of_nodes()} nodes and {subgraph.number_of_edges()} edges")
    
    net = Network(
        height="900px", 
        width="100%", 
        bgcolor="#1a1a1a", 
        font_color="white",
        directed=True
    )
    
    component_colors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", 
                       "#00BCD4", "#FFEB3B", "#795548", "#607D8B", "#E91E63"]
    node_to_component = {}
    for i, component in enumerate(selected_components):
        for node in component:
            if node in nodes_to_include:
                node_to_component[node] = i
    
    for node in subgraph.nodes():
        email = email_data.get(node, {})
        subject = email.get('subject', f'Email {node}')[:40] + "..."
        author = email.get('from_author', 'Unknown')[:15]
        
        is_patch = G.nodes[node].get('is_patch', False)
        patch_version = G.nodes[node].get('patch_version', '')
        version_num = G.nodes[node].get('version_num', 0)
        series_info = G.nodes[node].get('series_info', '')
        component_idx = node_to_component.get(node, 0)
        base_color = component_colors[component_idx % len(component_colors)]
        
        if is_patch:
            if version_num > 1:
                size = 25 + (version_num * 5)
                color = base_color
                shape = "diamond"  
            else:
                size = 30
                color = base_color
                shape = "box" 
        else:
            size = 15
            color = base_color.replace("F", "A")
            shape = "circle"
       
        label = f"{node}"
        if patch_version:
            label += f"\n{patch_version}"
        if series_info:
            label += f"\n{series_info}"
        
        title_parts = [
            f"ID: {node}",
            f"Subject: {subject}",
            f"Author: {author}",
            f"Patch: {is_patch}",
            f"Component: {component_idx + 1}"
        ]
        
        if is_patch:
            title_parts.extend([
                f"Version: {patch_version}",
                f"Series: {series_info}" if series_info else "Series: Standalone"
            ])
        
        net.add_node(
            node, 
            label=label,
            title="\n".join(title_parts),
            color=color,
            size=size,
            shape=shape,
            font={"size": 10, "color": "white"}
        )
    
    # Add edges with evolution-aware styling
    for edge in subgraph.edges():
        if edge[0] != edge[1]:
            relationship = G.edges[edge].get('relationship', 'related')
            evolution_type = G.edges[edge].get('evolution_type', 'discussion')
            weight = G.edges[edge].get('weight', 1.0)
            
            # Style based on evolution type
            if evolution_type == 'version_upgrade':
                color = "#FF0080"  
                width = 6
                arrows = {"to": {"enabled": True, "scaleFactor": 2}}
                edge_title = f"Version Evolution: {relationship}"
            elif evolution_type == 'series_progression':
                color = "#FFFF00"  
                width = 5
                arrows = {"to": {"enabled": True, "scaleFactor": 1.5}}
                edge_title = f"Series Progression: {relationship}"
            elif relationship == 'same_patch_topic':
                color = "#00FF00" 
                width = 3
                arrows = {"to": {"enabled": False}}
                edge_title = f"Same Topic: {relationship}"
            else:
                color = "#00BFFF"  
                width = 2
                arrows = {"to": {"enabled": True, "scaleFactor": 1}}
                edge_title = f"Discussion: {relationship}"
            
            net.add_edge(
                edge[0], edge[1], 
                title=edge_title,
                color=color,
                width=width,
                arrows=arrows
            )
    
    # Fixed layout configuration
    net.set_options("""
    {
        "physics": {
            "enabled": false
        },
        "layout": {
            "hierarchical": {
                "enabled": true,
                "direction": "LR",
                "sortMethod": "directed",
                "levelSeparation": 400,
                "nodeSpacing": 250,
                "treeSpacing": 350,
                "blockShifting": true,
                "edgeMinimization": true,
                "parentCentralization": true
            }
        },
        "interaction": {
            "dragNodes": true,
            "dragView": true,
            "zoomView": true,
            "selectConnectedEdges": true,
            "hover": true
        },
        "nodes": {
            "fixed": {
                "x": false,
                "y": false
            }
        }
    }
    """)
    
    net.html = net.html.replace(
        '</body>',
        '''
        <div style="position: fixed; top: 10px; right: 10px; background: rgba(0,0,0,0.8); padding: 10px; border-radius: 5px;">
            <button onclick="togglePhysics()" style="background: #4CAF50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                Toggle Physics
            </button>
            <button onclick="fitNetwork()" style="background: #2196F3; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-left: 5px;">
                Fit View
            </button>
        </div>
        <script>
            function togglePhysics() {
                var enabled = network.physics.physicsEnabled;
                network.setOptions({physics: {enabled: !enabled}});
                console.log("Physics " + (enabled ? "disabled" : "enabled"));
            }
            function fitNetwork() {
                network.fit();
            }
        </script>
        </body>'''
    )
    
    net.save_graph(output_file)
    print(f"Patch evolution graph saved as '{output_file}'")