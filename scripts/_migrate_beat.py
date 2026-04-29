"""Check existing columns and run migration."""
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL", "")
print(f"Connecting to DB...")
e = create_engine(db_url)

with e.begin() as c:
    # Check existing columns
    cols = c.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='library_songs' ORDER BY ordinal_position"
    )).fetchall()
    col_names = [r[0] for r in cols]
    print(f"Existing columns ({len(col_names)}): {col_names}")

    new_cols = {
        "beat_confidence": "FLOAT",
        "beat_grid_offset": "FLOAT",
        "beat_grid_interval": "FLOAT",
        "beat_engines_used": "JSON DEFAULT '[]' NOT NULL",
        "beat_needs_review": "INTEGER DEFAULT 0 NOT NULL",
    }

    for col, col_type in new_cols.items():
        if col in col_names:
            print(f"  Column '{col}' already exists, skipping.")
        else:
            sql = f"ALTER TABLE library_songs ADD COLUMN {col} {col_type}"
            print(f"  Adding column: {sql}")
            c.execute(text(sql))

    # Verify
    cols2 = c.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='library_songs' ORDER BY ordinal_position"
    )).fetchall()
    print(f"\nFinal columns ({len(cols2)}): {[r[0] for r in cols2]}")
    print("Migration complete!")
