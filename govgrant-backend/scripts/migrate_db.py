import sqlite3
import os

db_path = "govgrant.db"

if os.path.exists(db_path):
    print(f"Updating {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List of tables and columns to ensure exist
    migrations = [
        ("raw_schemes", "documents_json"),
        ("raw_schemes", "steps_json"),
        ("ranked_schemes", "documents_json"),
        ("ranked_schemes", "steps_json"),
    ]

    for table, column in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
            print(f"Added column {column} to {table}.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"Column {column} already exists in {table}.")
            else:
                print(f"Error updating {table}.{column}: {e}")
        
    conn.commit()
    conn.close()
    print("Database migration complete.")
else:
    print("Database not found. It will be created automatically on next run.")
