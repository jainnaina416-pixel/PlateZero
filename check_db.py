import sqlite3
import os

def check_db(db_path):
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return
    print(f"--- Checking {db_path} ---")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table_name in tables:
        print(f"\nTable: {table_name[0]}")
        cursor.execute(f"SELECT * FROM {table_name[0]} LIMIT 5;")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row}")
    conn.close()

if __name__ == "__main__":
    check_db("QR_attendance/platezero.db")
    check_db("QR_attendance/auth.db")
    check_db("image_hashes.db")
