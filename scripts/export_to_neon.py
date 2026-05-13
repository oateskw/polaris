"""
Export existing local SQLite data to SQL INSERT statements for Neon Postgres.

Usage:
    python scripts/export_to_neon.py > seed_neon.sql

Then paste the output into the Neon SQL editor.
"""
from polaris.config import get_settings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
session = Session()


def q(val):
    """Postgres-safe string quoting."""
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


def b(val):
    """Bool to Postgres literal."""
    if val is None:
        return "NULL"
    return "TRUE" if val else "FALSE"


print("-- Polaris data export for Neon Postgres")
print("-- Run this in the Neon SQL editor after running alembic migrations\n")

# instagram_accounts
rows = session.execute(text("SELECT * FROM instagram_accounts")).fetchall()
cols = session.execute(text("PRAGMA table_info(instagram_accounts)")).fetchall()
col_names = [c[1] for c in cols]
print("-- instagram_accounts")
for row in rows:
    vals = []
    for name, val in zip(col_names, row):
        if name in ("is_active",):
            vals.append(b(val))
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            vals.append(str(val) if val is not None else "NULL")
        else:
            vals.append(q(val))
    print(f"INSERT INTO instagram_accounts ({', '.join(col_names)}) VALUES ({', '.join(vals)}) ON CONFLICT (id) DO NOTHING;")

print()

# comment_triggers
rows = session.execute(text("SELECT * FROM comment_triggers")).fetchall()
cols = session.execute(text("PRAGMA table_info(comment_triggers)")).fetchall()
col_names = [c[1] for c in cols]
print("-- comment_triggers")
for row in rows:
    vals = []
    for name, val in zip(col_names, row):
        if name in ("is_active", "follow_up_enabled"):
            vals.append(b(val))
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            vals.append(str(val) if val is not None else "NULL")
        else:
            vals.append(q(val))
    print(f"INSERT INTO comment_triggers ({', '.join(col_names)}) VALUES ({', '.join(vals)}) ON CONFLICT (id) DO NOTHING;")

print()

# leads (existing leads so deduplication works correctly)
rows = session.execute(text("SELECT * FROM leads")).fetchall()
if rows:
    cols = session.execute(text("PRAGMA table_info(leads)")).fetchall()
    col_names = [c[1] for c in cols]
    print("-- leads (deduplication state)")
    for row in rows:
        vals = []
        for name, val in zip(col_names, row):
            if name in ("dm_sent",):
                vals.append(b(val))
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                vals.append(str(val) if val is not None else "NULL")
            else:
                vals.append(q(val))
        print(f"INSERT INTO leads ({', '.join(col_names)}) VALUES ({', '.join(vals)}) ON CONFLICT (id) DO NOTHING;")

session.close()
print("\n-- Done")
