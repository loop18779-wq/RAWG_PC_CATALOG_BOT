
import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "rawg_catalog.db"

load_dotenv(ROOT / ".env")

print("=== DIAGNÓSTICO DEL PROYECTO ===")

print("\nCredenciales configuradas:")
for key in (
    "IGDB_CLIENT_ID",
    "IGDB_CLIENT_SECRET",
    "RAWG_API_KEY",
    "TELEGRAM_BOT_TOKEN",
):
    print(f"{key}: {'CONFIGURADA' if os.getenv(key) else 'NO CONFIGURADA'}")

print("\nBase de datos:")
print("Ruta:", DB)
print("Existe:", DB.exists())

if not DB.exists():
    raise SystemExit("No se encuentra la base de datos.")

print("Tamaño:", round(DB.stat().st_size / 1024, 2), "KB")

with sqlite3.connect(DB) as conn:
    conn.row_factory = sqlite3.Row

    print("\nIntegridad:")
    print(conn.execute("PRAGMA integrity_check").fetchone()[0])

    print("\nTablas:")
    tables = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """).fetchall()

    for table in tables:
        name = table["name"]
        print(f"\n--- {name} ---")

        columns = conn.execute(
            f'PRAGMA table_info("{name}")'
        ).fetchall()

        print("Columnas:", ", ".join(c["name"] for c in columns))

        if name == "games":
            stats = conn.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(published=0) AS pendientes,
                    SUM(published=1) AS publicados,
                    COUNT(download_url) AS enlaces
                FROM games
            """).fetchone()

            print("Registros:", dict(stats))

        elif name == "settings":
            keys = conn.execute(
                "SELECT key FROM settings ORDER BY key"
            ).fetchall()

            print("Claves:", [r["key"] for r in keys])

print("\n=== FIN DEL DIAGNÓSTICO ===")
