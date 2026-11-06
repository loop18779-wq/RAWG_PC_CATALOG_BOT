
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "data" / "rawg_catalog.db"
BACKUPS = ROOT / "backups"
BACKUPS.mkdir(exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TEST_DB = BACKUPS / f"rawg_catalog_migracion_{STAMP}.db"

def main():
    if not ORIGINAL.exists():
        raise FileNotFoundError(f"No existe la base original: {ORIGINAL}")

    print("1. Creando copia de trabajo...")
    shutil.copy2(ORIGINAL, TEST_DB)

    print("2. Comprobando integridad...")
    with sqlite3.connect(TEST_DB) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Base de datos no íntegra: {integrity}")

        before = conn.execute("""
            SELECT
                COUNT(*),
                SUM(published = 0),
                SUM(published = 1)
            FROM games
        """).fetchone()

        print("   Registros originales:", before[0])
        print("   Pendientes:", before[1])
        print("   Publicados:", before[2])

        print("3. Preparando nueva estructura...")
        conn.execute("BEGIN IMMEDIATE")

        conn.execute("""
            CREATE TABLE games_new (
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
                rating TEXT,
                ratings_count INTEGER DEFAULT 0,
                rating_breakdown TEXT,
                metacritic INTEGER,
                platforms TEXT,
                esrb_rating TEXT,
                tags TEXT,
                details_checked_at TEXT
            )
        """)

        conn.execute("""
            INSERT INTO games_new (
                rawg_id, slug, name, release_date,
                genres, developer, publisher, description,
                minimum, recommended, image, url, download_url,
                published, published_at, discovered_at,
                rating, ratings_count, rating_breakdown,
                metacritic, platforms, esrb_rating, tags,
                details_checked_at
            )
            SELECT
                rawg_id, slug, name, release_date,
                genres, developer, publisher, description,
                minimum, recommended, image, url, download_url,
                published, published_at, discovered_at,
                rating, ratings_count, rating_breakdown,
                metacritic, platforms, esrb_rating, tags,
                details_checked_at
            FROM games
        """)

        conn.execute("DROP TABLE games")
        conn.execute("ALTER TABLE games_new RENAME TO games")

        conn.execute("""
            CREATE INDEX games_queue_idx
            ON games(published, name COLLATE NOCASE)
        """)

        conn.execute("""
            CREATE INDEX games_details_idx
            ON games(details_checked_at, rawg_id)
        """)

        after = conn.execute("""
            SELECT
                COUNT(*),
                SUM(published = 0),
                SUM(published = 1)
            FROM games
        """).fetchone()

        if tuple(before) != tuple(after):
            raise RuntimeError(
                f"Los recuentos no coinciden: antes={tuple(before)}, "
                f"después={tuple(after)}"
            )

        conn.commit()

        print("4. Verificando migración...")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Integridad incorrecta: {integrity}")

        print("   Integridad:", integrity)
        print("   Registros migrados:", after[0])
        print("   Pendientes:", after[1])
        print("   Publicados:", after[2])

        columns = conn.execute("PRAGMA table_info(games)").fetchall()
        print("   Nueva columna game_id:", any(c[1] == "game_id" for c in columns))
        print("   Nueva columna igdb_id:", any(c[1] == "igdb_id" for c in columns))
        print("   Nueva columna steam_app_id:", any(c[1] == "steam_app_id" for c in columns))

    print("\nMIGRACIÓN DE PRUEBA COMPLETADA.")
    print("Base original intacta.")
    print("Copia migrada:", TEST_DB)

if __name__ == "__main__":
    main()
