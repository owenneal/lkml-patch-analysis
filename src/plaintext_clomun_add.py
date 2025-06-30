from git_pull_case_study import get_best_email_body
import sqlite3
from tqdm import tqdm


BATCH_SIZE = 1000



def add_text_column_to_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Try to add the column; ignore error if it already exists
    try:
        cursor.execute("ALTER TABLE mails ADD COLUMN plaintext_body TEXT")
        print("Added plaintext_body column.")
    except sqlite3.OperationalError:
        print("plaintext_body column already exists.")

    conn.commit()
    conn.close()



def batch_update_plaintext_body(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count how many need updating
    cursor.execute("SELECT COUNT(*) FROM mails WHERE plaintext_body IS NULL OR plaintext_body = ''")
    total = cursor.fetchone()[0]
    print(f"Total emails to process: {total}")

    offset = 0
    with tqdm(total=total) as pbar:
        while True:
            cursor.execute(
                "SELECT id, html_content FROM mails WHERE plaintext_body IS NULL OR plaintext_body = '' LIMIT ?", (BATCH_SIZE,)
            )
            rows = cursor.fetchall()
            if not rows:
                break

            for email_id, html_content in rows:
                plaintext = get_best_email_body(html_content)
                cursor.execute(
                    "UPDATE mails SET plaintext_body=? WHERE id=?",
                    (plaintext, email_id)
                )
                pbar.update(1)

            conn.commit()  # Commit after each batch

    conn.close()
    print("Done.")

if __name__ == "__main__":
    batch_update_plaintext_body("lkml-data-2024.db")