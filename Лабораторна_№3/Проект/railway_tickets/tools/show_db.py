"""Перегляд вмісту таблиць БД:  python tools/show_db.py [Таблиця] [кількість рядків]"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "railway.db")
TABLES = ["Users", "Sessions", "Trains", "Trips", "Tickets", "Ratings", "RequestLog"]


def show(conn, table, limit):
    cur = conn.execute("SELECT * FROM %s ORDER BY Id DESC LIMIT ?" % table, (limit,))
    cols = [d[0] for d in cur.description]
    rows = [[("" if v is None else str(v))[:28] for v in r] for r in cur.fetchall()][::-1]
    total = conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    print("\nТаблиця %s (усього рядків: %d)" % (table, total))
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tables = [sys.argv[1]] if len(sys.argv) > 1 else TABLES
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    with sqlite3.connect(DB) as conn:
        for t in tables:
            show(conn, t, limit)


if __name__ == "__main__":
    main()
