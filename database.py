
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path(__file__).resolve().parent / "data" / "rawg_catalog.db"
DB.parent.mkdir(parents=True, exist_ok=True)

GAME_COLUMNS = {
    "rating": "TEXT DEFAULT ''",
    "ratings_count": "INTEGER DEFAULT 0",
    "rating_breakdown": "TEXT DEFAULT ''",
    "metacritic": "INTEGER",
    "platforms": "TEXT DEFAULT ''",
    "esrb_rating": "TEXT DEFAULT ''",
    "tags": "TEXT DEFAULT ''",
    "details_checked_at": "TEXT DEFAULT NULL",
}


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS games (
                rawg_id INTEGER PRIMARY KEY,
                slug TEXT DEFAULT '',
                name TEXT DEFAULT '',
                release_date TEXT DEFAULT '',
                genres TEXT DEFAULT '',
                developer TEXT DEFAULT '',
                publisher TEXT DEFAULT '',
                description TEXT DEFAULT '',
                minimum TEXT DEFAULT '',
                recommended TEXT DEFAULT '',
                image TEXT DEFAULT '',
                url TEXT DEFAULT '',
                download_url TEXT DEFAULT '',
                published INTEGER DEFAULT 0,
                published_at TEXT,
                discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                rating TEXT DEFAULT '',
                ratings_count INTEGER DEFAULT 0,
                rating_breakdown TEXT DEFAULT '',
                metacritic INTEGER,
                platforms TEXT DEFAULT '',
                esrb_rating TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                details_checked_at TEXT DEFAULT NULL
            )
        """)

        cols = {
            r["name"]
            for r in c.execute("PRAGMA table_info(games)")
        }

        for name, definition in {
            "download_url": "TEXT DEFAULT ''",
            **GAME_COLUMNS,
        }.items():
            if name not in cols:
                c.execute(
                    f"ALTER TABLE games ADD COLUMN {name} {definition}"
                )

        c.execute("""
            CREATE INDEX IF NOT EXISTS games_queue_idx
            ON games(published, name COLLATE NOCASE)
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS games_details_idx
            ON games(details_checked_at, rawg_id)
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        c.commit()


def setting(key):
    with conn() as c:
        r = c.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        ).fetchone()

        return r["value"] if r else None


def set_setting(key, value):
    with conn() as c:
        c.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
        """, (key, str(value)))

        c.commit()


def add_games(games):
    fields = [
        "id", "slug", "name", "release_date", "genres",
        "developer", "publisher", "description",
        "minimum", "recommended", "image", "url",
        "rating", "ratings_count", "rating_breakdown",
        "metacritic", "platforms", "esrb_rating", "tags"
    ]

    columns = ["rawg_id", *fields[1:]]
    rows = []

    for g in games:
        if g.get("id") and g.get("name"):
            rows.append(tuple(g.get(k) for k in fields))

    if not rows:
        return 0

    placeholders = ",".join("?" for _ in columns)

    updates = ",".join(
        f"""
        {col}=CASE
            WHEN (
                games.{col} IS NULL
                OR games.{col}=''
                OR games.{col}=0
            )
            AND excluded.{col} IS NOT NULL
            AND excluded.{col}!=''
            AND excluded.{col}!=0
            THEN excluded.{col}
            ELSE games.{col}
        END
        """
        for col in columns[1:]
    )

    with conn() as c:
        before = c.total_changes

        c.executemany(
            f"""
            INSERT INTO games ({','.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(rawg_id)
            DO UPDATE SET {updates}
            """,
            rows
        )

        changed = c.total_changes - before
        c.commit()

        return changed


# ============================================================
# ENRIQUECIMIENTO DE JUEGOS ANTIGUOS
# ============================================================

def games_needing_details(limit=5):
    """
    Devuelve juegos que todavía no han pasado por una
    consulta individual de detalles a RAWG.
    """

    limit = max(1, min(int(limit), 50))

    with conn() as c:
        return c.execute("""
            SELECT rawg_id, name
            FROM games
            WHERE details_checked_at IS NULL
            ORDER BY rowid
            LIMIT ?
        """, (limit,)).fetchall()


def mark_details_checked(rawg_id):
    """
    Registra que la ficha individual de RAWG
    se ha consultado correctamente.
    """

    timestamp = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    with conn() as c:
        c.execute("""
            UPDATE games
            SET details_checked_at=?
            WHERE rawg_id=?
        """, (timestamp, rawg_id))

        c.commit()


def details_pending_count():
    with conn() as c:
        return c.execute("""
            SELECT COUNT(*) AS n
            FROM games
            WHERE details_checked_at IS NULL
        """).fetchone()["n"]


# ============================================================
# COLA DE PUBLICACIONES
# ============================================================

def next_game():
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE published=0
            ORDER BY rowid
            LIMIT 1
        """).fetchone()


def pending_count():
    with conn() as c:
        return c.execute("""
            SELECT COUNT(*) AS n
            FROM games
            WHERE published=0
        """).fetchone()["n"]


def stats():
    with conn() as c:
        r = c.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(published=0) AS pending,
                SUM(published=1) AS published
            FROM games
        """).fetchone()

        return {
            k: int(r[k] or 0)
            for k in r.keys()
        }


def published_today(day):
    with conn() as c:
        return c.execute("""
            SELECT COUNT(*) AS n
            FROM games
            WHERE published=1
            AND published_at LIKE ?
        """, (day + "%",)).fetchone()["n"]


def last_published(day):
    with conn() as c:
        r = c.execute("""
            SELECT published_at
            FROM games
            WHERE published=1
            AND published_at LIKE ?
            ORDER BY published_at DESC
            LIMIT 1
        """, (day + "%",)).fetchone()

        return r["published_at"] if r else None


def mark_published(rawg_id, timestamp):
    with conn() as c:
        c.execute("""
            UPDATE games
            SET published=1, published_at=?
            WHERE rawg_id=?
        """, (timestamp, rawg_id))

        c.commit()


def set_download_link(rawg_id, url):
    with conn() as c:
        cur = c.execute("""
            UPDATE games
            SET download_url=?
            WHERE rawg_id=?
        """, (url, rawg_id))

        c.commit()
        return cur.rowcount


def find_game(rawg_id):
    with conn() as c:
        return c.execute("""
            SELECT rawg_id, name, published, download_url
            FROM games
            WHERE rawg_id=?
        """, (rawg_id,)).fetchone()


def pending_games(limit=15):
    with conn() as c:
        return c.execute("""
            SELECT rawg_id, name
            FROM games
            WHERE published=0
            ORDER BY rowid
            LIMIT ?
        """, (limit,)).fetchall()
