from bs4 import BeautifulSoup
import re
import os
import csv

def get_plaintext_body(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_before("\n")
    text = soup.get_text("\n")
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def get_best_email_body(html_content: str, parse_email_content_func=None) -> str:
    if not html_content:
        return ""
    body = ""
    if parse_email_content_func:
        parsed = parse_email_content_func(html_content)
        body = parsed.get('message_body', '') or ''
    if not body or body.count('\n') < 5 or len(body.splitlines()) <= 1:
        body = get_plaintext_body(html_content)
    return body


def clean_csv_final_report(input_path: str, output_path: str = None, remove_not_found: bool = True):
    """
    Cleans the final CSV report by removing rows with 'N/A' commit hashes and optionally removing rows
    where the commit hash is not found in the database.
    """
    if not os.path.exists(input_path):
        print(f"Input file {input_path} does not exist.")
        return
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_cleaned{ext}"
    
    cleaned_rows = []
    with open(input_path, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        header = next(reader)
        cleaned_rows.append(header)

        try:
            commit_hash_index = header.index('Merged_Commit_Hash')
            category_index = header.index('Vulnerability_Category')
        except ValueError:
            print("Merged_Commit_Hash column not found.")
            return

        for row in reader:
            if remove_not_found and row[commit_hash_index] == 'Not Found':
                continue

            # Clean the category field of llm output
            category = row[category_index]
            category = category.split('\n')[0]
            category = re.sub(r'^\d+\.\s*', '', category)
            row[category_index] = category.strip()

            # add all cleaning logic here
            cleaned_rows.append(row)

    with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerows(cleaned_rows)

    print(f"Cleaned report written to {output_path}")