"""Run with the existing core interpreter and working directory; SELECT only."""
import json
import sys
from datetime import date,datetime
from pathlib import Path


def main():
    from app.shared.database import engine
    from sqlalchemy import text
    target=Path(sys.argv[1])
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        rows=[dict(r) for r in connection.execute(text('SELECT * FROM library_songs ORDER BY title')).mappings()]
        connection.rollback()
    for row in rows:
        row.pop('user_id',None);row.pop('platform_url',None)
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(rows,ensure_ascii=False,default=lambda v:v.isoformat() if isinstance(v,(date,datetime)) else str(v)))
    temporary.chmod(0o600);temporary.replace(target)
    print(json.dumps({'exported':len(rows)}))


if __name__=='__main__':main()
