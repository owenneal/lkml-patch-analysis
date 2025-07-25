from ..core.data_access import get_patch_emails
from ..core.email_parser import parse_email_content, extract_patch_signature_improved, extract_patch_info
from collections import defaultdict


"""
Simple script to find the version numbers for patch threads and help determine the quality of the patch based
on the max number, the idea is assuming that if a patch goes through multiple versions then it started as not
acceptable before being refactored overtime to be merge ready. 

Exports the information into a text file.
"""


def label_patch_quality(emails):


    """
    Labels the patches based on their version numbers.
    Patches with versions <= 2 are labeled "good", versions >= 5 are labeled "bad",
    and versions between 3 and 4 are labeled "average".
    """
    patch_versions = defaultdict(set)
    patch_subjects = defaultdict(list)

    for email_id, title, url, html_content in emails:
        parsed = parse_email_content(html_content)
        if not parsed:
            continue
        subject = parsed.get('subject', '') or title or ""
        sig = extract_patch_signature_improved(subject)
        patch_info = extract_patch_info(subject)
        if sig and patch_info and patch_info.get("version"):
            version_str = patch_info["version"].strip("vV")
            try:
                version = int(version_str)
            except Exception:
                version = 1
            patch_versions[sig].add(version)
            patch_subjects[sig].append((email_id, subject, url, version))

    # Now label the patches based on their versions
    # 
    results = []
    for sig, versions in patch_versions.items():
        max_version = max(versions)
        if max_version <= 2:
            label = "good"
        elif max_version >= 5:
            label = "bad"
        else:
            label = "average"
        for email_id, subject, url, version in patch_subjects[sig]:
            results.append({
                "email_id": email_id,
                "subject": subject,
                "url": url,
                "patch_signature": sig,
                "patch_version": version,
                "max_version": max_version,
                "label": label
            })

    return results


def main(limit = 10000, output_file = "patch_quality_labels.txt"):
    """
    Main function to fetch patch emails, label their quality, and write results to a file.
    """
    emails = get_patch_emails(limit)
    labeled_patches = label_patch_quality(emails)

    print(f"Labeled {len(labeled_patches)} patch emails.")
    with open(output_file, "w", encoding="utf-8") as f:
        for entry in labeled_patches:
            f.write(f"{entry['email_id']}\t{entry['label']}\tv{entry['patch_version']}/v{entry['max_version']}\t{entry['patch_signature']}\t{entry['subject']}\n")
    print(f"Results written to {output_file}")
if __name__ == "__main__":
    main()