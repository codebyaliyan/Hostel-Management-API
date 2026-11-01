"""
db.py - everything related to talking to MySQL.

Same helpers as before (db_cursor, query_all, query_one, execute).
The only change: pool size is now read from .env (DB_POOL_SIZE) so you can
raise it when more branches/users hit the API at the same time.
"""

import os
from pathlib import Path
from contextlib import contextmanager

from dotenv import load_dotenv
from mysql.connector import pooling

# Read DB_HOST, DB_USER, ... from the .env file
load_dotenv(Path(__file__).resolve().with_name(".env"))

_pool = None


def _get_pool():
    """Create the connection pool the first time it is needed."""
    global _pool

    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="hostel_pool",
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),  # mysql-connector allows max 32
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "hostel_db_v3"),
        )

    return _pool


@contextmanager
def db_cursor():
    """
    Use it like this:

        with db_cursor() as cur:
            cur.execute("SELECT * FROM students WHERE id = %s", (5,))
            row = cur.fetchone()

    - If everything works, the changes are saved (commit).
    - If anything fails, ALL changes inside the block are undone (rollback).
      This is important when one action changes two tables
      (for example: allocation + bed status).
    """
    connection = _get_pool().get_connection()
    cursor = connection.cursor(dictionary=True)  # rows come back as dicts

    try:
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()  # returns the connection to the pool


def query_all(sql, params=None):
    """Run a SELECT and return a list of rows."""
    with db_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql, params=None):
    """Run a SELECT and return one row (or None)."""
    with db_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    """Run INSERT / UPDATE / DELETE. Returns the new row id for INSERT."""
    with db_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.lastrowid

def execute_rowcount(sql, params=None):
    """Run UPDATE / DELETE and return how many rows it changed."""
    with db_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount