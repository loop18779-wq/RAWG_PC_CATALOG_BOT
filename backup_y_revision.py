
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "rawg_catalog.db"
BACKUP_DIR = ROOT / "backups"

if not DB.exists():
    raise SystemExit("ERROR: no se encuentra la base de datos.")

BACKUP_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = BACKUP_DIR / f"rawg_catalog_backup_{timestamp}.db"

# Crear copia mediante el mecanismo seguro de SQLite.
with sqlite3.connect(DB) as source:
    with sqlite3.connect(BACKUP) as destination:
        source.backup(destination)

print("=== COPIA DE SEGURIDAD ===")
print("Archivo:", BACKUP)
print("Tamaño:", round(BACKUP.stat().st_size / 1024, 2), "KB")

# Comprobar la copia.
with sqlite3.connect(BACKUP) as conn:
    conn.row_factory = sqlite3.Row

    print("\nIntegridad de la copia:")
    print(conn.execute("PRAGMA integrity_check").fetchone()[0])

    print("\nÍndices existentes:")
    indexes = conn.execute("""
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'index'
        AND tbl_name = 'games'
        ORDER BY name
    """).fetchall()

    for index in indexes:
        print("-", index["name"])
        print(" ", index["sql"])

    print("\nEstado de los enlaces:")
    print(dict(conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(download_url IS NULL) AS nulos,
            SUM(TRIM(download_url) = '') AS vacios,
            SUM(TRIM(download_url) != '') AS con_contenido
        FROM games
    """).fetchone()))

    print("\nEjemplos de videojuegos:")
    games = conn.execute("""
        SELECT rawg_id, name, published,
               release_date, details_checked_at
        FROM games
        ORDER BY rawg_id
        LIMIT 8
    """).fetchall()

    for game in games:
        print(dict(game))

    print("\nConfiguración guardada:")
    settings = conn.execute("""
        SELECT key FROM settings ORDER BY key
    """).fetchall()

    for item in settings:
        print("-", item["key"])

print("\n=== REVISIÓN TERMINADA ===")
