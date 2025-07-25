import requests
import sqlite3
import re


def create_maintainer_DB():
    conn = sqlite3.connect('./maintainers.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maintainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            subsystem TEXT,
            role TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    return conn


# doesnt work, cant make requests to kernel.org
def scrape_maintainers_from_kernel_org():
    maintainers = []
    url = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/MAINTAINERS"

    try:
        res = requests.get(url)
        res.raise_for_status()
        content = res.text

        maintainers = parse_maintainers(content)

    except requests.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        maintainers = []

    return maintainers


def scrape_maintainers_from_github():
    """
    Scrape maintainer information from GitHub mirror of Linux kernel.
    """
    maintainers = []
    
    # use GitHub's raw content URL
    url = "https://raw.githubusercontent.com/torvalds/linux/master/MAINTAINERS"
    
    headers = {
        'User-Agent': 'Linux-Kernel-Research-Tool/1.0',
        'Accept': 'text/plain',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        content = response.text
        
        # Parse MAINTAINERS file
        maintainers = parse_maintainers(content)
        
    except Exception as e:
        print(f"Error fetching MAINTAINERS file from GitHub: {e}")
        print("Using fallback list of known maintainers...")
    
    return maintainers

'''
Function to find maintainers in the content of the MAINTAINERS file.
It parses the content line by line, identifying maintainers and their roles.
'''
def parse_maintainers(content):
    maintainers = []
    current_subsystem = None
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line =lines[i].strip()

        if not line or line.startswith('#'):
            i += 1
            continue

        # each subsystem starts with an uppercase letter and is not a maintainer or reviewer line
        if line.isupper() and not line.startswith(('M:', 'R:', 'L:', 'F:', 'T:', 'S:')):
            current_subsystem = line
            i += 1
            continue

        if line.startswith('M:'): # maintainer line
            email_match = re.search(r'<([^>]+)>', line)
            name_match = re.search(r'M:\s*([^<]+)', line)

            if email_match and name_match:
                maintainers.append({
                    'name': name_match.group(1).strip(),
                    'email': email_match.group(1).strip(),
                    'subsystem': current_subsystem,
                    'role': 'Maintainer'
                })

        elif line.startswith('R:'):  # reviewer line
            email_match = re.search(r'<([^>]+)>', line)
            name_match = re.search(r'R:\s*([^<]+)', line)
            if email_match and name_match:
                maintainers.append({
                    'name': name_match.group(1).strip(),
                    'email': email_match.group(1).strip(),
                    'subsystem': current_subsystem,
                    'role': 'Reviewer'
                })
        
        i += 1
    return maintainers

def store_maintainers_in_db():
    print("Creating database...")
    conn = create_maintainer_DB()
    cursor = conn.cursor()
    print("Scraping maintainers from kernel.org...")
    #maintainers = scrape_maintainers_from_kernel_org()
    maintainers = scrape_maintainers_from_github()

    print(f"Found {len(maintainers)} maintainers. Storing in database...")

    for maintainer in maintainers:
        try:
            cursor.execute('''
                INSERT INTO maintainers (name, email, subsystem, role)
                VALUES (?, ?, ?, ?)
            ''', (
                maintainer['name'], 
                maintainer['email'], 
                maintainer['subsystem'], 
                maintainer['role']
                ))
        except sqlite3.IntegrityError:
            print(f"Maintainer {maintainer['email']} already exists in the database.")

    conn.commit()
    print("Database updated successfully.")

    #printing some statistics
    cursor.execute('SELECT COUNT(*) FROM maintainers')
    total_maintainers = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(DISTINCT subsystem) FROM maintainers')
    total_subsystems = cursor.fetchone()[0]

    print(f"Total maintainers: {total_maintainers}")
    print(f"Total subsystems: {total_subsystems}")
    conn.close()

if __name__ == "__main__":
    store_maintainers_in_db()
    print("Maintainer scraping and storage completed.")