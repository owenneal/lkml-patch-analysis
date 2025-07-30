import os
import json
import sqlite3

"""
This script imports CVE JSON files from a specified directory into an SQLite database.
It creates a table for CVE records and extracts relevant information from each JSON file.
It also creates a separate table for Linux kernel CVEs based on specific criteria.

Only for one time use really to get the cves and popualte a sqlite database.
It assumes the JSON files follow a specific structure as per the CVE JSON format. Made specifically for the 2024 CVEs.
"""
# use this repo to get the cvelist: https://github.com/CVEProject/cvelistV5
# how to download the list: https://github.com/CVEProject/cvelistV5#how-to-download-the-cve-list
CVE_ROOT_DIR = r"cvelistV5\cves\2024" # Adjust this path as needed to fit local desitination, to lead to the 2024 cve list
# Database path for storing CVE records, adjust as needed
# we decided to consolidate the cve related data into one db so this wil be the one
DB_PATH = "suspected_cve_patches.db" # again, change this as needed, i.e remove the lkml-patch-analysis/ if you have it in a different folder

def create_cve_json_table(db_path):
    """Create the cve_json_records table in the SQLite database if it does not exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cve_json_records (
            cve_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            cwe_id TEXT,
            vendor TEXT,
            product TEXT,
            reference_urls TEXT  -- comma-separated URLs
        )
    """)
    conn.commit()
    conn.close()

def insert_cve_json_records(db_path, record):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO cve_json_records
        (cve_id, title, description, cwe_id, vendor, product, reference_urls)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        record['cve_id'],
        record['title'],
        record['description'],
        record['cwe_id'],
        record['vendor'],
        record['product'],
        record['reference_urls']
    ))
    conn.commit()
    conn.close()

def extract_info_from_json(json_data):
    """
    Extracts data from the CVE JSON structure.
    Returns a dictionary with the relevant fields.
    """
    cve_id = json_data.get("cveMetadata", {}).get("cveId", "")
    cna = json_data.get("containers", {}).get("cna", {})
    title = cna.get("title", "")
    description = ""
    for desc in cna.get("descriptions", []):
        if desc.get("lang") == "en":
            description = desc.get("value", "")
            break

    cwe_id = ""
    for pt in cna.get("problemTypes", []):
        for desc in pt.get("descriptions", []):
            if desc.get("lang") == "en" and "cweId" in desc:
                cwe_id = desc["cweId"]
                break
    vendor = ""
    product = ""
    affected = cna.get("affected", [])
    if affected:
        vendor = affected[0].get("vendor", "")
        product = affected[0].get("product", "")
    reference_urls = ",".join(ref.get("url", "") for ref in cna.get("references", []))
    return {
        "cve_id": cve_id,
        "title": title,
        "description": description,
        "cwe_id": cwe_id,
        "vendor": vendor,
        "product": product,
        "reference_urls": reference_urls
    }


def main():
    create_cve_json_table(DB_PATH)
    count = 0
    for root, dirs, files in os.walk(CVE_ROOT_DIR):
        for fname in files:
            if fname.endswith(".json"):
                file_path = os.path.join(root, fname)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    record = extract_info_from_json(data)
                    if record['cve_id']:
                        insert_cve_json_records(DB_PATH, record)
                        count += 1
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
    print(f"Inserted {count} CVE records into the database.")


def create_linux_kernel_table(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Create the new table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS linux_kernel_cves AS
        SELECT * FROM cve_json_records WHERE 0
    """)
    # Insert Linux kernel CVEs
    cursor.execute("""
        INSERT OR IGNORE INTO linux_kernel_cves
        SELECT * FROM cve_json_records
        WHERE LOWER(title) LIKE '%linux kernel%'
           OR LOWER(description) LIKE '%linux kernel%'
           OR LOWER(vendor) = 'linux'
           OR LOWER(product) = 'kernel'
    """)
    conn.commit()
    conn.close()
    print("linux_kernel_cves table created and populated.")

if __name__ == "__main__":
    #main()
    create_linux_kernel_table(DB_PATH)
