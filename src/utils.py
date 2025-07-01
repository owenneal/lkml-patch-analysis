from bs4 import BeautifulSoup
import re

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
    body = ""
    if parse_email_content_func:
        parsed = parse_email_content_func(html_content)
        body = parsed.get('message_body', '') or ''
    if not body or body.count('\n') < 5 or len(body.splitlines()) <= 1:
        body = get_plaintext_body(html_content)
    return body