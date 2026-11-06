import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "publicidad.db"


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def init():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS advertising_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                invite_url TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_advertising_active
            ON advertising_groups(active)
        """)


def add_group(chat_id, title, invite_url):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO advertising_groups (
                chat_id,
                title,
                invite_url,
                active
            )
            VALUES (?, ?, ?, 1)

            ON CONFLICT(chat_id)
            DO UPDATE SET
                title = excluded.title,
                invite_url = excluded.invite_url,
                active = 1
        """, (chat_id, title, invite_url))


def get_active_groups():
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM advertising_groups
            WHERE active = 1
            ORDER BY id ASC
        """).fetchall()


def get_all_groups():
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM advertising_groups
            ORDER BY id ASC
        """).fetchall()


def set_group_active(chat_id, active):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE advertising_groups
            SET active = ?
            WHERE chat_id = ?
        """, (int(active), chat_id))

        return cursor.rowcount


def delete_group(chat_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            DELETE FROM advertising_groups
            WHERE chat_id = ?
        """, (chat_id,))

        return cursor.rowcount