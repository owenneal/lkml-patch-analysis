"""
Case study analysis for patch merging status detection.


Relies on a heuristic approach to analyze email threads and patch signatures
to determine the likelihood of patches being merged into the main codebase.

The mailing list does not provide explicit merge indicators, so we infer
merge status based on community engagement, version progression, and
community feedback. Mainter replies and terminology are not standardized,
so we use a combination of heuristics to identify merge signals.

For example, we look for phrases like "queued to", "merged to",
"committed to", and "applied_to_official_tree" in email subjects or bodies.
"""

import networkx as nx
from typing import Dict, List
from collections import defaultdict
from email_parser import extract_patch_signature_improved

def analyze_patch_merge_status(G: nx.DiGraph, email_data: Dict) -> Dict:
    """
    Analyze patches to determine their likely merge status.
    """
    patch_analysis = {}
    
    # group patches by signature
    patch_groups = defaultdict(list)
    for node_id in G.nodes():
        email = email_data.get(node_id, {})
        if email.get('patch_info'):
            subject = email.get('subject', '')
            signature = extract_patch_signature_improved(subject)
            if signature:
                patch_groups[signature].append(node_id)
    
    print(f"Analyzing {len(patch_groups)} patch families for merge status...")
    
    for signature, patch_ids in patch_groups.items():
        if len(patch_ids) > 1:  # Multi-version patches
            analysis = analyze_patch_family(G, email_data, patch_ids, signature)
            patch_analysis[signature] = analysis
    
    return patch_analysis

def analyze_patch_family(G: nx.DiGraph, email_data: Dict, patch_ids: List[int], signature: str) -> Dict:
    """
    Analyze a single patch family for merge indicators.
    """
    # sort patches by version
    sorted_patches = sorted(patch_ids, key=lambda x: G.nodes[x].get('version_num', 0))
    
    merge_signals = []
    total_confidence = 0.0
    latest_version = 0
    reply_count = 0
    positive_feedback = 0
    
    # analyze each patch and its replies
    for patch_id in sorted_patches:
        email = email_data.get(patch_id, {})
        merge_info = email.get('merge_info', {})
        
        latest_version = max(latest_version, G.nodes[patch_id].get('version_num', 0))
        total_confidence += merge_info.get('confidence_score', 0)
        merge_signals.extend(merge_info.get('merge_signals', []))
        
        # count replies to this patch
        for successor in G.successors(patch_id):
            successor_email = email_data.get(successor, {})
            successor_subject = successor_email.get('subject', '')
            
            if successor_subject and successor_subject.lower().startswith('re:'):
                reply_count += 1
                
                # check for positive feedback
                body = successor_email.get('body_text', '').lower()
                if any(phrase in body for phrase in ['looks good', 'lgtm', 'nice work', 'approved']):
                    positive_feedback += 1
    
    # Calculate merge probability
    merge_probability = calculate_merge_probability(
        total_confidence, len(sorted_patches), latest_version, 
        reply_count, positive_feedback, merge_signals
    )
    
    return {
        'signature': signature,
        'total_versions': len(sorted_patches),
        'latest_version': latest_version,
        'reply_count': reply_count,
        'positive_feedback': positive_feedback,
        'merge_signals': list(set(merge_signals)),
        'confidence_score': total_confidence,
        'merge_probability': merge_probability,
        'status': determine_status(merge_probability)
    }

def calculate_merge_probability(confidence: float, versions: int, latest_version: int, 
                               replies: int, positive: int, signals: List[str]) -> float:
    """
    Calculate probability that a patch was merged based on maintainer signals.
    Simplified to focus on reliable indicators.
    """
    probability = 0.0
    
    # Maintainer approval signals (main indicator)
    maintainer_approval_signals = [s for s in signals if 'maintainer_' in s and any(
        approval in s for approval in ['acked_by', 'reviewed_by', 'tested_by']
    )]
    
    # + 30% for each maintainer approval signal
    # still leave room for other signals
    # max the contribution to 70% to avoid overconfidence and false positives
    if maintainer_approval_signals:
        # Multiple maintainer approvals = very high confidence
        probability += min(len(maintainer_approval_signals) * 0.3, 0.7)
    
    # Very strong definitive signals
    # these phrases are clear indicators of merge or acceptance
    # e.g., "applied, thanks", "queued for", "will be merged
    definitive_signals = [s for s in signals if any(
        definitive in s for definitive in ['applied, thanks', 'thanks, applied', 'queued for', 'will be merged']
    )]
    
    if definitive_signals:
        probability += 0.8  # Very high confidence
    
    # Community engagement (secondary factor)
    #probably remove this, community engagement is not a strong indicator and could
    # just mean that the patch is under discussion
    if replies > 2 and positive > 0:
        engagement_score = min((positive / replies) * 0.2, 0.15)
        probability += engagement_score
    
    # Version progression (shows active development)
    # if there are multiple versions, it indicates ongoing work
    # and potential acceptance into the codebase
    if versions > 1:
        probability += min(versions * 0.05, 0.15)
    
    # Penalty for no maintainer signals
    # If there are no maintainer signals or definitive signals, reduce confidence
    # to avoid false positives
    if not maintainer_approval_signals and not definitive_signals:
        probability = max(probability - 0.3, 0.0)
    
    return min(probability, 1.0)

def determine_status(probability: float) -> str:
    """
    Convert probability to human-readable status.
    Updated thresholds to be more conservative.
    """
    if probability >= 0.85:
        return "Very Likely Merged"
    elif probability >= 0.65:
        return "Likely Merged"
    elif probability >= 0.45:
        return "Possibly Merged"
    elif probability >= 0.25:
        return "Under Review"
    elif probability >= 0.1:
        return "Uncertain"
    else:
        return "Likely Rejected"

def generate_case_study_report(patch_analysis: Dict) -> None:
    """
    Generate a detailed case study report.
    """
    print("\n" + "="*60)
    print("PATCH MERGE STATUS CASE STUDY REPORT")
    print("="*60)
    
    # Sort by merge probability
    sorted_patches = sorted(
        patch_analysis.items(), 
        key=lambda x: x[1]['merge_probability'], 
        reverse=True
    )
    
    print(f"\nAnalyzed {len(sorted_patches)} patch families:")
    print("-" * 60)
    
    status_counts = defaultdict(int)
    
    for signature, analysis in sorted_patches[:15]:  # Top 15
        status = analysis['status']
        status_counts[status] += 1
        
        print(f"\nPatch: {signature[:50]}...")
        print(f"  Status: {status} ({analysis['merge_probability']:.2%})")
        print(f"  Versions: {analysis['total_versions']} (latest: v{analysis['latest_version']})")
        print(f"  Community: {analysis['reply_count']} replies, {analysis['positive_feedback']} positive")
        
        if analysis['merge_signals']:
            print(f"  Signals: {', '.join(analysis['merge_signals'][:3])}")
    
    print(f"\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    for status, count in status_counts.items():
        percentage = (count / len(sorted_patches)) * 100
        print(f"{status}: {count} patches ({percentage:.1f}%)")


def verify_merge_indicators(patch_analysis: Dict, email_data: Dict, G: nx.DiGraph) -> None:
    """
    Verify merge indicators by showing actual email content that triggered the detection.
    """
    print("\n" + "="*70)
    print("MERGE INDICATOR VERIFICATION")
    print("="*70)
    
    # Sort by merge probability and show top candidates
    sorted_patches = sorted(
        patch_analysis.items(), 
        key=lambda x: x[1]['merge_probability'], 
        reverse=True
    )
    
    print("\nTop 5 patches with highest merge probability:")
    print("-" * 70)
    
    for i, (signature, analysis) in enumerate(sorted_patches[:5]):
        print(f"\n{i+1}. {signature[:60]}...")
        print(f"   Status: {analysis['status']} ({analysis['merge_probability']:.2%})")
        print(f"   Signals detected: {analysis['merge_signals']}")
        
        # Find the patch IDs for this signature
        patch_ids = []
        for node_id in G.nodes():
            email = email_data.get(node_id, {})
            if email.get('patch_info'):
                from email_parser import extract_patch_signature_improved
                node_signature = extract_patch_signature_improved(email.get('subject', ''))
                if node_signature == signature:
                    patch_ids.append(node_id)
        
        # Show evidence from actual emails
        show_merge_evidence(patch_ids, email_data, G, limit=2)

def show_merge_evidence(patch_ids: List[int], email_data: Dict, G: nx.DiGraph, limit: int = 2) -> None:
    """
    Show actual email content that contains merge indicators.
    """
    evidence_count = 0
    
    for patch_id in patch_ids:
        if evidence_count >= limit:
            break
            
        email = email_data.get(patch_id, {})
        merge_info = email.get('merge_info', {})
        
        if merge_info.get('merge_signals'):
            print(f"\n   📧 Email {patch_id} evidence:")
            print(f"      Subject: {email.get('subject', 'Unknown')[:50]}...")
            print(f"      Signals: {merge_info.get('merge_signals')}")
            
            # Show relevant content snippets
            body_text = email.get('body_text', '') or email.get('message_body', '')
            if body_text:
                show_relevant_snippets(body_text, merge_info.get('merge_signals', []))
            
            evidence_count += 1
        
        # Also check replies to this patch
        for successor_id in G.successors(patch_id):
            if evidence_count >= limit:
                break
                
            successor_email = email_data.get(successor_id, {})
            successor_merge_info = successor_email.get('merge_info', {})
            
            if successor_merge_info.get('merge_signals'):
                print(f"\n   📧 Reply {successor_id} evidence:")
                print(f"      Subject: {successor_email.get('subject', 'Unknown')[:50]}...")
                print(f"      Signals: {successor_merge_info.get('merge_signals')}")
                
                body_text = successor_email.get('body_text', '') or successor_email.get('message_body', '')
                if body_text:
                    show_relevant_snippets(body_text, successor_merge_info.get('merge_signals', []))
                
                evidence_count += 1

def show_relevant_snippets(content: str, signals: List[str], context_chars: int = 300) -> None:
    """
    Show snippets of content around detected signals.
    """
    content_lower = content.lower()
    shown_any = False

    for signal in signals:
        start_idx = 0
        while True:
            signal_pos = content_lower.find(signal, start_idx)
            if signal_pos == -1:
                break
            start = max(0, signal_pos - context_chars // 2)
            end = min(len(content), signal_pos + len(signal) + context_chars // 2)
            snippet = content[start:end].strip()
            # Highlight the signal
            snippet_highlighted = snippet.replace(
                content[signal_pos:signal_pos+len(signal)],
                f"\033[93m{content[signal_pos:signal_pos+len(signal)]}\033[0m"
            )
            print(f"      Context: ...{snippet_highlighted}...")
            shown_any = True
            start_idx = signal_pos + len(signal)
    if not shown_any:
        print("      (No context found for signals)")

def generate_merge_indicators_text_report(patch_analysis: Dict, email_data: Dict, G: nx.DiGraph, output_file: str = "merge_indicators_report.txt") -> None:
    """
    Generate a text file report showing patches with merge indicators and their evidence.
    """
    from datetime import datetime
    
    # Sort by merge probability
    sorted_patches = sorted(
        patch_analysis.items(), 
        key=lambda x: x[1]['merge_probability'], 
        reverse=True
    )
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("PATCH MERGE INDICATORS REPORT\n")
        f.write("="*80 + "\n")
        f.write(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Analyzed {len(sorted_patches)} patch families\n\n")
        
        # High probability patches
        f.write("HIGH PROBABILITY PATCHES (>= 70%)\n")
        f.write("-" * 50 + "\n")
        high_prob_patches = [p for p in sorted_patches if p[1]['merge_probability'] >= 0.7]
        
        if high_prob_patches:
            write_patch_section(f, high_prob_patches, email_data, G, limit=20)
        else:
            f.write("No high probability patches found.\n")
        
        f.write("\n" + "="*80 + "\n\n")
        
        # Medium probability patches
        f.write("MEDIUM PROBABILITY PATCHES (30% - 70%)\n")
        f.write("-" * 50 + "\n")
        med_prob_patches = [p for p in sorted_patches if 0.3 <= p[1]['merge_probability'] < 0.7]
        
        if med_prob_patches:
            write_patch_section(f, med_prob_patches, email_data, G, limit=15)
        else:
            f.write("No medium probability patches found.\n")
        
        f.write("\n" + "="*80 + "\n\n")
        
        # Low probability patches (just first few for reference)
        f.write("LOW PROBABILITY PATCHES (< 30%) - Sample\n")
        f.write("-" * 50 + "\n")
        low_prob_patches = [p for p in sorted_patches if p[1]['merge_probability'] < 0.3][:10]
        
        if low_prob_patches:
            write_patch_section(f, low_prob_patches, email_data, G, limit=10)
        else:
            f.write("No low probability patches found.\n")
        
        # Summary statistics
        f.write("\n" + "="*80 + "\n")
        f.write("SUMMARY STATISTICS\n")
        f.write("="*80 + "\n")
        
        status_counts = {}
        for _, analysis in sorted_patches:
            status = analysis['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in status_counts.items():
            percentage = (count / len(sorted_patches)) * 100
            f.write(f"{status}: {count} patches ({percentage:.1f}%)\n")
    
    print(f"\n✅ Text report generated: {output_file}")

def write_patch_section(f, patches, email_data, G, limit=20):
    """Helper function to write a section of patches to the text file"""
    
    for i, (signature, analysis) in enumerate(patches[:limit]):
        f.write(f"\n{i+1}. PATCH: {signature}\n")
        f.write(f"   Status: {analysis['status']} ({analysis['merge_probability']:.2%})\n")
        f.write(f"   Versions: {analysis['total_versions']} (latest: v{analysis['latest_version']})\n")
        f.write(f"   Community: {analysis['reply_count']} replies, {analysis['positive_feedback']} positive\n")
        f.write(f"   Signals: {', '.join(analysis['merge_signals'][:10])}\n")
        
        # Find the patch IDs for this signature
        patch_ids = []
        for node_id in G.nodes():
            email = email_data.get(node_id, {})
            if email.get('patch_info'):
                from email_parser import extract_patch_signature_improved
                node_signature = extract_patch_signature_improved(email.get('subject', ''))
                if node_signature == signature:
                    patch_ids.append(node_id)
        
        # Show evidence
        f.write(f"   EVIDENCE:\n")
        evidence_count = 0
        
        for patch_id in patch_ids:
            if evidence_count >= 3:  # Limit evidence per patch
                break
                
            email = email_data.get(patch_id, {})
            merge_info = email.get('merge_info', {})
            
            if merge_info.get('merge_signals'):
                f.write(f"\n   📧 Email {patch_id}:\n")
                f.write(f"      Subject: {email.get('subject', 'Unknown')}\n")
                f.write(f"      From: {email.get('from_author', 'Unknown')}\n")
                f.write(f"      Signals: {', '.join(merge_info.get('merge_signals', []))}\n")
                
                # Add text snippets
                body_text = email.get('body_text', '') or email.get('message_body', '')
                if body_text:
                    f.write(f"      Snippets:\n")
                    write_text_snippets(f, body_text, merge_info.get('merge_signals', []))
                
                evidence_count += 1
            
            # Check replies to this patch
            for successor_id in G.successors(patch_id):
                if evidence_count >= 3:
                    break
                    
                successor_email = email_data.get(successor_id, {})
                successor_merge_info = successor_email.get('merge_info', {})
                
                if successor_merge_info.get('merge_signals'):
                    f.write(f"\n   📧 Reply {successor_id}:\n")
                    f.write(f"      Subject: {successor_email.get('subject', 'Unknown')}\n")
                    f.write(f"      From: {successor_email.get('from_author', 'Unknown')}\n")
                    f.write(f"      Signals: {', '.join(successor_merge_info.get('merge_signals', []))}\n")
                    
                    body_text = successor_email.get('body_text', '') or successor_email.get('message_body', '')
                    if body_text:
                        f.write(f"      Snippets:\n")
                        write_text_snippets(f, body_text, successor_merge_info.get('merge_signals', []))
                    
                    evidence_count += 1
        
        f.write(f"\n" + "-"*70 + "\n")

def write_text_snippets(f, content: str, signals: list, context_chars: int = 200):
    """Write text snippets around detected signals with maintainer focus"""
    content_lower = content.lower()
    
    for signal in signals[:3]:  # Show max 3 signals per email
        # Clean signal for searching
        search_signal = signal.lower().replace('maintainer_', '').replace('_', '-')
        if search_signal.endswith('-by'):
            search_signal += ':'
        
        signal_pos = content_lower.find(search_signal)
        if signal_pos != -1:
            start = max(0, signal_pos - context_chars // 2)
            end = min(len(content), signal_pos + len(search_signal) + context_chars // 2)
            snippet = content[start:end].strip()
            
            # Categorize the signal
            if 'maintainer_' in signal:
                category = "MAINTAINER SIGNAL"
            elif any(strong in signal for strong in ['applied, thanks', 'thanks, applied', 'queued for']):
                category = "DEFINITIVE"
            else:
                category = "APPROVAL"
            
            # Mark the signal with brackets
            actual_signal_text = content[signal_pos:signal_pos+len(search_signal)]
            snippet_with_marker = snippet.replace(
                actual_signal_text,
                f"[{actual_signal_text}]"
            )
            
            f.write(f"        {signal} ({category}): ...{snippet_with_marker}...\n")
            break