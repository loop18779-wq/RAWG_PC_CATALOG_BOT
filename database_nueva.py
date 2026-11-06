
import os
import sqlite3
from pathlib import Path
from datetime import datetime, date


ROOT = Path(__file__).resolve().parent

# Permite seleccionar una base de datos de prueba sin modificar la original.
CONFIGURED_DB = os.getenv("CATALOG_DB_PATH")

if CONFIGURED_DB:
    # Si existe una ruta configurada, respetarla.
    DB = Path(CONFIGURED_DB)
else:
    # Buscar automáticamente la última base migrada.
    BACKUPS_DIR = ROOT / "backups"

    migrated_databases = sorted(
        BACKUPS_DIR.glob("rawg_catalog_migracion_*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    if migrated_databases:
        DB = migrated_databases[0]
    else:
        # Compatibilidad si todavía no existe una base migrada.
        DB = ROOT / "data" / "rawg_catalog.db"

DB.parent.mkdir(parents=True, exist_ok=True)

print(f"BASE DE DATOS SELECCIONADA: {DB}")


def conn():
    """Abre una conexión SQLite."""
    connection = sqlite3.connect(DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init():
    """
    Comprueba la estructura de la base de datos.
    Este módulo está diseñado para trabajar con la copia migrada,
    que ya debe contener game_id.
    """
    with conn() as c:
        c.execute("PRAGMA journal_mode = WAL")

        exists = c.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'games'
        """).fetchone()

        if not exists:
            c.execute("""
                CREATE TABLE games (
                    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rawg_id INTEGER UNIQUE,
                    igdb_id INTEGER UNIQUE,
                    steam_app_id INTEGER UNIQUE,
                    slug TEXT,
                    name TEXT,
                    release_date TEXT,
                    genres TEXT,
                    developer TEXT,
                    publisher TEXT,
                    description TEXT,
                    minimum TEXT,
                    recommended TEXT,
                    image TEXT,
                    url TEXT,
                    download_url TEXT,
                    published INTEGER DEFAULT 0,
                    published_at TEXT,
                    discovered_at TEXT,
                    rating REAL,
                    ratings_count INTEGER,
                    rating_breakdown TEXT,
                    metacritic INTEGER,
                    platforms TEXT,
                    esrb_rating TEXT,
                    tags TEXT,
                    details_checked_at TEXT
                )
            """)

        columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(games)").fetchall()
        }

        if "game_id" not in columns:
            raise RuntimeError(
                "Esta base de datos no contiene game_id. "
                "Ejecuta primero la migración de prueba."
            )

        optional_columns = {
            "rawg_id": "INTEGER",
            "igdb_id": "INTEGER",
            "steam_app_id": "INTEGER",
            "slug": "TEXT",
            "name": "TEXT",
            "release_date": "TEXT",
            "genres": "TEXT",
            "developer": "TEXT",
            "publisher": "TEXT",
            "description": "TEXT",
            "minimum": "TEXT",
            "recommended": "TEXT",
            "image": "TEXT",
            "url": "TEXT",
            "download_url": "TEXT",
            "published": "INTEGER DEFAULT 0",
            "published_at": "TEXT",
            "discovered_at": "TEXT",
            "rating": "REAL",
            "ratings_count": "INTEGER",
            "rating_breakdown": "TEXT",
            "metacritic": "INTEGER",
            "platforms": "TEXT",
            "esrb_rating": "TEXT",
            "tags": "TEXT",
            "details_checked_at": "TEXT",
        }

        for column, definition in optional_columns.items():
            if column not in columns:
                c.execute(
                    f"ALTER TABLE games ADD COLUMN {column} {definition}"
                )

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS games_rawg_id_idx
            ON games(rawg_id)
        """)

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS games_igdb_id_idx
            ON games(igdb_id)
        """)

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS games_steam_app_id_idx
            ON games(steam_app_id)
        """)

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


def setting(key, default=None):
    with conn() as c:
        row = c.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        ).fetchone()

        return row["value"] if row else default


def set_setting(key, value):
    with conn() as c:
        c.execute("""
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (key, str(value)))


def _normalise_game(game, source):
    """Convierte los identificadores de cada proveedor a un formato común."""
    g = dict(game)

    if source == "rawg":
        g["rawg_id"] = g.get("rawg_id") or g.get("id")

    elif source == "igdb":
        g["igdb_id"] = g.get("igdb_id") or g.get("id")

    elif source == "steam":
        g["steam_app_id"] = (
            g.get("steam_app_id") or g.get("appid") or g.get("id")
        )

    else:
        raise ValueError("Proveedor desconocido: " + str(source))

    for field in ("rawg_id", "igdb_id", "steam_app_id"):
        if g.get(field) is not None:
            g[field] = int(g[field])

    g.pop("id", None)
    g.pop("appid", None)

    if not g.get("name"):
        raise ValueError("El videojuego debe tener un nombre.")

    return g


def upsert_game(game, source):
    """
    Inserta o actualiza un videojuego.

    Si los identificadores de dos proveedores apuntan al mismo registro,
    se incorporan ambos al mismo game_id.

    No realiza coincidencias automáticas por nombre, para evitar
    fusionar juegos diferentes que tengan títulos iguales.
    """
    g = _normalise_game(game, source)

    allowed = {
        "rawg_id", "igdb_id", "steam_app_id",
        "slug", "name", "release_date", "genres",
        "developer", "publisher", "description",
        "minimum", "recommended", "image", "url",
        "download_url", "published", "published_at",
        "discovered_at", "rating", "ratings_count",
        "rating_breakdown", "metacritic", "platforms",
        "esrb_rating", "tags", "details_checked_at"
    }

    values = {
        key: value
        for key, value in g.items()
        if key in allowed
    }

    identifiers = [
        (field, values[field])
        for field in ("rawg_id", "igdb_id", "steam_app_id")
        if values.get(field) is not None
    ]

    if not identifiers:
        raise ValueError(
            "El juego necesita un identificador RAWG, IGDB o Steam."
        )

    with conn() as c:
        c.execute("BEGIN IMMEDIATE")

        matches = set()

        for field, identifier in identifiers:
            row = c.execute(
                f"SELECT game_id FROM games WHERE {field} = ?",
                (identifier,)
            ).fetchone()

            if row:
                matches.add(row["game_id"])

        if len(matches) > 1:
            raise ValueError(
                "Los identificadores proporcionados pertenecen "
                "a videojuegos diferentes. No se han fusionado."
            )

        if matches:
            game_id = matches.pop()

            current = c.execute(
                "SELECT * FROM games WHERE game_id = ?",
                (game_id,)
            ).fetchone()

            updates = {}

            for field, value in values.items():
                if field == "published":
                    continue

                old_value = current[field]

                # Solo completar campos vacíos: no borrar información
                # existente con datos vacíos de otro proveedor.
                if value not in (None, "", 0) and old_value in (
                    None, "", 0
                ):
                    updates[field] = value

            if updates:
                assignments = ", ".join(
                    f"{field} = ?" for field in updates
                )

                c.execute(
                    f"UPDATE games SET {assignments} WHERE game_id = ?",
                    (*updates.values(), game_id)
                )

            return game_id

        fields = list(values.keys())
        placeholders = ", ".join("?" for _ in fields)
        columns = ", ".join(fields)

        cursor = c.execute(
            f"INSERT INTO games ({columns}) "
            f"VALUES ({placeholders})",
            tuple(values[field] for field in fields)
        )

        return cursor.lastrowid


def upsert_igdb_games(games):
    ids = []
    for game in games:
        ids.append(upsert_game(game, "igdb"))
    return ids


def upsert_steam_games(games):
    ids = []
    for game in games:
        ids.append(upsert_game(game, "steam"))
    return ids


def add_games(games):
    """
    Compatibilidad con el antiguo RAWG:
    el campo id se interpreta como rawg_id.
    """
    count = 0

    for game in games:
        upsert_game(game, "rawg")
        count += 1

    return count


def games_needing_details(limit=5):
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE rawg_id IS NOT NULL
              AND details_checked_at IS NULL
            ORDER BY game_id
            LIMIT ?
        """, (limit,)).fetchall()


def mark_details_checked(rawg_id):
    with conn() as c:
        c.execute("""
            UPDATE games
            SET details_checked_at = ?
            WHERE rawg_id = ?
        """, (datetime.now().isoformat(), rawg_id))


def details_pending_count():
    with conn() as c:
        row = c.execute("""
            SELECT COUNT(*) AS total
            FROM games
            WHERE rawg_id IS NOT NULL
              AND details_checked_at IS NULL
        """).fetchone()

        return row["total"]


def next_game():
    """Devuelve el siguiente juego pendiente con fecha válida ya alcanzada."""
    hoy = date.today().isoformat()

    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE published = 0
              AND release_date GLOB
                  '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
              AND date(release_date) IS NOT NULL
              AND date(release_date) <= date(?)
            ORDER BY game_id
            LIMIT 1
        """, (hoy,)).fetchone()


def pending_count():
    """Cuenta únicamente los juegos publicables por fecha."""
    hoy = date.today().isoformat()

    with conn() as c:
        return c.execute("""
            SELECT COUNT(*)
            FROM games
            WHERE published = 0
              AND release_date GLOB
                  '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
              AND date(release_date) IS NOT NULL
              AND date(release_date) <= date(?)
        """, (hoy,)).fetchone()[0]


def stats():
    """Devuelve estadísticas separando juegos publicables y no publicables."""
    hoy = date.today().isoformat()

    with conn() as c:
        row = c.execute("""
            SELECT
                COUNT(*) AS total,

                SUM(CASE
                    WHEN published = 0
                     AND release_date GLOB
                         '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                     AND date(release_date) IS NOT NULL
                     AND date(release_date) <= date(?)
                    THEN 1 ELSE 0
                END) AS pending,

                SUM(CASE
                    WHEN published = 0
                     AND release_date GLOB
                         '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                     AND date(release_date) > date(?)
                    THEN 1 ELSE 0
                END) AS future,

                SUM(CASE
                    WHEN published = 0
                     AND (
                         release_date IS NULL
                         OR TRIM(release_date) = ''
                         OR release_date = 'No especificada'
                         OR date(release_date) IS NULL
                    )
                    THEN 1 ELSE 0
                END) AS without_date,

                SUM(CASE
                    WHEN published = 1
                    THEN 1 ELSE 0
                END) AS published

            FROM games
        """, (hoy, hoy)).fetchone()

        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "future": row["future"] or 0,
            "without_date": row["without_date"] or 0,
            "published": row["published"] or 0
        }


def published_today(today=None):
    if today is None:
        today = date.today().isoformat()

    with conn() as c:
        return c.execute("""
            SELECT COUNT(*)
            FROM games
            WHERE published = 1
              AND published_at LIKE ?
        """, (today + "%",)).fetchone()[0]


def last_published():
    with conn() as c:
        row = c.execute("""
            SELECT published_at
            FROM games
            WHERE published = 1
              AND published_at IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 1
        """).fetchone()

        return row["published_at"] if row else None


def mark_published_by_game_id(game_id, timestamp):
    with conn() as c:
        c.execute("""
            UPDATE games
            SET published = 1,
                published_at = ?
            WHERE game_id = ?
        """, (timestamp, game_id))


def mark_published(rawg_id, timestamp):
    """Compatibilidad con el antiguo publicador RAWG."""
    with conn() as c:
        c.execute("""
            UPDATE games
            SET published = 1,
                published_at = ?
            WHERE rawg_id = ?
        """, (timestamp, rawg_id))


def find_game(rawg_id):
    """Busca por identificador RAWG, como hacía el bot original."""
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE rawg_id = ?
        """, (rawg_id,)).fetchone()


def find_game_by_game_id(game_id):
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE game_id = ?
        """, (game_id,)).fetchone()


def find_game_by_igdb_id(igdb_id):
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE igdb_id = ?
        """, (igdb_id,)).fetchone()


def find_game_by_steam_id(steam_app_id):
    with conn() as c:
        return c.execute("""
            SELECT *
            FROM games
            WHERE steam_app_id = ?
        """, (steam_app_id,)).fetchone()


def set_download_link(rawg_id, url):
    """Compatibilidad con el comando antiguo /enlace."""
    with conn() as c:
        c.execute("""
            UPDATE games
            SET download_url = ?
            WHERE rawg_id = ?
        """, (url, rawg_id))


def set_download_link_by_game_id(game_id, url):
    with conn() as c:
        c.execute("""
            UPDATE games
            SET download_url = ?
            WHERE game_id = ?
        """, (url, game_id))


def pending_games(limit=15):
    """Lista únicamente juegos pendientes con fecha válida ya alcanzada."""
    hoy = date.today().isoformat()

    with conn() as c:
        return c.execute("""
            SELECT game_id, rawg_id, igdb_id, steam_app_id, name
            FROM games
            WHERE published = 0
              AND release_date GLOB
                  '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
              AND date(release_date) IS NOT NULL
              AND date(release_date) <= date(?)
            ORDER BY game_id
            LIMIT ?
        """, (hoy, limit)).fetchall()
