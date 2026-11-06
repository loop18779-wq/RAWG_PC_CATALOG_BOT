
import os
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent

TEST_DB = (
    ROOT
    / "backups"
    / "rawg_catalog_migracion_20261106_130404.db"
)

if not TEST_DB.exists():
    raise FileNotFoundError(
        f"No se encuentra la copia migrada: {TEST_DB}"
    )

# IMPORTANTE: seleccionar la copia antes de importar database_nueva.
os.environ["CATALOG_DB_PATH"] = str(TEST_DB)

import database_nueva as db


def main():
    print("=" * 55)
    print("PRUEBA DEL NUEVO MÓDULO DE BASE DE DATOS")
    print("=" * 55)

    print("\n1. Base de datos seleccionada:")
    print(TEST_DB)

    print("\n2. Inicializando estructura...")
    db.init()
    print("OK: estructura inicializada.")

    print("\n3. Comprobando registros existentes...")
    before = db.stats()

    print("Total:", before["total"])
    print("Pendientes:", before["pending"])
    print("Publicados:", before["published"])

    assert before["total"] == 10249, (
        "El total de registros no coincide."
    )

    assert before["published"] == 43, (
        "El n?mero de publicados no coincide."
    )

    assert (
        before["pending"]
        + before["future"]
        + before["without_date"]
        + before["published"]
        == before["total"]
    ), "Las categor?as de juegos no suman el total."

    print("OK: los registros originales se conservan.")

    print("\n4. Comprobando identificadores internos...")
    game = db.next_game()

    assert game is not None, "No hay juegos pendientes."

    print("Primer juego pendiente:", game["name"])
    print("game_id:", game["game_id"])
    print("rawg_id:", game["rawg_id"])

    found = db.find_game_by_game_id(game["game_id"])
    assert found is not None

    print("OK: búsqueda por game_id.")

    if game["rawg_id"] is not None:
        found_rawg = db.find_game(game["rawg_id"])
        assert found_rawg is not None
        print("OK: búsqueda por rawg_id.")

    print("\n5. Probando incorporación IGDB + Steam...")

    # Identificadores artificiales para esta prueba local.
    test_id = 9000000000000000000 + int(time.time()) % 1000000
    test_steam_id = test_id + 1
    test_name = "__PRUEBA_MIGRACION_IGDB_STEAM__"

    try:
        igdb_game_id = db.upsert_game(
            {
                "id": test_id,
                "name": test_name,
                "release_date": "2026-01-01",
                "platforms": "Windows",
                "description": "Registro artificial de prueba."
            },
            source="igdb"
        )

        first = db.find_game_by_game_id(igdb_game_id)

        assert first is not None
        assert first["igdb_id"] == test_id

        print("OK: videojuego IGDB insertado.")
        print("game_id interno:", igdb_game_id)

        steam_game_id = db.upsert_game(
            {
                "steam_app_id": test_steam_id,
                "igdb_id": test_id,
                "name": test_name,
                "url": "https://store.steampowered.com/"
            },
            source="steam"
        )

        second = db.find_game_by_game_id(steam_game_id)

        assert second is not None
        assert second["game_id"] == igdb_game_id
        assert second["igdb_id"] == test_id
        assert second["steam_app_id"] == test_steam_id

        print("OK: Steam se ha asociado al mismo videojuego.")
        print("No se ha creado un registro duplicado.")

    finally:
        # Eliminar únicamente el registro artificial de esta prueba.
        with db.conn() as c:
            c.execute("""
                DELETE FROM games
                WHERE name = ?
                  AND igdb_id = ?
                  AND steam_app_id = ?
            """, (test_name, test_id, test_steam_id))

    print("\n6. Comprobando que no se han alterado los registros...")
    after = db.stats()

    print("Antes:", before)
    print("Después:", after)

    assert before == after, (
        "La prueba ha dejado cambios en los registros originales."
    )

    print("OK: la base de datos conserva sus estadísticas.")

    print("\n" + "=" * 55)
    print("TODAS LAS PRUEBAS HAN FINALIZADO CORRECTAMENTE")
    print("=" * 55)
    print("\nLa base original del bot no se ha utilizado.")


if __name__ == "__main__":
    main()
